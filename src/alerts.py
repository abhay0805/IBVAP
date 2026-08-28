"""The IBVAP alert engine.

The engine is the reasoning layer between raw detections and dispatched
alerts. It owns per-object tracking state and the behavioural rules that
keep alerts trustworthy:

* **Veracity** — a crossing is only promoted to an event once the object has
  been observed consistently for ``min_observations`` frames. The crossing is
  *latched* the moment it is detected, then verified later, so an object that
  enters the frame very close to the fence is still reported reliably.

* **Deduplication** — one event per distinct crossing transition; a track
  weaving along the fence line cannot spam the control room.

* **Throttling** — after an alert fires for a track, no further alerts are
  dispatched for that same object until ``alert_cooldown_seconds`` elapse,
  while the underlying events are still recorded faithfully.

* **Context** — every alert carries telemetry (observation count, running
  confidence, duration, position, crossing direction) so an operator can
  judge it without leaving the console.

The engine is intentionally free of side effects: each call to
:meth:`AlertEngine.update` returns newly produced
:class:`SecurityEvent` / :class:`SecurityAlert` objects and the caller
decides where they go. This keeps the layer unit-testable with zero CV or
I/O dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from numbers import Real
from typing import Callable, Sequence

from models import (
    CrossingDirection,
    Detection,
    EventType,
    SecurityAlert,
    SecurityEvent,
    Severity,
    TrackState,
)

DEFAULT_CAMERA_ID = "BOP-CAM-01"
DEFAULT_STATUS = "ACTIVE"


# ------------------------------------------------------------------ geometry


class Fence:
    """A horizontal virtual fence line at pixel row ``y``."""

    __slots__ = ("y",)

    def __init__(self, y: int) -> None:
        if y <= 0:
            raise ValueError(f"Fence y must be positive, got {y}")
        self.y = y

    def crossing(self, previous_y: Real, current_y: Real) -> CrossingDirection | None:
        """Return the direction of a line crossing, or ``None``.

        ``previous_y``/``current_y`` are consecutive tracked centroid rows
        for one object. ``INBOUND`` means the object moved into the guard
        region (rows ``>= self.y``); ``OUTBOUND`` means it moved back out.
        """
        if previous_y < self.y <= current_y:
            return CrossingDirection.INBOUND
        if previous_y >= self.y and current_y < self.y:
            return CrossingDirection.OUTBOUND
        return None


# -------------------------------------------------------------- severity rules


def default_severity(object_type: str) -> Severity:
    """Rank an object by threat relevance at a border location."""
    table = {
        "person": Severity.CRITICAL,
        "dog": Severity.HIGH,
        "horse": Severity.HIGH,
        "truck": Severity.HIGH,
        "car": Severity.MEDIUM,
        "bus": Severity.MEDIUM,
        "motorbike": Severity.MEDIUM,
        "bicycle": Severity.MEDIUM,
        "boat": Severity.HIGH,
    }
    return table.get(object_type.lower(), Severity.LOW)


def build_alert_message(
    object_type: str,
    camera_id: str,
    direction: CrossingDirection | None,
) -> str:
    action = (
        "crossed the virtual fence"
        if direction is not None
        else "was detected"
    )
    return f"{object_type.title()} {action} at camera {camera_id}"


# ---------------------------------------------------------------- track state


@dataclass(slots=True)
class _TrackRecord:
    """Live per-object state maintained across frames by the engine."""

    track_id: int
    class_name: str
    first_seen_frame: int
    last_seen_frame: int
    observations: int = 0
    confidence_sum: float = 0.0
    last_confidence: float | None = None
    center: tuple[int, int] | None = None
    previous_center: tuple[int, int] | None = None
    pending_direction: CrossingDirection | None = None

    def observe(self, detection: Detection) -> None:
        """Apply one confirmed observation of this track."""
        self.observations += 1
        self.confidence_sum += detection.confidence
        self.last_confidence = detection.confidence
        self.previous_center = self.center
        self.center = detection.center
        self.last_seen_frame = detection.frame_number

    @property
    def mean_confidence(self) -> float | None:
        if self.observations == 0:
            return None
        return self.confidence_sum / self.observations

    def is_stale(self, current_frame: int, max_gap_frames: int) -> bool:
        return current_frame - self.last_seen_frame > max_gap_frames

    def snapshot(self) -> TrackState:
        return TrackState(
            track_id=self.track_id,
            class_name=self.class_name,
            observations=self.observations,
            mean_confidence=self.mean_confidence,
            first_seen_frame=self.first_seen_frame,
            last_seen_frame=self.last_seen_frame,
            last_center=self.center,
            direction=self.pending_direction,
        )


# ---------------------------------------------------------------------- engine


class AlertEngine:
    """Turns per-frame detections into verified events and alerts.

    Typical use::

        engine = AlertEngine(Fence(700), fps=25.0, camera_id="BOP-CAM-01")
        for number, detections in frame_stream:
            events, alerts = engine.update(number, detections)
            persist(events, alerts)   # caller-owned side effects
    """

    def __init__(
        self,
        fence: Fence,
        *,
        fps: float = 25.0,
        min_observations: int = 3,
        alert_cooldown_seconds: float = 10.0,
        tracking_persistence_seconds: float = 2.0,
        event_on: str = "inbound",
        event_type: EventType = EventType.VIRTUAL_FENCE_BREACH,
        camera_id: str = DEFAULT_CAMERA_ID,
        severity: Callable[[str], Severity] = default_severity,
        make_message: Callable[
            [str, str, CrossingDirection | None], str
        ] = build_alert_message,
        status: str = DEFAULT_STATUS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        if min_observations < 1:
            raise ValueError(
                f"min_observations must be >= 1, got {min_observations}"
            )
        if alert_cooldown_seconds < 0:
            raise ValueError(
                f"alert_cooldown_seconds must be >= 0, got {alert_cooldown_seconds}"
            )
        if event_on.lower() not in {"inbound", "outbound", "both"}:
            raise ValueError(
                f"event_on must be one of inbound|outbound|both, got {event_on!r}"
            )

        self._fence = fence
        self._fps = float(fps)
        self._min_observations = max(1, int(min_observations))
        self._cooldown_s = float(alert_cooldown_seconds)
        self._stale_frames = max(
            int(fps * max(tracking_persistence_seconds, 0.1)), 1
        )
        self._event_on = event_on.lower()
        self._event_type = event_type
        self._camera_id = camera_id
        self._severity = severity
        self._make_message = make_message
        self._status = status
        self._now = now or (lambda: datetime.now().astimezone())

        self._tracks: dict[int, _TrackRecord] = {}
        # (track_id, direction) pairs that already produced an event today,
        # so the same crossing transition cannot fire twice while a track
        # remains in view. A genuine reversal (INBOUND then OUTBOUND) is a
        # distinct transition and is still recorded truthfully.
        self._crossed_gate: set[tuple[int, CrossingDirection]] = set()
        self._last_alert_at: dict[int, datetime] = {}
        self._active_alert_tracks: set[int] = set()
        self._event_counter = 0
        self._alert_counter = 0
        self._render_order: list[int] = []

    # ------------------------------------------------------------------ run
    def update(
        self,
        frame_number: int,
        detections: Sequence[Detection],
        when: datetime | None = None,
    ) -> "EngineUpdate":
        """Advance the engine by one frame.

        :param frame_number: current frame index (1-based).
        :param detections: detections observed in this frame.
        :param when: wall-clock time, defaults to now.
        :returns: an :class:`EngineUpdate`.
        """
        stamp = when or self._now()

        seen: set[int] = set()
        for detection in detections:
            track_id = detection.track_id
            seen.add(track_id)
            record = self._tracks.get(track_id)
            if record is None:
                record = _TrackRecord(
                    track_id=track_id,
                    class_name=detection.class_name,
                    first_seen_frame=frame_number,
                    last_seen_frame=frame_number,
                )
                self._tracks[track_id] = record
            record.observe(detection)

        # Tracks that vanish are forgotten after a grace period so the fence
        # gate re-arms for an object that re-enters the scene later.
        for track_id in list(self._tracks):
            if track_id not in seen and self._tracks[track_id].is_stale(
                frame_number, self._stale_frames
            ):
                self._forget(track_id)

        events, alerts = self._evaluate(frame_number, detections, stamp)

        for alert in alerts:
            self._active_alert_tracks.add(alert.track_id)
        self._active_alert_tracks &= seen
        self._render_order = self._build_render_order(list(seen))

        return EngineUpdate(
            events=events,
            alerts=alerts,
            render_order=self._render_order,
            active_tracks=list(self._tracks),
        )

    # -------------------------------------------------------------- internals
    def _forget(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)
        self._crossed_gate = {
            pair for pair in self._crossed_gate if pair[0] != track_id
        }
        self._last_alert_at.pop(track_id, None)
        self._active_alert_tracks.discard(track_id)

    def _evaluate(
        self,
        frame_number: int,
        detections: Sequence[Detection],
        stamp: datetime,
    ) -> tuple[list[SecurityEvent], list[SecurityAlert]]:
        events: list[SecurityEvent] = []
        alerts: list[SecurityAlert] = []

        for detection in detections:
            record = self._tracks[detection.track_id]
            if record.previous_center is None or record.center is None:
                continue

            # 1. Latch any freshly-detected crossing transition.
            direction = self._fence.crossing(
                record.previous_center[1], record.center[1]
            )
            if direction is not None and (
                detection.track_id, direction
            ) not in self._crossed_gate:
                if (
                    self._event_on == "both"
                    or direction.value.lower() == self._event_on
                ):
                    record.pending_direction = direction

            # 2. Promote a latched crossing once the track is trustworthy.
            pending = record.pending_direction
            if pending is None:
                continue
            if record.observations < self._min_observations:
                continue

            record.pending_direction = None
            self._crossed_gate.add((detection.track_id, pending))

            self._event_counter += 1
            event = SecurityEvent(
                event_id=f"EVT-{self._event_counter:04d}",
                event_type=self._event_type,
                object_type=detection.class_name,
                track_id=detection.track_id,
                camera_id=self._camera_id,
                timestamp=stamp,
                frame_number=frame_number,
                status=self._status,
                confidence=record.mean_confidence or detection.confidence,
                direction=pending,
            )
            events.append(event)

            # 3. Throttle duplicate notifications for the same object.
            last_alert = self._last_alert_at.get(detection.track_id)
            if last_alert is None or (
                stamp - last_alert
            ).total_seconds() >= self._cooldown_s:
                self._alert_counter += 1
                self._last_alert_at[detection.track_id] = stamp
                alerts.append(self._build_alert(event, record, pending))

        return events, alerts

    def _build_alert(
        self,
        event: SecurityEvent,
        record: _TrackRecord,
        direction: CrossingDirection | None,
    ) -> SecurityAlert:
        metadata = {
            "observations": record.observations,
            "mean_confidence": (
                None
                if record.mean_confidence is None
                else round(record.mean_confidence, 3)
            ),
            "duration_s": round(
                (record.last_seen_frame - record.first_seen_frame) / self._fps,
                2,
            ),
            "position": list(record.center) if record.center is not None else None,
        }
        return SecurityAlert(
            alert_id=f"ALT-{self._alert_counter:04d}",
            event_id=event.event_id,
            event_type=event.event_type,
            object_type=event.object_type,
            track_id=event.track_id,
            camera_id=event.camera_id,
            severity=self._severity(event.object_type),
            status=event.status,
            message=self._make_message(
                event.object_type, event.camera_id, direction
            ),
            timestamp=event.timestamp,
            frame_number=event.frame_number,
            evidence_path=None,  # filled by caller after evidence capture
            metadata=metadata,
        )

    def _build_render_order(self, seen: list[int]) -> list[int]:
        """Stable render ordering: existing tracks first, newest last."""
        order = [tid for tid in self._render_order if tid in seen]
        order.extend(tid for tid in seen if tid not in order)
        return order

    # ------------------------------------------------------------------ misc
    @property
    def track_snapshots(self) -> list[TrackState]:
        return [
            self._tracks[tid].snapshot()
            for tid in self._render_order
            if tid in self._tracks
        ]

    @property
    def event_count(self) -> int:
        return self._event_counter

    @property
    def alert_count(self) -> int:
        return self._alert_counter

    def clear(self) -> None:
        """Forget all tracking state (e.g. on camera reconnect)."""
        self._tracks.clear()
        self._crossed_gate.clear()
        self._last_alert_at.clear()
        self._active_alert_tracks.clear()
        self._render_order.clear()


@dataclass(frozen=True, slots=True)
class EngineUpdate:
    """Result of advancing the engine over one frame."""

    events: list[SecurityEvent]
    alerts: list[SecurityAlert]
    render_order: list[int] = field(default_factory=list)
    active_tracks: list[int] = field(default_factory=list)