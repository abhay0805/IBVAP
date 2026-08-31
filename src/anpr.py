"""Automatic Number Plate Recognition (ANPR) for the IBVAP platform.

Layered design with non-blocking async architecture:
- :class:`PlateDetector` (:class:`YoloPlateDetector`, :class:`ClassicalCVPlateDetector`)
- :class:`PlateReader` (EasyOCR wrapper with CLAHE, bilateral filter, deskew, and Indian/Euro grammar validation)
- :class:`PlateTracker` (Majority-voting and dedup per tracked vehicle)
- :class:`AnprPipeline` (Dedicated background queue so OCR never stalls live object tracking)
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Sequence

import cv2
import numpy as np

from database import get_vehicle_by_plate, initialize_database
from models import PlateReading

Logger = logging.Logger
LOG = logging.getLogger("ibvap.anpr")

# COCO classes that can carry a readable number plate.
VEHICLE_CLASSES: frozenset[str] = frozenset({"car", "truck", "bus", "motorbike"})

_INDIAN_PLATE_PATTERN = r"^[A-Z]{2}[0-9]{2}[A-Z]{0,2}[0-9]{4}$"
_EURO_PLATE_PATTERN = r"^[A-Z]{1,3}[0-9]{3,5}[A-Z]{1,3}$"
_GENERAL_PLATE_PATTERN = r"^[A-Z0-9]{4,10}$"

# OCR confusion: a digit rendered where a letter is expected.
_DIGIT_AS_LETTER = {
    "0": "O", "1": "I", "8": "B", "5": "S", "2": "Z", "6": "G",
}
# OCR confusion: a letter rendered where a digit is expected.
_LETTER_AS_DIGIT = {
    "O": "0", "I": "1", "L": "1", "B": "8", "S": "5", "Z": "2", "G": "6", "Q": "0",
    "D": "0", "J": "1", "T": "7",
}

_PLATE_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean_plate_text(raw: str) -> str:
    """Remove whitespace and special characters, returning uppercase alphanumeric string."""
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()


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
    if re.fullmatch(_INDIAN_PLATE_PATTERN, candidate):
        return candidate
    return None


def _normalize_euro_plate(cleaned: str) -> str | None:
    """Normalize European/Standard formats like AA3325MM or AI7060EC."""
    if 5 <= len(cleaned) <= 10:
        if re.fullmatch(_EURO_PLATE_PATTERN, cleaned):
            return cleaned
        num_letters = sum(1 for c in cleaned if c.isalpha())
        num_digits = sum(1 for c in cleaned if c.isdigit())
        if num_letters >= 2 and num_digits >= 2 and re.fullmatch(_GENERAL_PLATE_PATTERN, cleaned):
            return cleaned
    return None


def normalize_plate_text(raw: str) -> str | None:
    """Validate and clean an OCR string into a canonical plate.

    Supports Indian plate grammar (with confusion slot fixing) and
    International/European plate formats (e.g. AA3325MM, AI7060EC, WJMRU).
    """
    if not raw:
        return None
    cleaned = clean_plate_text(raw)
    if not cleaned or len(cleaned) < 4 or len(cleaned) > 10:
        return None

    indian = _normalize_indian_plate(cleaned)
    if indian is not None:
        return indian

    euro = _normalize_euro_plate(cleaned)
    if euro is not None:
        return euro

    if len(cleaned) >= 4 and re.fullmatch(_GENERAL_PLATE_PATTERN, cleaned):
        return cleaned

    return None


def normalize_plate_number(raw_text: str) -> str:
    """Alias for backwards compatibility."""
    return clean_plate_text(raw_text)


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

    Grayscale -> Gaussian blur -> Canny edges -> contours -> aspect/size filtering -> NMS.
    A second pass uses morphological closing + adaptive thresholding.
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

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours_canny, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        candidates = self._filter_contours(contours_canny, crop_w, crop_h)

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
        pass


class YoloPlateDetector(PlateDetector):
    """High-accuracy YOLO-based license plate detector."""

    def __init__(self, model_path: Path | str, confidence: float = 0.30) -> None:
        self.model_path = Path(model_path)
        self.confidence = confidence
        self._model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        from ultralytics import YOLO
        LOG.info("Loading YOLO plate detector model: %s", self.model_path)
        self._model = YOLO(str(self.model_path))

    def detect(self, crop: np.ndarray) -> list[PlateCandidate]:
        if crop is None or crop.size == 0 or self._model is None:
            return []
        try:
            results = self._model.predict(crop, conf=self.confidence, verbose=False)
            if not results or results[0].boxes is None:
                return []
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            candidates = []
            for box, conf in zip(boxes, confs):
                x1, y1, x2, y2 = map(int, box)
                candidates.append(PlateCandidate(x1, y1, x2, y2, score=float(conf)))
            return candidates
        except Exception as e:
            LOG.warning("YOLO plate detection failed on crop: %s", e)
            return []

    def close(self) -> None:
        self._model = None


def create_plate_detector(
    model_path: Path | str | None = None, confidence: float = 0.30
) -> PlateDetector:
    """Factory for plate detectors.

    ``model_path=None`` returns ClassicalCVPlateDetector.
    If a valid path is passed, returns YoloPlateDetector or raises NotImplementedError if file is missing.
    """
    if model_path is None:
        return ClassicalCVPlateDetector()

    p = Path(model_path)
    if p.exists():
        try:
            return YoloPlateDetector(p, confidence=confidence)
        except Exception as e:
            LOG.warning("Failed to initialize YOLO plate detector from %s: %s", p, e)
            return ClassicalCVPlateDetector()

    raise NotImplementedError(f"Model-backed plate detector weights not found: {model_path}")


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
    """EasyOCR wrapper: preprocess, recognize and validate a plate crop."""

    ALLOWLIST = _PLATE_CHARS

    def __init__(
        self,
        *,
        min_confidence: float = 0.35,
        gpu: bool = False,
        logger: Logger | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._gpu = gpu
        self._log = (logger or logging.getLogger("ibvap")).getChild("anpr")
        self._reader: Any = None
        self._init_error: Exception | None = None
        self._warned_unavailable = False
        self._clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))

    @property
    def unavailable(self) -> bool:
        return self._init_error is not None

    def ensure_loaded(self, quiet: bool = False) -> bool:
        if self._reader is not None:
            return True
        if self._init_error is not None:
            return False
        try:
            import easyocr

            self._reader = easyocr.Reader(["en"], gpu=self._gpu, verbose=False)
            self._log.info("EasyOCR recognition engine loaded")
            return True
        except Exception as exc:
            self._init_error = exc
            if not self._warned_unavailable:
                self._log.error("EasyOCR unavailable (%s); ANPR OCR disabled", exc)
                self._warned_unavailable = True
            elif not quiet:
                self._log.debug("EasyOCR still unavailable: %s", exc)
            return False

    def preprocess(self, plate_bgr: np.ndarray) -> np.ndarray:
        """Fast upscale + CLAHE contrast enhancement + Bilateral filtering."""
        if plate_bgr is None or plate_bgr.size == 0:
            return plate_bgr
        h, w = plate_bgr.shape[:2]
        if h == 0 or w == 0:
            return plate_bgr

        scale = max(3.0, 120.0 / float(h))
        resized = cv2.resize(plate_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if resized.ndim == 3 else resized.copy()
        enhanced = self._clahe.apply(gray)
        filtered = cv2.bilateralFilter(enhanced, 11, 17, 17)
        return cv2.cvtColor(filtered, cv2.COLOR_GRAY2BGR)

    def read_plate(self, plate_image: np.ndarray) -> tuple[str, float] | None:
        """Fast OCR on preprocessed plate image."""
        if not self.ensure_loaded():
            return None
        assert self._reader is not None

        prep = self.preprocess(plate_image)
        try:
            results = self._reader.readtext(
                prep,
                allowlist=self.ALLOWLIST,
                detail=1,
                paragraph=False,
            )
        except Exception as e:
            self._log.debug("EasyOCR readtext error: %s", e)
            return None

        best: tuple[str, float] | None = None
        for _, ocr_text, confidence in results:
            text = clean_plate_text(ocr_text)
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
    latest_reading: PlateReading | None = None


class PlateTracker:
    """Selects one best plate per vehicle track and locks it with majority voting."""

    def __init__(
        self,
        min_confirmations: int = 2,
        stale_frames: int = 75,
    ) -> None:
        self._min_confirmations = max(1, int(min_confirmations))
        self._stale_frames = max(5, int(stale_frames))
        self._states: dict[int, _TrackPlates] = {}

    def submit(self, reading: PlateReading, frame_number: int) -> PlateReading | None:
        state = self._states.get(reading.track_id)
        if state is None:
            state = self._states[reading.track_id] = _TrackPlates()
        state.last_seen_frame = frame_number
        state.latest_reading = reading

        promoted: PlateReading | None = None
        if not state.emitted:
            state.text_seen[reading.plate_text] = (
                state.text_seen.get(reading.plate_text, 0) + 1
            )
            if state.best is None or reading.confidence > state.best.confidence:
                state.best = reading

            if state.text_seen[reading.plate_text] >= self._min_confirmations:
                state.emitted = True
                promoted = state.best

        self.tick(frame_number)
        return promoted

    def tick(self, frame_number: int) -> None:
        for track_id in list(self._states):
            if frame_number - self._states[track_id].last_seen_frame > self._stale_frames:
                del self._states[track_id]

    def get_track_plate(self, track_id: int) -> tuple[str | None, float, bool]:
        """Returns (best_text, confidence, is_locked)."""
        state = self._states.get(track_id)
        if not state:
            return None, 0.0, False
        if state.best is not None:
            return state.best.plate_text, state.best.confidence, state.emitted
        return None, 0.0, False

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
    """Non-blocking background thread ANPR worker queue."""

    def __init__(
        self,
        detector: PlateDetector,
        reader: PlateReader,
        *,
        evidence_dir: Path | str = "output/evidence",
        queue_size: int = 16,
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

    def start(self) -> None:
        self._reader.ensure_loaded(quiet=True)
        self._running = True
        self._thread.start()
        self._log.info("ANPR background pipeline started (queue_size=%d)", self._queue.maxsize)

    def process(
        self,
        crop: np.ndarray,
        *,
        track_id: int,
        class_name: str,
        frame_number: int,
        vehicle_bbox: tuple[int, int, int, int],
    ) -> bool:
        """Enqueue an OCR job for a vehicle track non-blockingly."""
        if crop is None or crop.size == 0:
            return False
        job = _PlateJob(
            crop=crop.copy(),
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
                self._log.warning("ANPR queue full; dropped frame job for track %d", track_id)
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
        try:
            self._queue.join()
        except Exception:
            pass
        self._running = False
        self._thread.join(timeout=10.0)
        self._detector.close()

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

        candidates = self._detector.detect(crop)
        for candidate in candidates:
            cx1 = max(candidate.x1, 0)
            cy1 = max(candidate.y1, 0)
            cx2 = min(candidate.x2, crop.shape[1])
            cy2 = min(candidate.y2, crop.shape[0])
            if cx2 - cx1 < 8 or cy2 - cy1 < 4:
                continue
            plate_crop = crop[cy1:cy2, cx1:cx2]
            read = self._reader.read_plate(plate_crop)
            if read is None:
                continue
            text, confidence = read
            crop_path = self._save_evidence(job, plate_crop)
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

        # Fallback: test direct OCR if crop itself is already a cropped plate
        read = self._reader.read_plate(crop)
        if read is not None:
            text, confidence = read
            crop_path = self._save_evidence(job, crop)
            return PlateReading(
                plate_text=text,
                confidence=confidence,
                track_id=job.track_id,
                class_name=job.class_name,
                frame_number=job.frame_number,
                bbox=job.vehicle_bbox,
                crop_path=crop_path,
            )

        # Fallback: scan lower 50% of vehicle crop
        crop_h, crop_w = crop.shape[:2]
        if crop_h > 20 and crop_w > 20:
            lower_y = int(crop_h * 0.5)
            lower_crop = crop[lower_y:, :]
            if lower_crop.size > 0:
                prepared = self._reader.preprocess(lower_crop)
                read = self._reader.read_plate(prepared)
                if read is not None:
                    text, confidence = read
                    crop_path = self._save_evidence(job, lower_crop)
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
            return None

    @staticmethod
    def _crop_rect_to_frame(
        vehicle_bbox: tuple[int, int, int, int],
        crop_rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        vx1, vy1, _, _ = vehicle_bbox
        cx1, cy1, cx2, cy2 = crop_rect
        return (vx1 + cx1, vy1 + cy1, vx1 + cx2, vy1 + cy2)


# ------------------------------------------------------------- legacy helpers


_legacy_detector: PlateDetector | None = None
_legacy_reader: PlateReader | None = None


def get_ocr_reader() -> PlateReader:
    global _legacy_reader
    if _legacy_reader is None:
        _legacy_reader = PlateReader()
    return _legacy_reader


def preprocess_plate_image(plate_img: np.ndarray) -> np.ndarray | None:
    if plate_img is None or plate_img.size == 0:
        return None
    reader = get_ocr_reader()
    return reader.preprocess(plate_img)


def detect_license_plate_roi(vehicle_img: np.ndarray) -> tuple[np.ndarray | None, tuple[int, int, int, int] | None]:
    global _legacy_detector
    if _legacy_detector is None:
        _legacy_detector = create_plate_detector(None)
    if vehicle_img is None or vehicle_img.size == 0:
        return None, None
    candidates = _legacy_detector.detect(vehicle_img)
    if candidates:
        best = candidates[0]
        crop = vehicle_img[best.y1:best.y2, best.x1:best.x2]
        return crop, (best.x1, best.y1, best.width, best.height)
    h, w = vehicle_img.shape[:2]
    lower = vehicle_img[int(h * 0.5):h, 0:w]
    return lower, (0, int(h * 0.5), w, int(h * 0.5))


def recognize_plate(image: np.ndarray) -> dict[str, Any]:
    """Synchronous ANPR lookup for a single vehicle crop."""
    reader = get_ocr_reader()
    crop, bbox = detect_license_plate_roi(image)
    if crop is None or crop.size == 0:
        crop = image

    prep = reader.preprocess(crop)
    res = reader.read_plate(prep)
    if res is None:
        res = reader.read_plate(crop)

    if res is None:
        return {
            "raw_text": "",
            "normalized_plate": "",
            "status": "UNKNOWN",
            "vehicle_info": None,
            "confidence": 0.0,
        }

    norm_text, conf = res
    vinfo = get_vehicle_by_plate(norm_text)
    status = vinfo.get("status", "UNKNOWN") if vinfo else "UNKNOWN"

    return {
        "raw_text": norm_text,
        "normalized_plate": norm_text,
        "status": status,
        "vehicle_info": vinfo,
        "confidence": conf,
    }
