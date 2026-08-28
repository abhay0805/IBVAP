"""Centralized, validated configuration for the IBVAP platform.

Every tunable behaviour of the system is expressed as a field on
:class:`Settings`. Configuration is resolved in three layers, from lowest
to highest precedence:

1. dataclass defaults
2. an optional JSON config file (``--config``)
3. explicit command-line flags

This keeps deployment on remote border sites simple (ship one JSON file)
while remaining fully overridable from the command line.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

MODEL_PATH_DEFAULT = "yolo26n.pt"
VIDEO_PATH_DEFAULT = "videos/test.mp4"
OUTPUT_DIR_DEFAULT = "output"
EVIDENCE_DIR_NAME = "evidence"
DB_FILENAME = "ibvap.db"
EVENTS_FILENAME = "events.json"
ALERTS_FILENAME = "alerts.json"
VIDEO_OUT_FILENAME = "fence_detection.mp4"


@dataclass(slots=True)
class Settings:
    """Validated runtime configuration for one detection session."""

    video_path: Path = Path(VIDEO_PATH_DEFAULT)
    model_path: Path = Path(MODEL_PATH_DEFAULT)
    output_dir: Path = Path(OUTPUT_DIR_DEFAULT)

    confidence: float = 0.40
    fence_y: int = 700
    camera_id: str = "BOP-CAM-01"

    # per-track controls that keep alerts trustworthy (few false alarms)
    min_observations: int = 3
    alert_cooldown_seconds: float = 10.0
    tracking_persistence_seconds: float = 2.0

    classes: list[int] | None = None
    limit_frames: int = 0  # 0 = process the whole video

    # ANPR (automatic number-plate recognition)
    anpr_enabled: bool = True
    anpr_model_path: Path | None = None  # None = classical CV plate detector
    anpr_confidence: float = 0.5
    anpr_frame_interval: int = 5  # enqueue one OCR job per track every N frames

    # outbound notification
    webhook_url: str | None = None
    webhook_token: str | None = None
    webhook_timeout: float = 5.0
    webhook_max_retries: int = 3

    show_video: bool = False
    verbose: bool = False
    config: Path | None = None

    # ---------------------------------------------------------------- paths
    @property
    def evidence_dir(self) -> Path:
        return self.output_dir / EVIDENCE_DIR_NAME

    @property
    def db_path(self) -> Path:
        return self.output_dir / DB_FILENAME

    @property
    def events_path(self) -> Path:
        return self.output_dir / EVENTS_FILENAME

    @property
    def alerts_path(self) -> Path:
        return self.output_dir / ALERTS_FILENAME

    @property
    def video_out_path(self) -> Path:
        return self.output_dir / VIDEO_OUT_FILENAME

    # ------------------------------------------------------------ validation
    def validate(self, *, prepare_dirs: bool = True) -> None:
        errors: list[str] = []

        if not 0.0 < self.confidence <= 1.0:
            errors.append(f"confidence must be in (0, 1], got {self.confidence}")
        if self.fence_y <= 0:
            errors.append(f"fence_y must be positive, got {self.fence_y}")
        if self.min_observations < 1:
            errors.append(f"min_observations must be >= 1, got {self.min_observations}")
        if self.alert_cooldown_seconds < 0:
            errors.append(
                f"alert_cooldown_seconds must be >= 0, got {self.alert_cooldown_seconds}"
            )
        if self.limit_frames < 0:
            errors.append(f"limit_frames must be >= 0, got {self.limit_frames}")
        if not 0.0 < self.anpr_confidence <= 1.0:
            errors.append(
                f"anpr_confidence must be in (0, 1], got {self.anpr_confidence}"
            )
        if self.anpr_frame_interval < 1:
            errors.append(
                f"anpr_frame_interval must be >= 1, got {self.anpr_frame_interval}"
            )
        if self.anpr_model_path is not None and not self.anpr_model_path.exists():
            errors.append(f"ANPR model not found: {self.anpr_model_path}")

        if not self.video_path.exists():
            errors.append(f"video not found: {self.video_path}")
        if not self.model_path.exists():
            errors.append(f"model not found: {self.model_path}")

        if prepare_dirs:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.evidence_dir.mkdir(parents=True, exist_ok=True)

        if errors:
            raise ValueError("Invalid configuration:\n  - " + "\n  - ".join(errors))


# ------------------------------------------------------------------ CLI I/O


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="IBVAP",
        description=(
            "Intelligent Border Video Analytics Platform - real-time "
            "intrusion detection and object-level alerting on live or "
            "recorded CCTV video."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c", "--config", type=Path, default=None,
        help="JSON config file with defaults (CLI flags take precedence).",
    )
    parser.add_argument("-v", "--video", type=Path, default=None,
                        dest="video_path",
                        help="Input video or camera source path.")
    parser.add_argument("-m", "--model", type=Path, default=None,
                        dest="model_path",
                        help="YOLO weights file.")
    parser.add_argument("-o", "--output-dir", type=Path, default=None,
                        dest="output_dir",
                        help="Directory for all generated artifacts.")
    parser.add_argument("--confidence", type=float, default=None,
                        help="Minimum detection confidence (0-1).")
    parser.add_argument("--fence-y", type=int, default=None,
                        help="Y coordinate of the virtual fence line.")
    parser.add_argument("--camera-id", type=str, default=None,
                        help="Identifier reported in events and alerts.")
    parser.add_argument("--min-observations", type=int, default=None,
                        help="Minimum consecutive observations before a "
                             "crossing is trusted.")
    parser.add_argument("--alert-cooldown", type=float, default=None,
                        dest="alert_cooldown_seconds",
                        help="Minimum seconds between alerts for one object.")
    parser.add_argument("--classes", nargs="+", type=int, default=None,
                        help="Restrict detection to these COCO class ids "
                             "(default: all).")
    parser.add_argument("--limit-frames", type=int, default=None,
                        help="Stop after this many frames (0 = whole video).")
    parser.add_argument("--anpr-enabled", action=argparse.BooleanOptionalAction,
                        default=None,
                        help="Enable automatic number-plate recognition.")
    parser.add_argument("--anpr-model", type=Path, default=None,
                        dest="anpr_model_path",
                        help="Optional fine-tuned YOLO plate detector .pt "
                             "(default: classical CV detector).")
    parser.add_argument("--anpr-confidence", type=float, default=None,
                        help="Minimum OCR confidence to accept a plate (0-1).")
    parser.add_argument("--anpr-interval", type=int, default=None,
                        dest="anpr_frame_interval",
                        help="Run one OCR job per track every N frames.")
    parser.add_argument("--webhook-url", type=str, default=None,
                        help="POST alerts to this HTTP(S) endpoint.")
    parser.add_argument("--webhook-token", type=str, default=None,
                        help="Bearer token for webhook authentication.")
    parser.add_argument("--webhook-timeout", type=float, default=None,
                        help="Seconds to wait for a webhook response.")
    parser.add_argument("--webhook-retries", type=int, default=None,
                        dest="webhook_max_retries",
                        help="Maximum delivery attempts per alert.")
    parser.add_argument("--show-video", action="store_true",
                        help="Display the annotated frame in a window.")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging.")
    return parser


def _read_config_file(path: Path | None) -> dict[str, Any]:
    """Load a JSON config file, normalizing relative paths to the repo root."""
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    import json

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return data


def load_settings(argv: list[str] | None = None) -> Settings:
    """Resolve runtime settings using defaults, then JSON, then CLI flags."""
    parser = build_parser()
    args = vars(parser.parse_args(argv))

    file_defaults = _read_config_file(args.pop("config", None))

    def _clean(raw: dict[str, Any]) -> dict[str, Any]:
        """Keep only keys that are actual settings fields and not None."""
        valid = {f.name for f in fields(Settings)}
        return {
            key: value
            for key, value in raw.items()
            if key in valid and value is not None
        }

    values: dict[str, Any] = _clean(asdict(Settings()))
    values.update(_clean(file_defaults))
    values.update(_clean(args))

    settings = Settings(**values)
    settings.validate()
    return settings