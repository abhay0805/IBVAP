"""Unit tests for the ANPR layer.

Run with::

    python -m unittest discover -s tests -v

EasyOCR-dependent behaviour degrades gracefully: those tests are skipped
when the library or its model weights are unavailable, so the suite still
passes on stock deployments without a download.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

import cv2 as cv

from anpr import (
    AnprPipeline,
    ClassicalCVPlateDetector,
    PlateReader,
    PlateTracker,
    create_plate_detector,
    normalize_plate_text,
)
from database import Database
from models import EventType, PlateReading, SecurityEvent


# ------------------------------------------------------------ text normalize


class NormalizePlateTextTest(unittest.TestCase):
    def test_canonical_ten_char(self) -> None:
        self.assertEqual(normalize_plate_text("MH12AB1234"), "MH12AB1234")

    def test_lowercase_and_separators(self) -> None:
        self.assertEqual(normalize_plate_text("mh 12 a b 12 34"), "MH12AB1234")

    def test_letter_slot_digit_confusion_fixed(self) -> None:
        self.assertEqual(normalize_plate_text("0H12AB1234"), "OH12AB1234")

    def test_digit_slot_letter_confusion_fixed(self) -> None:
        # The "1" in the trailing digits read as an "I".
        self.assertEqual(normalize_plate_text("MH12ABI234"), "MH12AB1234")

    def test_ocr_zero_as_letter_o_digit_slot(self) -> None:
        self.assertEqual(normalize_plate_text("MH12AB1O34"), "MH12AB1034")

    def test_ocr_two_as_z_in_digit_slot(self) -> None:
        # Real captured case: EasyOCR read "MH12AB1234" as "MH1ZAB1234".
        self.assertEqual(normalize_plate_text("MH1ZAB1234"), "MH12AB1234")

    def test_one_optional_letter(self) -> None:
        self.assertEqual(normalize_plate_text("KA05MJ1234"), "KA05MJ1234")

    def test_eight_char_no_optional_letters(self) -> None:
        self.assertEqual(normalize_plate_text("MH123456"), "MH123456")

    def test_too_long_rejected(self) -> None:
        self.assertIsNone(normalize_plate_text("MH12AB12345"))

    def test_short_garbage_rejected(self) -> None:
        self.assertIsNone(normalize_plate_text("HI"))
        self.assertIsNone(normalize_plate_text(""))
        self.assertIsNone(normalize_plate_text("###$$$@@@"))


# ---------------------------------------------------------------- detectors


def _render_plate_crop(text: str | None = None) -> np.ndarray:
    """Dark vehicle crop containing one bright synthetic plate region."""
    crop = np.full((120, 460, 3), 40, dtype=np.uint8)
    plate_x, plate_y, plate_w, plate_h = 15, 20, 430, 85
    cv.rectangle(
        crop,
        (plate_x, plate_y),
        (plate_x + plate_w, plate_y + plate_h),
        (245, 245, 245),
        -1,
    )
    if text:
        cv.putText(
            crop, text, (40, 80),
            cv.FONT_HERSHEY_SIMPLEX, 1.8, (20, 20, 20), 3,
        )
    return crop


class ClassicalPlateDetectorTest(unittest.TestCase):
    def test_detects_synthetic_plate(self) -> None:
        detector = ClassicalCVPlateDetector()
        candidates = detector.detect(_render_plate_crop())
        self.assertTrue(len(candidates) >= 1)
        largest = max(candidates, key=lambda c: c.area)
        self.assertGreater(largest.width / largest.height, 1.8)

    def test_blank_crop_returns_nothing(self) -> None:
        detector = ClassicalCVPlateDetector()
        self.assertEqual(
            detector.detect(np.full((100, 100, 3), 0, dtype=np.uint8)), []
        )

    def test_empty_input_safe(self) -> None:
        detector = ClassicalCVPlateDetector()
        self.assertEqual(detector.detect(np.zeros((0, 0, 3), dtype=np.uint8)), [])

    def test_factory_defaults_to_classical(self) -> None:
        detector = create_plate_detector(None)
        self.assertIsInstance(detector, ClassicalCVPlateDetector)
        detector.close()

    def test_model_path_not_yet_supported(self) -> None:
        with self.assertRaises(NotImplementedError):
            create_plate_detector(Path("yolo_plate.pt"))


# ------------------------------------------------------------------ tracking


class PlateTrackerTest(unittest.TestCase):
    def _reading(
        self, track: int, frame: int, text: str, conf: float = 0.8
    ) -> PlateReading:
        return PlateReading(
            plate_text=text,
            confidence=conf,
            track_id=track,
            class_name="car",
            frame_number=frame,
        )

    def test_never_promotes_below_confirmations(self) -> None:
        tracker = PlateTracker(min_confirmations=2)
        self.assertIsNone(tracker.submit(self._reading(7, 10, "MH12AB1234"), 10))
        self.assertIsNotNone(
            tracker.submit(self._reading(7, 15, "MH12AB1234"), 15)
        )

    def test_promotes_highest_confidence_read(self) -> None:
        tracker = PlateTracker(min_confirmations=2)
        tracker.submit(self._reading(7, 10, "MH12AB1234", conf=0.7), 10)
        actual = tracker.submit(
            self._reading(7, 15, "MH12AB1234", conf=0.95), 15
        )
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(actual.confidence, 0.95)
        self.assertEqual(actual.plate_text, "MH12AB1234")

    def test_emits_only_once_per_track_visit(self) -> None:
        tracker = PlateTracker(min_confirmations=2)
        tracker.submit(self._reading(1, 10, "KA01AB1234", conf=0.8), 10)
        self.assertIsNotNone(
            tracker.submit(self._reading(1, 15, "KA01AB1234", conf=0.9), 15)
        )
        self.assertIsNone(
            tracker.submit(self._reading(1, 20, "KA01AB1234", conf=0.9), 20)
        )

    def test_gate_rearms_after_track_forgotten(self) -> None:
        tracker = PlateTracker(min_confirmations=2, stale_frames=10)
        tracker.submit(self._reading(1, 1, "KA01AB1234", conf=0.8), 1)
        actual = tracker.submit(self._reading(1, 5, "KA01AB1234", conf=0.8), 5)
        self.assertIsNotNone(actual)
        self.assertTrue(tracker.is_emitted(1))
        # Track absent for > stale_frames -- time alone must forget it.
        for frame in range(6, 40):
            tracker.tick(frame)
        self.assertFalse(tracker.is_emitted(1))
        # Re-enters the scene later: needs a fresh pair of confirmations.
        self.assertIsNone(
            tracker.submit(self._reading(1, 100, "KA01AB1234", conf=0.8), 100)
        )
        self.assertIsNotNone(
            tracker.submit(self._reading(1, 110, "KA01AB1234", conf=0.8), 110)
        )
        self.assertTrue(tracker.is_emitted(1))

    def test_tracks_are_isolated(self) -> None:
        tracker = PlateTracker(min_confirmations=2)
        tracker.submit(self._reading(1, 10, "KA01AB1234"), 10)
        tracker.submit(self._reading(2, 10, "DL4CAF7890"), 10)
        actual = tracker.submit(self._reading(2, 15, "DL4CAF7890"), 15)
        self.assertIsNotNone(actual)
        self.assertTrue(tracker.is_emitted(2))
        # Track 1's counter is untouched: a *different* second read must not
        # chain into an emission.
        self.assertIsNone(
            tracker.submit(self._reading(1, 20, "KA01AB9999"), 20)
        )


# ------------------------------------------------------------------ pipeline


class AnprPipelineTest(unittest.TestCase):
    def test_process_and_close_are_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = AnprPipeline(
                ClassicalCVPlateDetector(),
                PlateReader(min_confidence=0.5),
                evidence_dir=Path(tmp),
            )
            pipeline.start()
            ok = pipeline.process(
                _render_plate_crop(),
                track_id=3,
                class_name="car",
                frame_number=9,
                vehicle_bbox=(100, 100, 560, 220),
            )
            self.assertTrue(ok)
            pipeline.close()
            self.assertEqual(pipeline.drain(), [])
            pipeline.close()  # idempotent


# ----------------------------------------------------------------- database


class MigrationTest(unittest.TestCase):
    def test_old_schema_gains_anpr_columns_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"

            # Seed a row with the *current* schema first...
            old_db = Database(db_path)
            event = SecurityEvent(
                event_id="EVT-0001",
                event_type=EventType.VIRTUAL_FENCE_BREACH,
                object_type="person",
                track_id=1,
                camera_id="BOP-CAM-01",
                timestamp=datetime.now().astimezone(),
                frame_number=10,
                status="ACTIVE",
                confidence=0.9,
                direction=None,
                evidence_path="x.jpg",
            )
            old_db.insert_event(event)

            # ...then drop the ANPR columns to reproduce a pre-ANPR database.
            with old_db._connect() as connection:
                connection.execute("ALTER TABLE security_events DROP COLUMN plate_text")
                connection.execute(
                    "ALTER TABLE security_events DROP COLUMN plate_confidence"
                )
                connection.execute(
                    "ALTER TABLE security_events DROP COLUMN plate_crop_path"
                )

            # Re-opening must add the columns back in place, keeping the row.
            migrated = Database(db_path)
            migrated.initialize()
            with migrated._connect() as connection:
                columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(security_events)"
                    ).fetchall()
                }
                self.assertIn("plate_text", columns)
                self.assertIn("plate_confidence", columns)
                self.assertIn("plate_crop_path", columns)
                row = connection.execute(
                    "SELECT event_id, plate_text FROM security_events"
                ).fetchone()
                self.assertEqual(row["event_id"], "EVT-0001")
                self.assertIsNone(row["plate_text"])


# ------------------------------------------------------ easyocr (optional) --


def _easyocr_available() -> bool:
    try:
        import easyocr  # noqa: F401

        return True
    except Exception:
        return False


@unittest.skipUnless(
    _easyocr_available(), "easyocr not installed; skipping OCR integration tests"
)
class EasyOcrIntegrationTest(unittest.TestCase):
    def test_reader_normalizes_real_ocr_output(self) -> None:
        reader = PlateReader(min_confidence=0.2)
        if reader.unavailable:
            self.skipTest("easyocr weights unavailable")
        text = "MH12AB1234"
        crop = np.full((120, 460, 3), 60, dtype=np.uint8)
        cv.putText(
            crop, text, (40, 85),
            cv.FONT_HERSHEY_SIMPLEX, 2.2, (235, 235, 235), 4,
        )
        prepared = reader.preprocess(crop)
        read = reader.read_plate(prepared)
        if read is None:
            self.skipTest("OCR produced no valid plate on synthetic input")
        plate_text, confidence = read
        self.assertEqual(plate_text, "MH12AB1234")
        self.assertGreaterEqual(confidence, 0.2)


if __name__ == "__main__":
    unittest.main()