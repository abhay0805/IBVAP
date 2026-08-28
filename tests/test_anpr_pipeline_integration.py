"""End-to-end ANPR data-path integration tests.

These drive the *real* worker pipeline (:class:`AnprPipeline` running the
classical detector + EasyOCR), the per-track :class:`PlateTracker`, and the
actual persistence/dispatch helpers used by ``src/detect.py`` against a
temporary filesystem -- proving a validated plate read lands, exactly as it
does in a live run, as:

* a ``SecurityEvent`` (``PLATE_READ``) with plate fields in ``events.json``,
* a ``SecurityAlert`` in ``alerts.json``,
* a row in the SQLite database with ``plate_text`` populated,
* a plate-crop evidence JPEG under the evidence directory.

Run with::

    python -m unittest tests.test_anpr_pipeline_integration -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cv2 as cv

import numpy as np

from anpr import (
    AnprPipeline,
    ClassicalCVPlateDetector,
    PlateReader,
    PlateTracker,
)
from channels import JsonChannel
from database import Database
from detect import build_plate_alert, build_plate_event, persist_event, send_alert


def _big_plate_crop() -> np.ndarray:
    """A large, legible synthetic plate inside a dark vehicle crop."""
    crop = np.full((260, 1100, 3), 30, dtype=np.uint8)
    plate_w, plate_h = 980, 220
    px0, py0 = 40, 20
    cv.rectangle(crop, (px0, py0), (px0 + plate_w, py0 + plate_h), (248, 248, 248), -1)
    cv.putText(
        crop, "MH12AB1234", (px0 + 70, py0 + 170),
        cv.FONT_HERSHEY_SIMPLEX, 3.2, (10, 10, 10), 6, cv.LINE_AA,
    )
    return crop


@unittest.skipIf(
    not (lambda: __import__("importlib.util").util.find_spec("easyocr"))(),
    "easyocr not installed; skipping ANPR data-path integration",
)
class AnprDataPathIntegrationTest(unittest.TestCase):
    def test_read_flows_to_json_database_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            db = Database(root / "ibvap.db")
            db.initialize()

            events_json = JsonChannel(root / "events.json")
            alerts_json = JsonChannel(root / "alerts.json")

            pipeline = AnprPipeline(
                ClassicalCVPlateDetector(),
                PlateReader(min_confidence=0.4),
                evidence_dir=evidence,
            )
            pipeline.start()
            crop = _big_plate_crop()
            self.assertTrue(
                pipeline.process(
                    crop, track_id=9, class_name="truck",
                    frame_number=12, vehicle_bbox=(200, 150, 1300, 410),
                )
            )
            pipeline.close()

            readings = pipeline.drain()
            self.assertTrue(readings, "worker should have produced a reading")

            tracker = PlateTracker(min_confirmations=1)
            promoted = None
            for reading in readings:
                candidate = tracker.submit(reading, reading.frame_number)
                if candidate is not None:
                    promoted = candidate
            self.assertIsNotNone(promoted, "consistent read should promote")
            self.assertEqual(promoted.plate_text, "MH12AB1234")
            self.assertGreaterEqual(promoted.confidence, 0.4)

            stamp = datetime.now().astimezone()
            event = build_plate_event(
                promoted,
                camera_id="BOP-CAM-01",
                status="ACTIVE",
                event_id="PLT-0001",
                stamp=stamp,
            )
            events_total = persist_event(db, events_json, event)

            alert = build_plate_alert(event, promoted, alert_id="PLA-0001")
            alerts_total = send_alert([alerts_json], db, alert)
            events_json.close()
            alerts_json.close()

            self.assertEqual((events_total, alerts_total), (1, 1))

            # events.json holds the plate fields
            import json

            with (root / "events.json").open(encoding="utf-8") as fh:
                persisted_events = json.load(fh)
            self.assertEqual(persisted_events[0]["event_id"], "PLT-0001")
            self.assertEqual(persisted_events[0]["plate_text"], "MH12AB1234")
            self.assertEqual(
                persisted_events[0]["plate_confidence"], round(promoted.confidence, 3)
            )

            # alerts.json holds the notification payload
            with (root / "alerts.json").open(encoding="utf-8") as fh:
                persisted_alerts = json.load(fh)
            self.assertEqual(persisted_alerts[0]["alert_id"], "PLA-0001")
            self.assertIn("Plate MH12AB1234", persisted_alerts[0]["message"])
            self.assertEqual(persisted_alerts[0]["event_id"], "PLT-0001")

            # database row carries plate data
            with db._connect() as connection:
                row = connection.execute(
                    "SELECT event_id, plate_text, plate_confidence, plate_crop_path "
                    "FROM security_events WHERE event_id='PLT-0001'"
                ).fetchone()
            self.assertEqual(row["plate_text"], "MH12AB1234")
            self.assertAlmostEqual(row["plate_confidence"], promoted.confidence, places=2)
            self.assertTrue(Path(row["plate_crop_path"]).exists())

            # evidence crop written next to the regular evidence files
            self.assertTrue(
                evidence.joinpath(f"PLT-{promoted.track_id}-{promoted.frame_number:04d}.jpg").exists()
            )


if __name__ == "__main__":
    unittest.main()