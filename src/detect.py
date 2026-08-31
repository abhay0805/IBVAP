"""IBVAP unified simultaneous detection pipeline.

Wires the layers of the platform together for high-throughput detection sessions:
- Primary YOLO Object Tracking (Persons, Vehicles: Cars, Trucks, Buses, Motorbikes)
- Virtual Fence Breach Detection & Behavioral Trajectory Analytics
- Asynchronous ANPR Engine (Plate Localization + Preprocessing + EasyOCR + Majority Voting)
- Cryptographic SHA-256 Blockchain Audit Ledger + SQLite Persistence
- Multi-Channel Notifications (Console, JSON Feeds, Webhooks)
- Simultaneous Visual Overlays (Vehicle, Person, and Exact License Plate Bounding Boxes)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

from alerts import (
    DEFAULT_STATUS,
    AlertEngine,
    Fence,
    build_plate_alert_message,
    severity_for_event,
)
from analytics import (
    SuspiciousActivityTracker,
    apply_night_vision_enhancement,
    is_low_light_frame,
    log_suspicious_activity,
)
from anpr import (
    VEHICLE_CLASSES,
    AnprPipeline,
    PlateCandidate,
    PlateReader,
    PlateReading,
    PlateTracker,
    YoloPlateDetector,
    create_plate_detector,
)
from blockchain import add_event_to_blockchain, initialize_blockchain
from channels import AlertChannel, ConsoleChannel, JsonChannel, LogChannel, WebhookChannel
from config import Settings, load_settings
from database import (
    Database,
    get_next_event_number,
    get_vehicle_by_plate,
    initialize_database,
    save_event,
)
from models import Detection, EventType, PlateReading as ModelPlateReading, SecurityAlert, SecurityEvent

LOG = logging.getLogger("ibvap.detect")

ALERT_VISIBLE_SECONDS = 3.0
PROGRESS_EVERY = 50
DEFAULT_MODEL = "yolo26n.pt"
DEFAULT_PLATE_MODEL = Path(__file__).resolve().parent / "weights" / "license_plate_detector.pt"


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger("ibvap")
    root.setLevel(logging.DEBUG if settings.verbose else logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if hasattr(settings, "output_dir") and settings.output_dir:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            settings.output_dir / "run.log", encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    logging.getLogger("ultralytics").setLevel(logging.WARNING)


def open_source(settings: Settings) -> tuple[cv2.VideoCapture, float, int, int]:
    capture = cv2.VideoCapture(str(settings.video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video source: {settings.video_path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    if width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError(
            f"Invalid video dimensions from {settings.video_path}: {width}x{height}"
        )
    LOG.info("Source %s: %dx%d @ %.2f fps", settings.video_path, width, height, fps)
    return capture, float(fps), width, height


def load_model(settings: Settings) -> YOLO:
    model_path = Path(settings.model_path)
    if not model_path.exists():
        candidates = [
            Path("src/weights") / model_path.name,
            Path("weights") / model_path.name,
            Path("src/weights/yolov8s.pt"),
            Path("yolo26n.pt"),
        ]
        for c in candidates:
            if c.exists():
                model_path = c
                break
    LOG.info("Loading YOLO model: %s", model_path)
    model = YOLO(str(model_path))
    LOG.info("Model loaded successfully")
    return model


def extract_detections(result: Any, frame_number: int) -> list[Detection]:
    """Convert one Ultralytics result into Detection objects."""
    boxes = result.boxes
    if boxes is None or boxes.id is None:
        return []

    detections: list[Detection] = []
    names = result.names
    raw_boxes = boxes.xyxy.cpu().numpy()
    track_ids = boxes.id.cpu().numpy().astype(int)
    class_ids = boxes.cls.cpu().numpy().astype(int)
    confidences = boxes.conf.cpu().numpy()

    for box, track_id, class_id, confidence in zip(
        raw_boxes, track_ids, class_ids, confidences
    ):
        detections.append(
            Detection(
                track_id=int(track_id),
                class_id=int(class_id),
                class_name=str(names[int(class_id)]),
                confidence=float(confidence),
                x1=int(round(box[0])),
                y1=int(round(box[1])),
                x2=int(round(box[2])),
                y2=int(round(box[3])),
                frame_number=frame_number,
            )
        )
    return detections


def _draw_fence(frame: Any, fence_y: int) -> None:
    height, width = frame.shape[:2]
    cv2.line(frame, (0, fence_y), (width, fence_y), (0, 0, 255), 3)
    label = "VIRTUAL FENCE BOUNDARY"
    cv2.putText(
        frame,
        label,
        (30, max(fence_y - 12, 30)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 0, 255),
        2,
    )


def _draw_detection(
    frame: Any,
    detection: Detection,
    *,
    intrusion: bool,
    plate_info: tuple[str, float] | None = None,
    plate_bbox: tuple[int, int, int, int] | None = None,
    registry_status: str | None = None,
) -> None:
    # 1. Main bounding box
    if detection.class_name in VEHICLE_CLASSES:
        if registry_status == "VERIFIED":
            color = (0, 255, 0)
        elif plate_info is not None:
            color = (0, 165, 255)
        else:
            color = (255, 200, 0)
    else:
        color = (0, 0, 255) if intrusion else (0, 140, 255)

    cv2.rectangle(frame, (detection.x1, detection.y1), (detection.x2, detection.y2), color, 2)
    center = detection.center
    cv2.circle(frame, center, 5, color, -1)

    # 2. Main Badge Label
    if plate_info is not None:
        p_text, p_conf = plate_info
        stat = f" [{registry_status}]" if registry_status else ""
        label = f"{detection.class_name.upper()} #{detection.track_id} | PLATE: {p_text}{stat}"
    elif detection.class_name in VEHICLE_CLASSES:
        label = f"{detection.class_name.upper()} #{detection.track_id} | Scanning ANPR..."
    else:
        label = f"{detection.class_name.upper()} #{detection.track_id} ({detection.confidence:.2f})"

    (badge_w, badge_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    badge_y = max(detection.y1 - 25, 0)
    cv2.rectangle(frame, (detection.x1, badge_y), (detection.x1 + badge_w + 10, detection.y1), color, -1)
    cv2.putText(
        frame,
        label,
        (detection.x1 + 5, detection.y1 - 7),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        2,
    )

    # 3. Exact License Plate Bounding Box (Rendered prominently on the vehicle)
    if plate_bbox is not None:
        px1, py1, px2, py2 = plate_bbox
        p_color = (0, 255, 0) if plate_info is not None else (0, 255, 255)
        cv2.rectangle(frame, (px1, py1), (px2, py2), p_color, 2)

        plate_text_label = f"[{plate_info[0]}]" if plate_info is not None else "[PLATE]"
        (ptw, pth), _ = cv2.getTextSize(plate_text_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        tag_y = max(py1 - 20, 0)
        cv2.rectangle(frame, (px1, tag_y), (px1 + ptw + 6, py1), (0, 0, 0), -1)
        cv2.putText(
            frame,
            plate_text_label,
            (px1 + 3, py1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            p_color,
            2,
        )

    # 4. Intrusion Banner
    if intrusion:
        text = "⚠️ INTRUSION BREACH"
        (text_width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        banner_x = min(max(detection.x1, 0), frame.shape[1] - text_width - 10)
        banner_y = min(detection.y2 + 26, frame.shape[0] - 8)
        cv2.putText(
            frame,
            text,
            (banner_x, banner_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )


def _draw_status_bar(frame: Any, settings: Settings, now: datetime) -> None:
    width = frame.shape[1]
    text = (
        f"IBVAP CYPHER | {settings.camera_id} | {now.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"FENCE Y={settings.fence_y} | REAL-TIME ASYNC ANPR"
    )
    cv2.rectangle(frame, (0, 0), (width, 30), (0, 0, 0), -1)
    cv2.putText(
        frame,
        text,
        (10, 21),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 200),
        1,
    )


# ------------------------------------------------------------- evidence + io


def evidence_path_for(settings: Settings, event_id: str) -> str:
    path = settings.evidence_dir / f"{event_id}.jpg"
    return str(path)


def capture_evidence(frame: Any, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def replace_path(record: Any, path: str | None) -> Any:
    return replace(record, evidence_path=path)


def persist_event(db: Database, events_json: JsonChannel, event: SecurityEvent) -> int:
    """Write one event to the database and JSON feed; returns counter increment."""
    db.insert_event(event)
    events_json.append(event.as_dict())
    LOG.warning(
        "EVENT %s | %s at %s | %s #%s | frame %d",
        event.event_id,
        event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
        event.camera_id,
        event.object_type,
        event.track_id,
        event.frame_number,
    )
    return 1


def send_alert(
    channels: list[AlertChannel],
    db: Database,
    alert: SecurityAlert,
) -> int:
    """Dispatch one alert through channels and persist it."""
    for channel in channels:
        channel.send(alert)
    db.insert_alert(alert)
    return 1


def build_plate_event(
    reading: ModelPlateReading,
    *,
    camera_id: str,
    status: str,
    event_id: str,
    stamp: datetime,
) -> SecurityEvent:
    """Promote a validated OCR read into a persistable SecurityEvent."""
    return SecurityEvent(
        event_id=event_id,
        event_type=EventType.PLATE_READ,
        object_type=reading.class_name,
        track_id=reading.track_id,
        camera_id=camera_id,
        timestamp=stamp,
        frame_number=reading.frame_number,
        status=status,
        confidence=reading.confidence,
        direction=None,
        evidence_path=reading.crop_path,
        plate_text=reading.plate_text,
        plate_confidence=reading.confidence,
        plate_crop_path=reading.crop_path,
    )


def build_plate_alert(
    event: SecurityEvent,
    reading: ModelPlateReading,
    *,
    alert_id: str,
) -> SecurityAlert:
    """Build the notification payload for a promoted plate event."""
    return SecurityAlert(
        alert_id=alert_id,
        event_id=event.event_id,
        event_type=EventType.PLATE_READ,
        object_type=event.object_type,
        track_id=event.track_id,
        camera_id=event.camera_id,
        severity=severity_for_event(EventType.PLATE_READ, event.object_type),
        status=event.status,
        message=build_plate_alert_message(
            event.object_type, reading.plate_text, event.camera_id
        ),
        timestamp=event.timestamp,
        frame_number=event.frame_number,
        evidence_path=event.evidence_path,
        metadata={
            "plate_text": reading.plate_text,
            "plate_confidence": round(float(reading.confidence), 3),
            "plate_bbox": list(reading.bbox) if reading.bbox else [],
        },
    )


def print_session_summary(
    settings: Settings,
    events_count: int,
    alerts_count: int,
    plates_count: int,
    frames_done: int,
    elapsed_s: float,
) -> None:
    avg_fps = frames_done / elapsed_s if elapsed_s else 0.0
    LOG.info(
        "Processing complete — %d frames in %.1fs (%.1f FPS), %d event(s), %d alert(s), %d plate(s)",
        frames_done, elapsed_s, avg_fps, events_count, alerts_count, plates_count,
    )


# ---------------------------------------------------------------------- run


def run(settings: Settings) -> int:
    """Full platform detection session with Settings dataclass."""
    start_wall = time.monotonic()

    model = load_model(settings)
    capture, fps, width, height = open_source(settings)

    db = Database(settings.db_path)
    db.initialize()
    initialize_blockchain()
    suspicious_tracker = SuspiciousActivityTracker()

    engine = AlertEngine(
        Fence(settings.fence_y),
        fps=fps,
        min_observations=settings.min_observations,
        alert_cooldown_seconds=settings.alert_cooldown_seconds,
        camera_id=settings.camera_id,
    )

    events_json = JsonChannel(settings.events_path)
    alerts_json = JsonChannel(settings.alerts_path)
    console_channel = ConsoleChannel()
    log_channel = LogChannel(LOG, level=logging.WARNING)
    webhook = WebhookChannel(
        None if settings.webhook_url is None else settings.webhook_url,
        token=settings.webhook_token,
        timeout=settings.webhook_timeout,
        max_retries=settings.webhook_max_retries,
    )
    if settings.webhook_url is not None:
        webhook.start()

    channels: list[AlertChannel] = [
        console_channel,
        log_channel,
        alerts_json,
        webhook,
    ]

    video_writer: cv2.VideoWriter | None = None
    if settings.save_video:
        settings.video_out_path.parent.mkdir(parents=True, exist_ok=True)
        video_writer = cv2.VideoWriter(
            str(settings.video_out_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not video_writer.isOpened():
            LOG.warning("Could not open video writer: %s", settings.video_out_path)
            video_writer = None

    track_kwargs: dict = {"persist": True, "conf": settings.confidence}
    if settings.classes is not None:
        track_kwargs["classes"] = list(dict.fromkeys(settings.classes))

    anpr: AnprPipeline | None = None
    plate_model_yolo: Any | None = None   # YOLO model for full-frame plate scanning
    plate_reader: PlateReader | None = None
    plate_tracker: PlateTracker | None = None
    plate_event_seq = 0
    plate_total = 0
    _PLATE_SCAN_INTERVAL = max(1, int(fps / 5))  # scan ~5x per second
    last_plate_scan_frame = 0

    if settings.anpr_enabled:
        plate_model_path = settings.anpr_model_path
        if plate_model_path is None:
            default_weights = Path(__file__).resolve().parent / "weights" / "license_plate_detector.pt"
            if default_weights.exists():
                plate_model_path = default_weights

        detector = create_plate_detector(plate_model_path)
        plate_reader = PlateReader(min_confidence=settings.anpr_confidence, logger=LOG)
        anpr = AnprPipeline(
            detector,
            plate_reader,
            evidence_dir=settings.evidence_dir,
            queue_size=32,
        )
        plate_tracker = PlateTracker(
            min_confirmations=1,
            stale_frames=max(int(fps * 3), 10),
        )
        anpr.start()

        if plate_model_path is not None and isinstance(detector, YoloPlateDetector):
            plate_model_yolo = detector._model
            LOG.info("Full-frame YOLO plate scanner loaded: %s", plate_model_path)
        LOG.info("ANPR active | async pipeline | OCR conf>=%.2f", settings.anpr_confidence)

    frame_number = 0
    events_total = 0
    alerts_total = 0
    overlays: dict[int, float] = {}
    known_plates: dict[int, tuple[str, float]] = {}
    plate_boxes: dict[int, tuple[int, int, int, int]] = {}
    plate_rel_boxes: dict[int, tuple[float, float, float, float]] = {}
    registry_statuses: dict[int, str] = {}
    last_anpr_at: dict[int, int] = {}
    start_loop = time.monotonic()

    try:
        while True:
            ret, frame = capture.read()
            if not ret:
                break
            frame_number += 1

            results = model.track(frame, verbose=False, tracker="bytetrack.yaml", **track_kwargs)
            detections = extract_detections(results[0], frame_number)
            stamp = datetime.now().astimezone()
            update = engine.update(frame_number, detections, stamp)

            # Fast full-frame plate detection & asynchronous OCR queueing
            if plate_model_yolo is not None and anpr is not None:
                if frame_number - last_plate_scan_frame >= _PLATE_SCAN_INTERVAL:
                    last_plate_scan_frame = frame_number
                    _plate_results = plate_model_yolo(frame, conf=0.25, verbose=False)
                    _plate_boxes = _plate_results[0].boxes.xyxy.cpu().numpy() if _plate_results[0].boxes is not None else []

                    for _pb in _plate_boxes:
                        _px1, _py1, _px2, _py2 = int(_pb[0]), int(_pb[1]), int(_pb[2]), int(_pb[3])
                        if (_px2 - _px1) < 16 or (_py2 - _py1) < 6:
                            continue

                        # Match to vehicle track by best containment
                        _best_tid: int | None = None
                        _best_cname = "car"
                        _best_area = 0
                        for _d in detections:
                            if _d.class_name not in VEHICLE_CLASSES:
                                continue
                            _pcx, _pcy = (_px1 + _px2) // 2, (_py1 + _py2) // 2
                            if _d.x1 <= _pcx <= _d.x2 and _d.y1 <= _pcy <= _d.y2:
                                _area = (_d.x2 - _d.x1) * (_d.y2 - _d.y1)
                                if _area > _best_area:
                                    _best_area = _area
                                    _best_tid = _d.track_id
                                    _best_cname = _d.class_name

                        if _best_tid is not None:
                            plate_boxes[_best_tid] = (_px1, _py1, _px2, _py2)
                            if _best_tid not in known_plates:
                                if frame_number - last_anpr_at.get(_best_tid, 0) >= settings.anpr_frame_interval:
                                    last_anpr_at[_best_tid] = frame_number
                                    pad = 2
                                    _plate_crop = frame[max(0, _py1 - pad):min(height, _py2 + pad), max(0, _px1 - pad):min(width, _px2 + pad)]
                                    if _plate_crop.size > 0:
                                        anpr.process(
                                            np.ascontiguousarray(_plate_crop),
                                            track_id=_best_tid,
                                            class_name=_best_cname,
                                            frame_number=frame_number,
                                            vehicle_bbox=(_px1, _py1, _px2, _py2),
                                        )

            # Harvest readings asynchronously from background worker
            if anpr is not None and plate_tracker is not None:
                plate_tracker.tick(frame_number)
                for reading in anpr.drain():
                    promoted = plate_tracker.submit(reading, frame_number)
                    if promoted is None:
                        continue
                    plate_event_seq += 1
                    vinfo = get_vehicle_by_plate(promoted.plate_text)
                    vstatus = "VERIFIED" if vinfo and vinfo.get("status") == "VERIFIED" else "UNAUTHORIZED"
                    registry_statuses[promoted.track_id] = vstatus

                    event = build_plate_event(
                        promoted,
                        camera_id=settings.camera_id,
                        status=vstatus,
                        event_id=f"PLT-{plate_event_seq:04d}",
                        stamp=stamp,
                    )
                    events_total += persist_event(db, events_json, event)
                    if promoted.crop_path:
                        add_event_to_blockchain(event.event_id, event.as_dict(), promoted.crop_path)
                    alert = build_plate_alert(event, promoted, alert_id=f"PLA-{plate_event_seq:04d}")
                    alerts_total += send_alert(channels, db, alert)
                    plate_total += 1
                    known_plates[promoted.track_id] = (promoted.plate_text, promoted.confidence)

            # Mark intrusion alerts
            for alert in update.alerts:
                overlays[alert.track_id] = time.monotonic() + ALERT_VISIBLE_SECONDS
            overlays = {
                tid: until
                for tid, until in overlays.items()
                if time.monotonic() < until
            }

            # Behavioral analysis
            for detection in detections:
                cx, cy = detection.center
                sa_alerts = suspicious_tracker.analyze_object(
                    detection.track_id, detection.class_name, cx, cy, settings.fence_y
                )
                for sa in sa_alerts:
                    log_suspicious_activity(sa)

            # Simultaneous Visual Rendering
            _draw_fence(frame, settings.fence_y)
            _draw_status_bar(frame, settings, stamp)

            detection_by_track = {d.track_id: d for d in detections}
            for track_id in update.render_order:
                detection = detection_by_track.get(track_id)
                if detection is None:
                    continue

                pbox = None
                rel = plate_rel_boxes.get(track_id)
                if rel is not None:
                    rx1, ry1, rx2, ry2 = rel
                    dw = detection.x2 - detection.x1
                    dh = detection.y2 - detection.y1
                    pbox = (
                        detection.x1 + int(rx1 * dw),
                        detection.y1 + int(ry1 * dh),
                        detection.x1 + int(rx2 * dw),
                        detection.y1 + int(ry2 * dh),
                    )
                elif track_id in plate_boxes:
                    pbox = plate_boxes[track_id]

                _draw_detection(
                    frame,
                    detection,
                    intrusion=track_id in overlays,
                    plate_info=known_plates.get(track_id),
                    plate_bbox=pbox,
                    registry_status=registry_statuses.get(track_id),
                )

            # Persist events & alerts
            evidence_by_event: dict[str, str] = {}
            for event in update.events:
                path = capture_evidence(frame, evidence_path_for(settings, event.event_id))
                persisted = replace_path(event, path)
                evidence_by_event[persisted.event_id] = persisted.evidence_path or ""
                events_total += persist_event(db, events_json, persisted)
                add_event_to_blockchain(persisted.event_id, persisted.as_dict(), path)

            for alert in update.alerts:
                evidence = evidence_by_event.get(alert.event_id or "")
                complete = replace_path(alert, evidence)
                alerts_total += send_alert(channels, db, complete)

            if video_writer is not None:
                video_writer.write(frame)

            if settings.show_video:
                cv2.imshow("IBVAP - Border Surveillance", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    LOG.info("Operator interrupt via window")
                    break

            if frame_number % PROGRESS_EVERY == 0:
                LOG.info(
                    "Processed %d frames (%d events, %d alerts, %d plates)",
                    frame_number, events_total, alerts_total, plate_total,
                )

            if settings.limit_frames and frame_number >= settings.limit_frames:
                LOG.info("Reached --limit-frames=%d, stopping", settings.limit_frames)
                break

    except KeyboardInterrupt:
        LOG.warning("Interrupted by operator")
    finally:
        capture.release()
        if video_writer is not None:
            video_writer.release()
        webhook.close()
        events_json.close()
        alerts_json.close()
        if anpr is not None:
            anpr.close()

    elapsed = time.monotonic() - start_wall
    print_session_summary(
        settings, events_total, alerts_total, plate_total, frame_number, elapsed,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        settings = load_settings(argv)
        configure_logging(settings)
        LOG.info(
            "IBVAP start | camera=%s | conf=%.2f | fence_y=%d | anpr=%s",
            settings.camera_id, settings.confidence, settings.fence_y, settings.anpr_enabled,
        )
        return run(settings)
    except Exception as exc:
        logging.getLogger("ibvap").exception("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())