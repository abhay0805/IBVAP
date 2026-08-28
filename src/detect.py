"""IBVAP detection pipeline - main entry point.

Wires the layers of the platform together for one detection session::

    video source -> object detector (YOLO tracking)
                  -> alert engine (crossings, throttling)
                  -> persistence (SQLite + JSON feeds)
                  -> notification channels (console, optional webhook)

Run from the repository root::

    python src/detect.py
    python src/detect.py --webhook-url http://control-room:8080/ingest/alerts

Exit codes: 0 on success, 1 on failure, 130 when interrupted.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import datetime
from typing import Any

import cv2
from ultralytics import YOLO

from alerts import AlertEngine, Fence
from channels import AlertChannel, ConsoleChannel, JsonChannel, LogChannel, WebhookChannel
from config import Settings, load_settings
from database import Database
from models import Detection

LOG = logging.getLogger("ibvap.detect")

ALERT_VISIBLE_SECONDS = 3.0
PROGRESS_EVERY = 50


# ---------------------------------------------------------------------- setup


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
            f"Invalid video dimensions from {settings.video_path}: "
            f"{width}x{height}"
        )
    LOG.info("Source %s: %dx%d @ %.2f fps", settings.video_path, width, height, fps)
    return capture, float(fps), width, height


def load_model(settings: Settings) -> YOLO:
    LOG.info("Loading YOLO model: %s", settings.model_path)
    model = YOLO(str(settings.model_path))
    LOG.info("Model loaded")
    return model


# ------------------------------------------------------------------ detections


def extract_detections(
    result: Any, frame_number: int
) -> list[Detection]:
    """Convert one Ultralytics result into :class:`Detection` objects."""
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


# ------------------------------------------------------------------ annotate


def _draw_fence(frame: Any, fence_y: int) -> None:
    height, width = frame.shape[:2]
    cv2.line(frame, (0, fence_y), (width, fence_y), (0, 0, 255), 4)
    label = "VIRTUAL FENCE"
    (text_width, text_height), _ = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3
    )
    label_y = max(fence_y - 12, text_height + 6)
    cv2.putText(
        frame, label, (50, label_y),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3,
    )


def _draw_detection(
    frame: Any,
    detection: Detection,
    *,
    intrusion: bool,
) -> None:
    color = (0, 0, 255) if intrusion else (0, 255, 0)
    cv2.rectangle(
        frame,
        (detection.x1, detection.y1),
        (detection.x2, detection.y2),
        color,
        2,
    )
    center = detection.center
    cv2.circle(frame, center, 6, color, -1)

    label = f"{detection.class_name} #{detection.track_id} {detection.confidence:.2f}"
    label_y = max(detection.y1 - 10, 20)
    cv2.putText(
        frame, label, (detection.x1, label_y),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
    )

    if intrusion:
        text = "INTRUSION"
        (text_width, _), _ = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2
        )
        banner_x = min(max(detection.x1, 0), frame.shape[1] - text_width - 10)
        banner_y = min(detection.y2 + 24, frame.shape[0] - 8)
        cv2.putText(
            frame, text, (banner_x, banner_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2,
        )
        cv2.rectangle(
            frame,
            (banner_x - 6, banner_y - 18),
            (banner_x + text_width + 6, banner_y + 6),
            (0, 0, 255),
            1,
        )


def _draw_status_bar(frame: Any, settings: Settings, now: datetime) -> None:
    width = frame.shape[1]
    text = (
        f"{settings.camera_id}  |  {now.strftime('%Y-%m-%d %H:%M:%S')}  |  "
        f"fence y={settings.fence_y}"
    )
    cv2.rectangle(frame, (0, 0), (width, 30), (0, 0, 0), -1)
    cv2.putText(
        frame, text, (10, 21),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
    )


# ------------------------------------------------------------- evidence + io


def evidence_path_for(settings: Settings, event_id: str) -> str:
    path = settings.evidence_dir / f"{event_id}.jpg"
    return str(path)


def capture_evidence(frame: Any, path: str) -> str:
    cv2.imwrite(
        path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90]
    )
    return path


def print_session_summary(
    settings: Settings,
    events_count: int,
    alerts_count: int,
    frames_done: int,
    elapsed_s: float,
) -> None:
    LOG.info(
        "Processing complete - %d frames in %.1fs, %d event(s), %d alert(s)",
        frames_done, elapsed_s, events_count, alerts_count,
    )
    LOG.info("Video out : %s", settings.video_out_path)
    LOG.info("Events    : %s", settings.events_path)
    LOG.info("Alerts    : %s", settings.alerts_path)
    LOG.info("Database  : %s", settings.db_path)
    LOG.info("Evidence  : %s", settings.evidence_dir)


# ---------------------------------------------------------------------- run


def run(settings: Settings) -> int:
    start_wall = time.monotonic()

    model = load_model(settings)
    capture, fps, width, height = open_source(settings)

    db = Database(settings.db_path)
    db.initialize()

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

    video_writer = cv2.VideoWriter(
        str(settings.video_out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not video_writer.isOpened():
        raise RuntimeError(f"Could not open video writer: {settings.video_out_path}")

    track_kwargs: dict = {"persist": True, "conf": settings.confidence}
    if settings.classes is not None:
        track_kwargs["classes"] = list(dict.fromkeys(settings.classes))

    frame_number = 0
    events_total = 0
    alerts_total = 0
    overlays: dict[int, float] = {}
    start_loop = time.monotonic()

    try:
        while True:
            ret, frame = capture.read()
            if not ret:
                break
            frame_number += 1

            results = model.track(frame, verbose=False, **track_kwargs)
            detections = extract_detections(results[0], frame_number)
            stamp = datetime.now().astimezone()
            update = engine.update(frame_number, detections, stamp)

            # label this frame's fresh events as intrusions and reset timer
            for alert in update.alerts:
                overlays[alert.track_id] = time.monotonic() + ALERT_VISIBLE_SECONDS
            overlays = {
                tid: until
                for tid, until in overlays.items()
                if time.monotonic() < until
            }

            _draw_fence(frame, settings.fence_y)
            _draw_status_bar(frame, settings, stamp)
            detection_by_track = {d.track_id: d for d in detections}
            for track_id in update.render_order:
                detection = detection_by_track.get(track_id)
                if detection is None:
                    continue
                _draw_detection(
                    frame,
                    detection,
                    intrusion=track_id in overlays,
                )

            # persist events + dispatch alerts (evidence shows the overlay)
            evidence_by_event: dict[str, str] = {}
            for event in update.events:
                path = capture_evidence(frame, evidence_path_for(settings, event.event_id))
                persisted = replace_path(event, path)
                db.insert_event(persisted)
                events_json.append(persisted.as_dict())
                evidence_by_event[persisted.event_id] = persisted.evidence_path or ""
                events_total += 1
                LOG.warning(
                    "EVENT %s | %s at %s | %s #%s | frame %d",
                    persisted.event_id,
                    persisted.event_type.value,
                    persisted.camera_id,
                    persisted.object_type,
                    persisted.track_id,
                    persisted.frame_number,
                )

            for alert in update.alerts:
                evidence = evidence_by_event.get(alert.event_id or "")
                complete = replace_path(alert, evidence)
                for channel in channels:
                    channel.send(complete)
                db.insert_alert(complete)
                alerts_total += 1

            video_writer.write(frame)

            if settings.show_video:
                cv2.imshow("IBVAP - Border Surveillance", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    LOG.info("Operator interrupt via window")
                    break

            if frame_number % PROGRESS_EVERY == 0:
                LOG.info(
                    "Processed %d frames (%d events, %d alerts)",
                    frame_number, events_total, alerts_total,
                )

            if settings.limit_frames and frame_number >= settings.limit_frames:
                LOG.info("Reached --limit-frames=%d, stopping", settings.limit_frames)
                break

    except KeyboardInterrupt:
        LOG.warning("Interrupted by operator")
    finally:
        capture.release()
        video_writer.release()

        # settle webhook before writing final registry counts
        webhook.close()
        events_json.close()
        alerts_json.close()

    elapsed = time.monotonic() - start_wall
    loop_seconds = time.monotonic() - start_loop
    print_session_summary(
        settings, events_total, alerts_total, frame_number, elapsed,
    )
    if frame_number == 0 and not settings.limit_frames:
        LOG.error("No frames were read from source")
        return 2

    LOG.info(
        "Throughput %.1f fps (inference + IO)",
        frame_number / loop_seconds if loop_seconds else 0.0,
    )
    return 0


def replace_path(record: Any, path: str | None) -> Any:
    return replace(record, evidence_path=path)


def main(argv: list[str] | None = None) -> int:
    try:
        settings = load_settings(argv)
        configure_logging(settings)
        LOG.info("IBVAP start | camera=%s | conf=%.2f | fence_y=%d",
                 settings.camera_id, settings.confidence, settings.fence_y)
        return run(settings)
    except Exception as exc:
        logging.getLogger("ibvap").exception("Fatal error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())