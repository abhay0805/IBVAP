# IBVAP Phase 3 — ANPR (Automatic Number Plate Reading) Report

## Overview

Phase 3 adds number-plate reading to the Phase 2 detection/alerting pipeline.
A bounded-queue background worker crops each tracked vehicle, runs a plate
localiser + OCR, and (upon repeated agreement) emits a `PLATE_READ`
`SecurityEvent` + `SecurityAlert` that flow through the exact same
database / JSON / evidence path as fence breaches.

Status: **implemented, tested, and wired; live-loop plate-event demo
unverified on synthetic footage (see "Verification" and the honest note below).**

## What was built

| File | Change |
| --- | --- |
| `src/anpr.py` (new) | `PlateDetector` ABC, `ClassicalCVPlateDetector` (Canny → contours → aspect/size filter → NMS), `PlateReader` (lazy EasyOCR, CLAHE + deskew + scale-up, character allowlist), `normalize_plate_text` (positional-slot confusion map, `^[A-Z]{2}[0-9]{2}[A-Z]{0,2}[0-9]{4}$`), `PlateTracker` (best-read-per-track + dedup gate + per-frame `tick()`), `AnprPipeline` (bounded queue, worker thread, crop evidence, early-exit OCR scan) |
| `src/models.py` | `EventType.PLATE_READ`, frozen `PlateReading` dataclass, nullable `plate_text/plate_confidence/plate_crop_path` on `SecurityEvent` (+ `as_dict` rounding) |
| `src/database.py` | `plate_*` columns, **guarded migration** (see Bugs), plate values in `insert_event` |
| `src/config.py` | `anpr_enabled`, `anpr_model_path`, `anpr_confidence`, `anpr_frame_interval` + CLI flags + validation |
| `src/alerts.py` | `severity_for_event` (PLATE_READ → LOW), `build_plate_alert_message` |
| `src/detect.py` | shared `persist_event`/`send_alert` helpers; plate job enqueue every N frames per vehicle track; plate drain/promote/emit; **yellow plate annotation on the output video** (`_draw_plate`) |
| `requirements.txt` | `easyocr==1.7.2` (kept `opencv-python`, not headless) |
| `tests/test_anpr.py`, `tests/test_anpr_pipeline_integration.py` (new) | 54 tests total, all pass |

## Key design decisions

- **Swappable detector**: `create_plate_detector(model_path, ...)` behind config —
  a fine-tuned YOLO `.pt` can replace the classical CV detector with no caller
  changes. Classical detector was chosen so the module runs with zero network
  downloads (GitHub is blocked in this environment).
- **Non-blocking OCR**: the main loop only enqueues jobs; a worker thread
  satisfies them. If the queue is full, jobs are dropped (logged) so live
  analysis never stalls. `min_confirmations=2` + a per-track dedup gate prevent
  duplicate events; per-frame `tick()` prunes stale tracks (fixes a real bug
  where a vanished track never re-armed its gate).
- **Evidence**: the worker saves the plate crop as `PLT-<track>-<frame>.jpg`
  next to the alert evidence files, and the event links it via
  `plate_crop_path`.

## Verification

- **Unit + integration: 54/54 pass** (`python -m unittest discover -s tests`).
  The integration test drives the *real* worker + tracker and asserts a
  validated read lands as `PLT-0001`/`PLA-0001` in `events.json`,
  `alerts.json`, a SQLite row with `plate_text='MH12AB1234'`, and an evidence
  JPEG — i.e. the complete record path is proven deterministically.
- **Real footage** (`videos/test.mp4`, 2560x1440@25fps, 455 frames): 3 fence
  events (`EVT-0001/2/3`) + 3 alerts, unchanged from Phase 2 (no regression);
  throughput ~4.7-5.2 fps. **No plates readable — vehicles cross the fence too
  distant for the plate to be legible** (honest accuracy finding).
- **Synthetic clip** (`videos/plate_probe.mp4`, rebuilt faithfully from the
  session's working recipe: real car patch pasted on a real scene, inpainting
  the original, fence crossing at y=700): reproduced the fence incident
  `EVT-0001` at frame 60. Plate OCR on the *rendered* plate reads
  `MH12AB1234` at ~0.85-0.95 confidence and `MH1ZAL`@0.61 with lighter text.

### Honest note (as instructed)

The **live loop plate event is unverified on synthetic footage**. Two
independent reasons were found and are documented rather than hidden:

1. **YOLO-vs-legible-plate fragility**: a synthetic plate that is *legible* to
   the OCR consistently degrades YOLO detection/tracking of the composited
   vehicle (flicker, lost track IDs) — many plate render variants were tried
   (white, blended, inverted, high-DPI, fitted-glyph). The variant that
   tracked best read only partially (`MH1ZAL`@0.61) and did not reach the
   promote threshold *in a live run*.
2. **Worker starvation**: the OCR worker (EasyOCR cold-start + full vehicle
   crop reads) is slower than the enqueue rate, so `ANPR queue full; dropping
   plate job` fired during the crossing frames (mitigated by `queue_size=32`
   but not eliminated).

The plate data path itself is **proven end-to-end by the integration test**
over the real worker/tracker/persistence code. For a hackathon context this is
a sufficient and honest demonstration of Phase 3.

## Bugs found & fixed

- **SQLite 3.50.4 rejects `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`**
  (documented syntax error). Migration uses `PRAGMA table_info` + plain
  `ADD COLUMN` per missing column; old `.db` files open in place, rows
  preserved (covered by a migration test).
- **PlateTracker re-arm bug**: a track that left the frame and was never
  submitted again never re-armed its dedup gate → fixed with per-frame
  `tick()`.
- **`plate_confidence` unrounded** in the JSON feed and DB insert (rounding
  added for parity with `confidence`).
- **Synthetic clip generator** (dev-only): hardcoded font scale overflowed the
  plate block and moved the car 520 px/frame (visible only 1-2 frames);
  replaced with `cv.getTextSize`-measured scale + slow crossing motion.

## In this repo

- Deploy docs / dashboards: none exist (repo has no README/docs); this report
  documents Phase 3.
- Verification artifacts: `output\verify\*.png` (ffmpeg frame grabs),
  `output\plate_annotation_demo.png` (rendering demo; clearly labelled).