"""IBVAP standalone license-plate detection pipeline.

Runs a YOLO tracker + EasyOCR majority-vote pipeline on a user-supplied
video.  The video can be given as the first CLI argument, via ``--video``,
or entered interactively at runtime.

Usage::

    python src/main.py                          # prompts for a video path
    python src/main.py videos/test.mp4          # positional argument
    python src/main.py --video videos/test.mp4  # named flag
    python src/main.py --video videos/test.mp4 --model yolo26n.pt --output output/result.mp4

Exit codes: 0 success, 1 failure, 130 keyboard interrupt.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import cv2
import easyocr
from ultralytics import YOLO


# ------------------------------------------------------------------ defaults

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
DEFAULT_MODEL_NAME = "license_plate_detector.pt"
DEFAULT_MODEL_PATH = WEIGHTS_DIR / DEFAULT_MODEL_NAME
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_CONFIDENCE = 0.4
DEFAULT_MIN_READS = 15          # frames of consistent OCR before locking
DEFAULT_MIN_PLATE_LEN = 5      # reject OCR glitches shorter than this
DEFAULT_OCR_ALLOWLIST = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# HuggingFace model URL (community fine-tuned YOLOv8 for license plates)
_HF_MODEL_URL = (
    "https://huggingface.co/Koushim/yolov8-license-plate-detection"
    "/resolve/main/best.pt?download=true"
)


def ensure_model(model_path: Path) -> Path:
    """Return a valid model path, checking fallback locations or downloading from HuggingFace if needed."""
    if model_path.exists():
        return model_path

    # Check common fallback locations
    candidates = [
        model_path,
        WEIGHTS_DIR / model_path.name,
        Path.cwd() / model_path.name,
        Path(__file__).resolve().parent.parent / model_path.name,
        WEIGHTS_DIR / DEFAULT_MODEL_NAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    target_path = WEIGHTS_DIR / DEFAULT_MODEL_NAME
    if target_path.exists():
        return target_path

    # Auto-download the default model
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"⬇️  Model not found locally ({model_path.name})")
    print(f"   Downloading plate-detection weights from HuggingFace …")
    print(f"   URL: {_HF_MODEL_URL}\n")

    try:
        req = urllib.request.Request(_HF_MODEL_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 64
            with open(target_path, "wb") as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = min(100, downloaded * 100 // total_size)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(
                            f"\r   [{bar}] {pct:3d}%  ({mb:.1f}/{total_mb:.1f} MB)",
                            end="", flush=True,
                        )
        print(f"\n\n   ✅ Model saved to {target_path}\n")
        return target_path
    except Exception as exc:
        print(f"\n   ❌ Download failed: {exc}", file=sys.stderr)
        print(
            "   Please download the model manually and place it at:\n"
            f"     {target_path}\n"
            f"   Or specify a different model with --model <path>",
            file=sys.stderr,
        )
        if target_path.exists():
            target_path.unlink()
        sys.exit(1)


# ------------------------------------------------------------------ helpers

def preprocess_plate(plate_img):
    """Upscale and enhance contrast for dark / blurry plates."""
    h, w = plate_img.shape[:2]
    if h == 0 or w == 0:
        return None

    # Upscale — at least 3× or enough to reach 120 px tall
    scale = max(3.0, 120.0 / h)
    resized = cv2.resize(
        plate_img,
        (int(w * scale), int(h * scale)),
        interpolation=cv2.INTER_CUBIC,
    )

    # Grayscale + CLAHE contrast enhancement
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Bilateral filter to suppress pixel noise while keeping edges
    filtered = cv2.bilateralFilter(enhanced, 11, 17, 17)
    return filtered


def clean_plate_text(raw_text: str) -> str:
    """Remove spaces and special characters, upper-case the result."""
    return re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()


# ------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="IBVAP-Main",
        description=(
            "Standalone license-plate detection pipeline.  Supply a video "
            "via CLI flag, positional argument, or enter it interactively."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "video_pos",
        nargs="?",
        default=None,
        help="Input video path (positional, optional).",
    )
    parser.add_argument(
        "--video", "-v",
        type=str,
        default=None,
        dest="video_flag",
        help="Input video path (named flag).",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=str(DEFAULT_MODEL_PATH),
        help="YOLO weights file for plate detection.",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output video path.  Defaults to output/<input_name>_output.mp4.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE,
        help="Minimum YOLO detection confidence.",
    )
    parser.add_argument(
        "--min-reads",
        type=int,
        default=DEFAULT_MIN_READS,
        help="Number of consistent OCR reads before a plate is confirmed.",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        default=False,
        help="Enable GPU acceleration for EasyOCR.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        default=False,
        help="Display annotated frames in a live window (press 'q' to quit).",
    )
    parser.add_argument(
        "--limit-frames",
        type=int,
        default=0,
        help="Stop after processing this many frames (0 = entire video).",
    )
    return parser


def resolve_video_path(args: argparse.Namespace) -> Path:
    """Determine the video path from CLI args or interactive prompt."""
    # Named flag takes precedence, then positional, then interactive.
    raw = args.video_flag or args.video_pos

    if raw is None:
        print("\n╔══════════════════════════════════════════════════╗")
        print("║   IBVAP — License Plate Detection Pipeline      ║")
        print("╚══════════════════════════════════════════════════╝\n")
        raw = input("  Enter path to the input video: ").strip()
        if not raw:
            print("Error: No video path provided.", file=sys.stderr)
            sys.exit(1)

    # Strip surrounding quotes the user may have pasted from Explorer
    raw = raw.strip("\"'")
    path = Path(raw)

    if not path.exists():
        print(f"Error: Video not found: {path}", file=sys.stderr)
        sys.exit(1)

    return path


def resolve_output_path(args: argparse.Namespace, video_path: Path) -> Path:
    """Build a sensible output path from args or derive from the input name."""
    if args.output:
        out = Path(args.output)
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = video_path.stem
        out = DEFAULT_OUTPUT_DIR / f"{stem}_output.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------- pipeline

def run(
    video_path: Path,
    output_path: Path,
    model_path: Path,
    confidence: float,
    min_reads: int,
    use_gpu: bool,
    show_video: bool,
    limit_frames: int = 0,
) -> int:
    """Execute the plate-detection pipeline end-to-end."""

    # ----- 1. Load models ------------------------------------------------
    model_path = ensure_model(model_path)
    print(f"\n⏳ Loading YOLO model: {model_path}")
    model = YOLO(str(model_path))

    print("⏳ Loading EasyOCR engine …")
    reader = easyocr.Reader(["en"], gpu=use_gpu)

    # ----- 2. Open video source ------------------------------------------
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: Could not open video: {video_path}", file=sys.stderr)
        return 1

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"📹 Source : {video_path}  ({width}×{height} @ {fps} fps)")
    print(f"📂 Output : {output_path}")
    print(f"🔧 Config : conf≥{confidence}  min_reads={min_reads}  gpu={use_gpu}\n")

    out = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not out.isOpened():
        print(f"Error: Could not open video writer: {output_path}", file=sys.stderr)
        cap.release()
        return 1

    # ----- 3. Tracking state ---------------------------------------------
    plate_history: dict[int, list[str]] = {}
    reported_plates: set[int] = set()
    frame_count = 0
    start_time = time.monotonic()

    print("🚀 Processing video …\n")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False,
                conf=confidence,
            )

            if results[0].boxes.id is not None:
                for box, track_id_tensor in zip(
                    results[0].boxes, results[0].boxes.id
                ):
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    track_id = int(track_id_tensor.item())

                    # Pad and crop the plate region
                    pad = 2
                    plate_crop = frame[
                        max(0, y1 - pad) : min(height, y2 + pad),
                        max(0, x1 - pad) : min(width, x2 + pad),
                    ]

                    # Enhance the crop for OCR
                    processed_plate = preprocess_plate(plate_crop)

                    if processed_plate is not None:
                        ocr_results = reader.readtext(
                            processed_plate,
                            allowlist=DEFAULT_OCR_ALLOWLIST,
                            detail=0,
                        )

                        if ocr_results:
                            raw_text = "".join(ocr_results)
                            clean_text = clean_plate_text(raw_text)

                            # Ignore short glitch reads
                            if len(clean_text) >= DEFAULT_MIN_PLATE_LEN:
                                plate_history.setdefault(track_id, []).append(
                                    clean_text
                                )

                        # Trigger confirmation once we have enough reads
                        if (
                            track_id in plate_history
                            and len(plate_history[track_id]) >= min_reads
                            and track_id not in reported_plates
                        ):
                            best_read = Counter(
                                plate_history[track_id]
                            ).most_common(1)[0][0]

                            if len(best_read) >= DEFAULT_MIN_PLATE_LEN:
                                print(
                                    f"  🚨 [CONFIRMED] Vehicle #{track_id}  →  "
                                    f"Plate: {best_read}"
                                )
                                reported_plates.add(track_id)

                    # --- Draw annotations ---
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    if track_id in reported_plates:
                        display_text = Counter(
                            plate_history[track_id]
                        ).most_common(1)[0][0]
                        color = (0, 255, 0)  # green — locked
                    else:
                        current_count = len(
                            plate_history.get(track_id, [])
                        )
                        display_count = min(current_count, min_reads)
                        display_text = f"Scanning… ({display_count}/{min_reads})"
                        color = (0, 255, 255)  # yellow — scanning

                    (tw, th), _ = cv2.getTextSize(
                        display_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2
                    )
                    cv2.rectangle(
                        frame,
                        (x1, max(y1 - 30, 0)),
                        (x1 + tw + 10, y1),
                        color,
                        -1,
                    )
                    cv2.putText(
                        frame,
                        display_text,
                        (x1 + 5, max(y1 - 8, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 0),
                        2,
                    )

            out.write(frame)

            # Show live preview if requested
            if show_video:
                cv2.imshow("IBVAP — Plate Detection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("\n⏹  Stopped by operator (q)")
                    break

            # Progress indicator every 100 frames
            if frame_count % 100 == 0:
                elapsed = time.monotonic() - start_time
                fps_actual = frame_count / elapsed if elapsed else 0
                pct = (
                    f" ({frame_count * 100 // total_frames}%)"
                    if total_frames > 0
                    else ""
                )
                print(
                    f"  ⏱  Frame {frame_count}{pct}  "
                    f"| {fps_actual:.1f} fps  "
                    f"| plates confirmed: {len(reported_plates)}"
                )

            if limit_frames > 0 and frame_count >= limit_frames:
                print(f"\n⏹  Reached frame limit ({limit_frames})")
                break

    except KeyboardInterrupt:
        print("\n⏹  Interrupted by operator")

    finally:
        cap.release()
        out.release()
        if show_video:
            cv2.destroyAllWindows()

    # ----- 4. Summary ----------------------------------------------------
    elapsed = time.monotonic() - start_time
    print("\n" + "═" * 50)
    print(f"  ✅ Processing complete")
    print(f"     Frames  : {frame_count}")
    print(f"     Time    : {elapsed:.1f}s  ({frame_count / elapsed:.1f} fps)" if elapsed else "")
    print(f"     Plates  : {len(reported_plates)} confirmed")
    print(f"     Output  : {output_path}")
    print("═" * 50 + "\n")

    if reported_plates:
        print("  Confirmed plates:")
        for tid in sorted(reported_plates):
            best = Counter(plate_history[tid]).most_common(1)[0][0]
            reads = len(plate_history[tid])
            print(f"    Vehicle #{tid:>3d}  →  {best}  ({reads} reads)")
        print()

    return 0


# ------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    video_path = resolve_video_path(args)
    output_path = resolve_output_path(args, video_path)

    return run(
        video_path=video_path,
        output_path=output_path,
        model_path=Path(args.model),
        confidence=args.confidence,
        min_reads=args.min_reads,
        use_gpu=args.gpu,
        show_video=args.show,
        limit_frames=args.limit_frames,
    )


if __name__ == "__main__":
    raise SystemExit(main())
