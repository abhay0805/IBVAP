"""Unit tests for the alert engine and data models.

Run with::

    python -m unittest discover -s tests -v

Uses only the standard library so the test suite runs on any deployment
including offline border posts.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alerts import AlertEngine, Fence, default_severity
from models import CrossingDirection, Detection, EventType, Severity


def make_detection(
    track_id: int,
    frame: int,
    x1: int = 100,
    y1: int = 100,
    x2: int = 300,
    y2: int = 400,
    class_name: str = "person",
    confidence: float = 0.9,
) -> Detection:
    return Detection(
        track_id=track_id,
        class_id=0,
        class_name=class_name,
        confidence=confidence,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        frame_number=frame,
    )


class FenceTests(unittest.TestCase):
    def test_inbound_crossing(self) -> None:
        fence = Fence(700)
        self.assertEqual(
            fence.crossing(600, 800), CrossingDirection.INBOUND
        )

    def test_outbound_crossing(self) -> None:
        fence = Fence(700)
        self.assertEqual(
            fence.crossing(800, 600), CrossingDirection.OUTBOUND
        )

    def test_no_crossing_when_staying_on_one_side(self) -> None:
        fence = Fence(700)
        self.assertIsNone(fence.crossing(300, 500))
        self.assertIsNone(fence.crossing(800, 900))

    def test_boundary_line_counts_as_crossed(self) -> None:
        fence = Fence(700)
        self.assertEqual(fence.crossing(699, 700), CrossingDirection.INBOUND)

    def test_rejects_non_positive_y(self) -> None:
        with self.assertRaises(ValueError):
            Fence(0)


class EngineVeracityTests(unittest.TestCase):
    """Crossings must be backed by consistent observations."""

    @staticmethod
    def _engine(fence_y: int = 700, **kwargs):
        return AlertEngine(Fence(fence_y), fps=25.0, **kwargs)

    def test_flicker_suppressed_by_min_observations(self) -> None:
        engine = self._engine(min_observations=3)
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        # one observation at y=600, jumps below the fence on the second
        update = engine.update(1, [make_detection(1, 1, y1=500, y2=600)])
        self.assertEqual(update.events, [])

        update = engine.update(2, [make_detection(1, 2, y1=600, y2=800)])
        self.assertEqual(update.events, [], "only 2 observations, not trusted")

        # third stable observation now reports the crossing
        update = engine.update(3, [make_detection(1, 3, y1=600, y2=800)])
        if update.events:
            self.assertEqual(update.events[0].direction, CrossingDirection.INBOUND)
        else:
            self.fail("expected a trusted event after 3 observations")

    def test_event_carries_telemetry(self) -> None:
        engine = self._engine()
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        # one observation above the line, then a crossing, then stabilisation
        engine.update(
            1, [make_detection(7, 1, y1=400, y2=500)], stamp
        )
        engine.update(
            2, [make_detection(7, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        update = engine.update(
            3, [make_detection(7, 3, y1=800, y2=900)], stamp + timedelta(seconds=2)
        )

        self.assertEqual(len(update.events), 1)
        event = update.events[0]
        self.assertEqual(event.object_type, "person")
        self.assertEqual(event.track_id, 7)
        self.assertGreaterEqual(event.confidence, 0.9)

        self.assertEqual(len(update.alerts), 1)
        alert = update.alerts[0]
        self.assertEqual(alert.event_id, event.event_id)
        self.assertEqual(alert.object_type, "person")
        self.assertEqual(alert.severity, Severity.CRITICAL)
        self.assertEqual(alert.event_type, EventType.VIRTUAL_FENCE_BREACH)
        self.assertIn("observations", alert.metadata)
        self.assertEqual(alert.metadata["observations"], 3)
        self.assertIn("position", alert.metadata)

    def test_duplicate_crossing_not_reported_twice(self) -> None:
        engine = self._engine(min_observations=1)
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        engine.update(1, [make_detection(2, 1, y1=400, y2=500)], stamp)
        update = engine.update(
            2, [make_detection(2, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        self.assertEqual(len(update.events), 1)

        # object keeps walking deeper; must not fire again for the same crossing
        for i in range(3, 8):
            update = engine.update(
                i,
                [make_detection(2, i, y1=900, y2=1000)],
                stamp + timedelta(seconds=i),
            )
            self.assertEqual(
                update.events, [], f"frame {i}: duplicate event emitted"
            )

    def test_gate_re_arms_after_track_disappears(self) -> None:
        engine = self._engine(min_observations=1, tracking_persistence_seconds=0.4)
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        engine.update(1, [make_detection(3, 1, y1=400, y2=500)], stamp)
        update = engine.update(
            2, [make_detection(3, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        self.assertEqual(len(update.events), 1)

        # track vanishes for longer than the persistence window
        for i in range(3, 20):
            engine.update(i, [], stamp + timedelta(seconds=i))

        # object returns and crosses again -> allowed as a new incident
        engine.update(
            20, [make_detection(3, 20, y1=400, y2=500)], stamp + timedelta(seconds=20)
        )
        update = engine.update(
            21, [make_detection(3, 21, y1=800, y2=900)], stamp + timedelta(seconds=21)
        )
        self.assertEqual(len(update.events), 1)
        self.assertNotEqual(update.events[0].event_id, "EVT-0001")

    def test_outbound_ignored_by_default(self) -> None:
        engine = self._engine(min_observations=1, event_on="inbound")
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        engine.update(1, [make_detection(4, 1, y1=800, y2=900)], stamp)
        update = engine.update(
            2, [make_detection(4, 2, y1=400, y2=500)], stamp + timedelta(seconds=1)
        )
        self.assertEqual(update.events, [], "outbound crossings do not alert")

    def test_severity_mapping(self) -> None:
        self.assertEqual(default_severity("person"), Severity.CRITICAL)
        self.assertEqual(default_severity("car"), Severity.MEDIUM)
        self.assertEqual(default_severity("truck"), Severity.HIGH)
        self.assertEqual(default_severity("kangaroo"), Severity.LOW)

    def test_alert_throttled_per_track(self) -> None:
        engine = self._engine(
            min_observations=1, event_on="both", alert_cooldown_seconds=5.0
        )
        stamp = datetime(2026, 1, 1, 12, 0, 0)

        # inbound alert fires immediately
        engine.update(
            1, [make_detection(5, 1, y1=400, y2=500)], stamp
        )
        update = engine.update(
            2, [make_detection(5, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        self.assertEqual(len(update.alerts), 1)
        self.assertEqual(len(update.events), 1)

        # the same object exits the zone moments later...
        update = engine.update(
            3, [make_detection(5, 3, y1=400, y2=500)], stamp + timedelta(seconds=2)
        )
        self.assertEqual(len(update.events), 1, "outbound is still a real event")
        self.assertEqual(
            update.alerts, [], "cooldown must suppress a second alert for track 5"
        )

    def test_no_detections_produce_nothing(self) -> None:
        engine = self._engine()
        stamp = datetime(2026, 1, 1, 12, 0, 0)
        update = engine.update(1, [], stamp)
        self.assertEqual(update.events, [])
        self.assertEqual(update.alerts, [])

    def test_invalid_parameters_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AlertEngine(Fence(700), fps=0)
        with self.assertRaises(ValueError):
            AlertEngine(Fence(700), min_observations=0)
        with self.assertRaises(ValueError):
            AlertEngine(Fence(700), event_on="sideways")


class FeedSerializationTests(unittest.TestCase):
    def test_event_as_dict_backwards_compatible(self) -> None:
        engine = AlertEngine(
            Fence(700), min_observations=1, now=lambda: datetime(2026, 1, 1, 12, 0, 0)
        )
        stamp = datetime(2026, 1, 1, 12, 0, 0)
        engine.update(1, [make_detection(1, 1, y1=400, y2=500)], stamp)
        update = engine.update(
            2, [make_detection(1, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        data = update.events[0].as_dict()
        # legacy dashboards expect an "object" key
        self.assertEqual(data["object"], "person")
        self.assertEqual(data["direction"], CrossingDirection.INBOUND.value)
        self.assertIn("timestamp", data)
        self.assertIn("evidence_path", data)

    def test_alert_as_dict_complete(self) -> None:
        engine = AlertEngine(
            Fence(700), min_observations=1, now=lambda: datetime(2026, 1, 1, 12, 0, 0)
        )
        stamp = datetime(2026, 1, 1, 12, 0, 0)
        engine.update(1, [make_detection(9, 1, y1=400, y2=500)], stamp)
        update = engine.update(
            2, [make_detection(9, 2, y1=800, y2=900)], stamp + timedelta(seconds=1)
        )
        payload = update.alerts[0].as_dict()
        for key in (
            "alert_id", "severity", "message", "timestamp",
            "frame_number", "metadata",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["severity"], "CRITICAL")

    def test_detection_validation(self) -> None:
        with self.assertRaises(ValueError):
            make_detection(1, 1, x1=300, x2=100)
        with self.assertRaises(ValueError):
            Detection(
                track_id=1, class_id=0, class_name="x", confidence=1.5,
                x1=0, y1=0, x2=10, y2=10, frame_number=1,
            )


if __name__ == "__main__":
    unittest.main()