"""Core data models and enumerations for the IBVAP platform.

These types are the vocabulary of the system:

* :class:`Detection`      - a single model output box (one object, one frame)
* :class:`TrackState`     - an immutable telemetry snapshot of a live track
* :class:`SecurityEvent`  - a verified, persisted security incident record
* :class:`SecurityAlert`  - a notification payload dispatched to channels

All values are immutable (``frozen=True, slots=True``) so they are safe to
share between the detection, alerting and persistence layers while
guaranteeing a single, consistent view of an incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, unique
from typing import Any


@unique
class Severity(str, Enum):
    """Operational severity assigned to an alert.

    Ordering intentionally ranks CRITICAL highest so callers can filter
    or escalate by severity.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _SEVERITY_ORDER[self]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


@unique
class EventType(str, Enum):
    """Kinds of security incidents the platform can generate."""

    VIRTUAL_FENCE_BREACH = "VIRTUAL_FENCE_BREACH"
    NIGHT_MOVEMENT = "NIGHT_MOVEMENT"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"


@unique
class CrossingDirection(str, Enum):
    """Direction of travel relative to the virtual fence.

    ``INBOUND``  - the object entered the protected zone (crossed the line).
    ``OUTBOUND`` - the object left the protected zone.
    """

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


def _require_positive_area(x1: int, y1: int, x2: int, y2: int) -> None:
    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            f"Degenerate bounding box ({x1}, {y1}, {x2}, {y2}): "
            "expected x2 > x1 and y2 > y1"
        )


@dataclass(frozen=True, slots=True)
class Detection:
    """A single tracked detection returned by the object detector."""

    track_id: int
    class_id: int
    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int
    frame_number: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence {self.confidence} out of [0, 1]")
        _require_positive_area(self.x1, self.y1, self.x2, self.y2)

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    @property
    def center_x(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def center_y(self) -> int:
        return (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(float(self.confidence), 3),
            "bbox": [self.x1, self.y1, self.x2, self.y2],
            "frame_number": self.frame_number,
        }


@dataclass(frozen=True, slots=True)
class TrackState:
    """Immutable snapshot of the alert engine's state for one track.

    Emitted on every frame so the presentation layer can overlay accurate
    telemetry (tracking confidence, sustained observations) rather than
    showing raw detections.
    """

    track_id: int
    class_name: str
    observations: int
    mean_confidence: float | None
    first_seen_frame: int
    last_seen_frame: int
    last_center: tuple[int, int] | None
    direction: CrossingDirection | None
    active_alert: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "observations": self.observations,
            "mean_confidence": (
                None if self.mean_confidence is None else round(self.mean_confidence, 3)
            ),
            "first_seen_frame": self.first_seen_frame,
            "last_seen_frame": self.last_seen_frame,
            "last_center": self.last_center,
            "direction": None if self.direction is None else self.direction.value,
            "active_alert": self.active_alert,
        }


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    """A verified security incident that has been recorded and persisted."""

    event_id: str
    event_type: EventType
    object_type: str
    track_id: int
    camera_id: str
    timestamp: datetime
    frame_number: int
    status: str
    confidence: float
    direction: CrossingDirection | None
    evidence_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            # Backwards-compatible key consumed by existing dashboards.
            "object": self.object_type,
            "object_type": self.object_type,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "frame_number": self.frame_number,
            "status": self.status,
            "confidence": round(float(self.confidence), 3),
            "direction": None if self.direction is None else self.direction.value,
            "evidence_path": self.evidence_path,
        }


@dataclass(frozen=True, slots=True)
class SecurityAlert:
    """A notification payload dispatched to external alerting channels."""

    alert_id: str
    event_id: str | None
    event_type: EventType
    object_type: str
    track_id: int
    camera_id: str
    severity: Severity
    status: str
    message: str
    timestamp: datetime
    frame_number: int
    evidence_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "object_type": self.object_type,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "severity": self.severity.value,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "frame_number": self.frame_number,
            "evidence_path": self.evidence_path,
            "metadata": self.metadata,
        }