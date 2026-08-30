"""Automatic Number Plate Recognition (ANPR) for the IBVAP platform.

Layered design, all substitutions contained behind clean interfaces:

* :class:`PlateDetector` -- turns a vehicle crop into candidate plate
  rectangles. The default :class:`ClassicalCVPlateDetector` needs no
  externally-downloaded ML weights (grayscale -> Canny edges -> contours ->
  aspect/size filtering); a fine-tuned YOLO ``.pt`` can later be supplied
  purely via ``settings.anpr_model_path`` without touching any caller.

* :class:`PlateReader` -- EasyOCR wrapper; does grayscale + CLAHE
  contrast enhancement and deskewing before recognition, then normalizes
  and validates output against the Indian plate grammar.

* :class:`PlateTracker` -- per-track best-read selection and dedup that
  mirrors the crossing-gate + stale-eviction pattern used by
  :class:`~alerts.AlertEngine`.

* :class:`AnprPipeline` -- runs the detector + reader on a dedicated
  background thread behind a bounded queue (same shape as
  :class:`~channels.WebhookChannel`), so OCR can never stall the live
  fence-detection loop.

The only network I/O is EasyOCR fetching its own recognition weights once
via its normal install process -- there is no plate-detection model fetch.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Sequence

import cv2
import numpy as np

from models import PlateReading

Logger = logging.Logger

# COCO classes that can carry a readable number plate.
VEHICLE_CLASSES: frozenset[str] = frozenset({"car", "truck", "bus", "motorbike"})

_INDIAN_PLATE_PATTERN = r"^[A-Z]{2}[0-9]{2}[A-Z]{0,2}[0-9]{4}$"
_EURO_PLATE_PATTERN = r"^[A-Z]{1,3}[0-9]{3,5}[A-Z]{1,3}$"
_GENERAL_PLATE_PATTERN = r"^[A-Z0-9]{6,10}$"

# OCR confusion: a digit rendered where a letter is expected.
_DIGIT_AS_LETTER = {
    "0": "O", "1": "I", "8": "B", "5": "S", "2": "Z", "6": "G",
}
# OCR confusion: a letter rendered where a digit is expected.
_LETTER_AS_DIGIT = {
    "O": "0", "I": "1", "B": "8", "S": "5", "Z": "2", "G": "6", "Q": "0",
    "D": "0", "J": "1", "T": "7",
}

_PLATE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _normalize_indian_plate(cleaned: str) -> str | None:
    optional_letters = len(cleaned) - 8
    if optional_letters not in (0, 1, 2):
        return None

    letter_slots: set[int] = {0, 1}
    if optional_letters >= 1:
        letter_slots.add(4)
    if optional_letters == 2:
        letter_slots.add(5)

    chars = list(cleaned)
    for index, char in enumerate(chars):
        if index in letter_slots and char in _DIGIT_AS_LETTER:
            chars[index] = _DIGIT_AS_LETTER[char]
        elif index not in letter_slots and char in _LETTER_AS_DIGIT:
            chars[index] = _LETTER_AS_DIGIT[char]

    candidate = "".join(chars)
    import re
    if re.fullmatch(_INDIAN_PLATE_PATTERN, candidate):
        return candidate
    return None


def _normalize_euro_plate(cleaned: str) -> str | None:
    """Normalize European/Standard formats like AA3325MM or AI7060EC."""
    import re
    if 6 <= len(cleaned) <= 10:
        # Check standard euro pattern (letters + numbers + letters or letters + numbers)
        if re.fullmatch(_EURO_PLATE_PATTERN, cleaned):
            return cleaned
        # Must have at least 2 letters and 2 digits
        num_letters = sum(1 for c in cleaned if c.isalpha())
        num_digits = sum(1 for c in cleaned if c.isdigit())
        if num_letters >= 2 and num_digits >= 2 and re.fullmatch(_GENERAL_PLATE_PATTERN, cleaned):
            return cleaned
    return None


def normalize_plate_text(raw: str) -> str | None:
    """Validate and clean an OCR string into a canonical plate.

    Supports both Indian plate grammar (with slot-based confusion correction)
    and International/European plate formats (e.g. AA3325MM, AI7060EC).

    Returns the normalized string (uppercase, no separators) or ``None``
    when the input cannot be a plausible plate (garbage rejected).
    """
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw if ch.isalnum()).upper()
    if not cleaned or len(cleaned) < 6 or len(cleaned) > 10:
        return None

    # First try Indian plate normalization (with confusion slot fixing)
    indian = _normalize_indian_plate(cleaned)
    if indian is not None:
        return indian

    # Second try European/International plate format
    euro = _normalize_euro_plate(cleaned)
    if euro is not None:
        return euro

    return None


# -------------------------------------------------------------- plate detector


@dataclass(frozen=True, slots=True)
class PlateCandidate:
    """A candidate plate rectangle, coordinates relative to the vehicle crop."""

    x1: int
    y1: int
    x2: int
    y2: int
    score: float = 0.0

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height


class PlateDetector(ABC):
    """Interface for producing plate candidates from a vehicle crop."""

    @abstractmethod
    def detect(self, crop: np.ndarray) -> list[PlateCandidate]:
        """Return candidate plate rectangles inside ``crop``."""

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the detector."""


def _iou(a: PlateCandidate, b: PlateCandidate) -> float:
    left = max(a.x1, b.x1)
    right = min(a.x2, b.x2)
    top = max(a.y1, b.y1)
    bottom = min(a.y2, b.y2)
    inter = max(0, right - left) * max(0, bottom - top)
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def _nms(candidates: Sequence[PlateCandidate], threshold: float = 0.3) -> list[PlateCandidate]:
    keep: list[PlateCandidate] = []
    for candidate in sorted(candidates, key=lambda c: c.area, reverse=True):
        if not any(_iou(candidate, kept) > threshold for kept in keep):
            keep.append(candidate)
    return keep


class ClassicalCVPlateDetector(PlateDetector):
    """Zero-download plate detector using classical computer vision.

    On a vehicle crop: grayscale -> gaussian blur -> Canny edges ->
    contours -> aspect-ratio / size filtering -> lightweight NMS.
    Tuned to be permissive (plates are rare) and to rank candidates by
    area; the OCR + validator stage is what rejects false positives.

    A second pass uses morphological closing + adaptive thresholding to
    catch plates that the Canny pipeline misses (common on low-contrast
    or distant footage).
    """

    def __init__(
        self,
        *,
        min_aspect: float = 1.3,
        max_aspect: float = 7.0,
        min_width_ratio: float = 0.05,
        min_area_ratio: float = 0.0005,
        max_candidates: int = 6,
    ) -> None:
        self._min_aspect = min_aspect
        self._max_aspect = max_aspect
        self._min_width_ratio = min_width_ratio
        self._min_area_ratio = min_area_ratio
        self._max_candidates = max_candidates

    def _filter_contours(
        self,
        contours: Sequence,
        crop_w: int,
        crop_h: int,
    ) -> list[PlateCandidate]:
        """Shared contour-to-candidate filtering used by both passes."""
        crop_area = float(crop_h * crop_w)
        min_width = self._min_width_ratio * crop_w
        min_area = self._min_area_ratio * crop_area

        candidates: list[PlateCandidate] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < min_width or h < 8:
                continue
            area = float(w * h)
            if area < min_area:
                continue
            aspect = w / float(h)
            if not self._min_aspect <= aspect <= self._max_aspect:
                continue
            candidates.append(
                PlateCandidate(x, y, x + w, y + h, score=area / crop_area)
            )
        return candidates

    def detect(self, crop: np.ndarray) -> list[PlateCandidate]:
        if crop is None or crop.size == 0:
            return []
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        crop_h, crop_w = gray.shape

        # --- Pass 1: Canny edges (original approach, relaxed thresholds) ---
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours_canny, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        candidates = self._filter_contours(contours_canny, crop_w, crop_h)

        # --- Pass 2: Morphological closing + adaptive threshold ---
        # This catches plates the Canny pipeline misses on low-contrast
        # or small crops common with distant vehicles.
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        morph = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)
        adaptive = cv2.adaptiveThreshold(
            morph, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 8,
        )
        contours_morph, _ = cv2.findContours(
            adaptive, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        candidates.extend(self._filter_contours(contours_morph, crop_w, crop_h))

        kept = _nms(candidates)
        kept.sort(key=lambda c: c.score, reverse=True)
        return kept[: self._max_candidates]

    def close(self) -> None:
        return None


def create_plate_detector(
    model_path: Path | None, confidence: float = 0.5
) -> PlateDetector:
    """Factory for plate detectors, driven purely by configuration.

    ``model_path=None`` selects the classical CV detector. A future
    ``anpr_model_path`` pointing at a fine-tuned YOLO ``.pt`` will select
    a model-backed detector here -- no caller needs to change.
    """
    if model_path is not None:
        raise NotImplementedError(
            "Model-backed plate detector not yet wired; use the classical "
            "fallback (anpr_model_path=None) for now."
        )
    return ClassicalCVPlateDetector()


# ------------------------------------------------------------------- reading


def _deskew(plate_gray: np.ndarray) -> np.ndarray:
    """Rotate a slightly tilted plate so OCR sees horizontal text."""
    _, binary = cv2.threshold(
        plate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    points = np.column_stack(np.where(binary > 0))
    if len(points) < 50:
        return plate_gray

    rotated = cv2.minAreaRect(points)
    _, (width, height), angle = rotated
    if width < height:
        angle += 90.0
    if abs(angle) < 0.8 or abs(angle) > 45.0:
        return plate_gray

    height_px, width_px = plate_gray.shape
    matrix = cv2.getRotationMatrix2D((width_px / 2.0, height_px / 2.0), angle, 1.0)
    return cv2.warpAffine(
        plate_gray,
        matrix,
        (width_px, height_px),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


class PlateReader:
    """EasyOCR wrapper: preprocess, recognize and validate a plate crop.

    EasyOCR is loaded lazily so the rest of the platform runs even if the
    library (or its on-device weights) is unavailable; in that case reads
    simply never succeed and the ANPR pipeline disables itself gracefully.
    """

    ALLOWLIST = _PLATE_CHARS

    def __init__(
        self,
        *,
        min_confidence: float = 0.5,
        gpu: bool = False,
        logger: Logger | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._gpu = gpu
        self._log = (logger or logging.getLogger("ibvap")).getChild("anpr")
        self._reader: object | None = None
        self._init_error: Exception | None = None
        self._warned_unavailable = False
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    # ------------------------------------------------------------------ API
    @property
    def unavailable(self) -> bool:
        return self._init_error is not None

    def ensure_loaded(self, quiet: bool = False) -> bool:
        """Make sure the EasyOCR engine is loaded; idempotent, never raises."""
        if self._reader is not None:
            return True
        if self._init_error is not None:
            return False
        try:
            import easyocr

            self._reader = easyocr.Reader(["en"], gpu=self._gpu, verbose=False)
            self._log.info("EasyOCR recognition engine loaded")
            return True
        except Exception as exc:  # network download, import, or runtime failure
            self._init_error = exc
            if not self._warned_unavailable:
                self._log.error(
                    "EasyOCR unavailable (%s); ANPR OCR disabled for this run",
                    exc,
                )
                self._warned_unavailable = True
            elif not quiet:
                self._log.debug("EasyOCR still unavailable: %s", exc)
            return False

    def preprocess(self, plate_bgr: np.ndarray) -> np.ndarray:
        """Grayscale -> bilateral filter -> CLAHE -> deskew -> upscale.

        Bilateral filtering preserves edges while smoothing noise, which
        is critical for small plates from distant vehicles.  The upscale
        target is 280 px (up from 220) so EasyOCR gets enough pixels to
        distinguish plate characters on low-resolution crops.
        """
        gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        gray = self._clahe.apply(gray)
        gray = _deskew(gray)
        if gray.shape[1] < 280:
            scale = 280.0 / gray.shape[1]
            gray = cv2.resize(
                gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def read_plate(self, plate_image: np.ndarray) -> tuple[str, float] | None:
        """Return ``(normalized_text, confidence)`` for the best valid read."""
        if not self.ensure_loaded():
            return None
        assert self._reader is not None

        results = self._reader.readtext(
            plate_image,
            allowlist=self.ALLOWLIST,
            detail=1,
            paragraph=False,
        )
        best: tuple[str, float] | None = None
        for _, ocr_text, confidence in results:
            if confidence < self._min_confidence:
                continue
            text = ocr_text.strip().upper()
            if not text:
                continue
            normalized = normalize_plate_text(text)
            if normalized is None:
                continue
            if best is None or float(confidence) > best[1]:
                best = (normalized, float(confidence))
        return best


# ------------------------------------------------------------- plate tracker


@dataclass(slots=True)
class _TrackPlates:
    last_seen_frame: int = 0
    emitted: bool = False
    best: PlateReading | None = None
    text_seen: dict[str, int] = field(default_factory=dict)


class PlateTracker:
    """Selects one best plate per track and emits it at most once per visit.

    Follows the same gate + stale-eviction philosophy as the alert engine:
    the same normalized plate must be confirmed ``min_confirmations`` times
    (here: across the sampled frames) before it is trusted, and the chosen
    reading is the highest-confidence raw read for that track. Afterward
    the per-track gate blocks repeats until the track leaves view long
    enough to be forgotten (gate re-arms).
    """

    def __init__(
        self,
        min_confirmations: int = 2,
        stale_frames: int = 75,
    ) -> None:
        self._min_confirmations = max(1, int(min_confirmations))
        self._stale_frames = max(5, int(stale_frames))
        self._states: dict[int, _TrackPlates] = {}

    def submit(self, reading: PlateReading, frame_number: int) -> PlateReading | None:
        """Feed one read in; returns the promoted reading, or ``None``."""
        state = self._states.get(reading.track_id)
        if state is None:
            state = self._states[reading.track_id] = _TrackPlates()
        state.last_seen_frame = frame_number

        promoted: PlateReading | None = None
        if not state.emitted:
            state.text_seen[reading.plate_text] = (
                state.text_seen.get(reading.plate_text, 0) + 1
            )
            if state.best is None or reading.confidence > state.best.confidence:
                state.best = reading
            if (
                state.text_seen[reading.plate_text]
                >= self._min_confirmations
            ):
                state.emitted = True
                promoted = state.best

        self.tick(frame_number)
        return promoted

    def tick(self, frame_number: int) -> None:
        """Advance time by one frame.

        Call this every processed frame (even without reads) so tracks that
        simply left the scene are forgotten and their per-visit gate
        re-arms; without it a vanished track would emit forever.
        """
        for track_id in list(self._states):
            if frame_number - self._states[track_id].last_seen_frame > self._stale_frames:
                del self._states[track_id]

    def is_emitted(self, track_id: int) -> bool:
        state = self._states.get(track_id)
        return bool(state is not None and state.emitted)

    def clear(self) -> None:
        self._states.clear()


# ---------------------------------------------------------------- pipeline


@dataclass(slots=True)
class _PlateJob:
    crop: np.ndarray
    vehicle_bbox: tuple[int, int, int, int]
    track_id: int
    class_name: str
    frame_number: int


class AnprPipeline:
    """Background-thread ANPR worker with a bounded input queue.

    Shape mirrors :class:`~channels.WebhookChannel`: ``start()`` boots the
    worker, ``process()`` enqueues a job non-blocking, ``drain()`` harvests
    finished :class:`PlateReading` results, ``close()`` shuts the worker
    down after a grace window. OCR can never block the detection loop; a
    full input queue simply drops the job (logged) instead of slowing live
    analysis.
    """

    def __init__(
        self,
        detector: PlateDetector,
        reader: PlateReader,
        *,
        evidence_dir: Path,
        queue_size: int = 8,
        logger: Logger | None = None,
    ) -> None:
        self._detector = detector
        self._reader = reader
        self._evidence_dir = Path(evidence_dir)
        self._queue: Queue[_PlateJob] = Queue(maxsize=max(1, int(queue_size)))
        self._results: Queue[PlateReading] = Queue()
        self._log = (logger or logging.getLogger("ibvap")).getChild("anpr")
        self._thread = threading.Thread(
            target=self._worker, name="ibvap-anpr", daemon=True
        )
        self._running = False
        self._dropped = 0

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        if not self._reader.ensure_loaded():
            self._log.warning(
                "Starting ANPR pipeline without a usable OCR engine; "
                "only plate detection will run."
            )
        self._running = True
        self._thread.start()
        self._log.info(
            "ANPR pipeline started (queue_size=%d)", self._queue.maxsize
        )

    def process(
        self,
        crop: np.ndarray,
        *,
        track_id: int,
        class_name: str,
        frame_number: int,
        vehicle_bbox: tuple[int, int, int, int],
    ) -> bool:
        """Enqueue an OCR job for one vehicle track (non-blocking)."""
        job = _PlateJob(
            crop=crop,
            vehicle_bbox=vehicle_bbox,
            track_id=track_id,
            class_name=class_name,
            frame_number=frame_number,
        )
        try:
            self._queue.put_nowait(job)
            return True
        except Full:
            self._dropped += 1
            if self._dropped <= 5:
                self._log.warning(
                    "ANPR queue full; dropping plate job for track %d "
                    "(protection for the live detection loop)", track_id,
                )
            return False

    def drain(self) -> list[PlateReading]:
        readings: list[PlateReading] = []
        while True:
            try:
                readings.append(self._results.get_nowait())
            except Empty:
                break
        return readings

    def close(self) -> None:
        if not self._running:
            return
        self._running = False
        self._thread.join(timeout=30.0)
        if self._thread.is_alive():
            self._log.warning("ANPR worker did not stop within grace period")
        remaining = self._queue.qsize()
        if remaining:
            self._log.debug("Dropping %d queued plate jobs on shutdown", remaining)
        self._detector.close()

    # ------------------------------------------------------------- internals
    def _worker(self) -> None:
        while self._running or not self._queue.empty():
            try:
                job = self._queue.get(timeout=0.25)
            except Empty:
                continue
            try:
                reading = self._analyze(job)
                if reading is not None:
                    self._results.put(reading)
            except Exception:
                self._log.exception("ANPR worker failed on track %d", job.track_id)
            finally:
                self._queue.task_done()

    def _analyze(self, job: _PlateJob) -> PlateReading | None:
        crop = job.crop
        if crop is None or crop.size == 0:
            return None

        # OCR is the expensive stage, so the first candidate that yields a
        # validated read wins and later candidates are skipped for this job.
        for candidate in self._detector.detect(crop):
            cx1 = max(candidate.x1, 0)
            cy1 = max(candidate.y1, 0)
            cx2 = min(candidate.x2, crop.shape[1])
            cy2 = min(candidate.y2, crop.shape[0])
            if cx2 - cx1 < 8 or cy2 - cy1 < 4:
                continue
            prepared = self._reader.preprocess(crop[cy1:cy2, cx1:cx2])
            read = self._reader.read_plate(prepared)
            if read is None:
                continue
            text, confidence = read
            crop_path = self._save_evidence(job, prepared)
            frame_bbox = self._crop_rect_to_frame(
                job.vehicle_bbox, (cx1, cy1, cx2, cy2)
            )
            return PlateReading(
                plate_text=text,
                confidence=confidence,
                track_id=job.track_id,
                class_name=job.class_name,
                frame_number=job.frame_number,
                bbox=frame_bbox,
                crop_path=crop_path,
            )

        # --- Fallback: OCR on the lower 40% of the vehicle crop ---
        # When the plate detector finds nothing (common on distant or
        # low-contrast vehicles), the plate is most likely in the lower
        # portion of the vehicle bounding box.
        crop_h, crop_w = crop.shape[:2]
        if crop_h > 20 and crop_w > 20:
            lower_y = int(crop_h * 0.6)
            lower_crop = crop[lower_y:, :]
            if lower_crop.size > 0:
                prepared = self._reader.preprocess(lower_crop)
                read = self._reader.read_plate(prepared)
                if read is not None:
                    text, confidence = read
                    crop_path = self._save_evidence(job, prepared)
                    frame_bbox = self._crop_rect_to_frame(
                        job.vehicle_bbox, (0, lower_y, crop_w, crop_h)
                    )
                    return PlateReading(
                        plate_text=text,
                        confidence=confidence,
                        track_id=job.track_id,
                        class_name=job.class_name,
                        frame_number=job.frame_number,
                        bbox=frame_bbox,
                        crop_path=crop_path,
                    )
        return None

    def _save_evidence(self, job: _PlateJob, image: np.ndarray) -> str | None:
        try:
            self._evidence_dir.mkdir(parents=True, exist_ok=True)
            filename = f"PLT-{job.track_id}-{job.frame_number:04d}.jpg"
            path = self._evidence_dir / filename
            cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return str(path)
        except OSError:
            self._log.exception("Could not save plate crop evidence")
            return None

    @staticmethod
    def _crop_rect_to_frame(
        vehicle_bbox: tuple[int, int, int, int],
        crop_rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        """Map a plate rect in crop space onto the full-frame coordinates."""
        vx1, vy1, _, _ = vehicle_bbox
        cx1, cy1, cx2, cy2 = crop_rect
        return (vx1 + cx1, vy1 + cy1, vx1 + cx2, vy1 + cy2)