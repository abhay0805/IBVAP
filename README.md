# 🛡️ IBVAP — Intelligent Border Video Analytics Platform

> **Real-time AI-powered perimeter surveillance system for border security outposts.**
> Detects intrusions, reads license plates, flags suspicious behavior, and records every incident on a tamper-proof blockchain audit ledger — all from a single CCTV feed.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running the Detection Pipeline](#running-the-detection-pipeline)
  - [Running the Dashboard & API Server](#running-the-dashboard--api-server)
  - [Running the Next.js Dashboard](#running-the-nextjs-dashboard)
- [Usage & CLI Reference](#usage--cli-reference)
  - [Detection Engine (Structured Pipeline)](#detection-engine-structured-pipeline)
  - [Standalone License Plate Pipeline](#standalone-license-plate-pipeline)
  - [Legacy Detection Script](#legacy-detection-script)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Module Reference](#module-reference)
- [License](#license)

---

## Overview

**IBVAP (Intelligent Border Video Analytics Platform)** is a defense-grade video analytics system designed for real-time perimeter security at border outposts. It processes live or recorded CCTV footage through a multi-stage AI pipeline:

1. **Object Detection & Tracking** — YOLOv8 with ByteTrack for persistent multi-object tracking.
2. **Virtual Fence Breach Detection** — A configurable horizontal fence line triggers alerts when tracked objects cross from one zone to another.
3. **Automatic Number Plate Recognition (ANPR)** — A non-blocking background pipeline crops vehicles, localizes plates using classical CV or a fine-tuned YOLO model, and reads text via EasyOCR with majority-vote confirmation.
4. **Suspicious Activity Analytics** — Detects loitering behavior (prolonged dwell near the fence) and rapid-approach velocity anomalies.
5. **Blockchain Audit Ledger** — Every security event is cryptographically hashed (SHA-256 with proof-of-work) into an immutable chain stored in SQLite, guaranteeing tamper-proof evidence records.
6. **Multi-Channel Alerting** — Console, JSON file, structured logging, and HTTP webhook delivery with retry and backoff.
7. **Command Dashboard** — A military-style web UI for live surveillance, event browsing, ANPR lookup, blockchain verification, and AI-generated situation reports (SITREP).

---

## Key Features

| Feature | Description |
|---|---|
| 🎯 **YOLOv8 Object Tracking** | Real-time detection and ByteTrack persistent tracking across frames |
| 🚧 **Virtual Fence** | Configurable horizontal boundary with inbound/outbound crossing detection |
| 🔢 **ANPR** | License plate detection (classical CV + optional YOLO), EasyOCR reading, Indian-format normalization, vehicle registry verification |
| 🌙 **Night Vision** | Adaptive CLAHE contrast enhancement and pseudo-thermal colormap for low-light conditions |
| 🕵️ **Behavioral Analytics** | Loitering detection (dwell time + speed heuristics) and rapid fence-approach velocity anomalies |
| 🔗 **Blockchain Ledger** | SHA-256 hashed, proof-of-work mined, Merkle-linked audit chain for tamper-proof evidence |
| 📡 **Webhook Alerts** | Background-threaded HTTP(S) delivery with exponential backoff and bearer token auth |
| 🖥️ **CYPHER Dashboard** | Military-themed web UI with live MJPEG feed, event logs, ANPR hub, blockchain explorer, and AI SITREP generator |
| 🧪 **54 Unit Tests** | Comprehensive test suite covering the alert engine, ANPR pipeline, configuration, and notification channels |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        IBVAP Platform                              │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │  Video    │──▶│  YOLOv8 +    │──▶│  Alert     │──▶│ Channels  │ │
│  │  Source   │   │  ByteTrack   │   │  Engine    │   │ (Console, │ │
│  │          │   │  Detector    │   │            │   │  JSON,    │ │
│  └──────────┘   └──────┬───────┘   └─────┬──────┘   │  Webhook, │ │
│                        │                  │          │  Log)     │ │
│                        ▼                  ▼          └───────────┘ │
│               ┌──────────────┐   ┌──────────────┐                  │
│               │  ANPR        │   │  SQLite DB   │                  │
│               │  Pipeline    │   │  + JSON Feed │                  │
│               │  (async)     │   └──────┬───────┘                  │
│               └──────────────┘          │                          │
│                                         ▼                          │
│                               ┌──────────────────┐                 │
│                               │  Blockchain       │                │
│                               │  Audit Ledger     │                │
│                               └──────────────────┘                 │
│                                         │                          │
│                        ┌────────────────┴────────────────┐         │
│                        ▼                                 ▼         │
│               ┌──────────────┐                 ┌──────────────┐    │
│               │  FastAPI     │                 │  Next.js     │    │
│               │  REST API    │                 │  Dashboard   │    │
│               │  + Dashboard │                 │  (v2)        │    │
│               └──────────────┘                 └──────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Object Detection** | [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) (v8.4.130) with ByteTrack |
| **Computer Vision** | [OpenCV](https://opencv.org/) 5.0 |
| **Deep Learning** | [PyTorch](https://pytorch.org/) 2.13.0 + TorchVision 0.28.0 |
| **OCR** | [EasyOCR](https://github.com/JaidedAI/EasyOCR) 1.7.2 |
| **Backend API** | [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn |
| **Database** | SQLite 3 (WAL mode, crash-safe) |
| **Frontend (v1)** | Vanilla HTML/CSS/JS — military-themed CYPHER dashboard |
| **Frontend (v2)** | [Next.js](https://nextjs.org/) 14 + React 18 + TailwindCSS 3 + TypeScript |
| **Tracking** | NumPy 2.5.2 + LAP 0.5.13 (linear assignment) |
| **Language** | Python 3.14+ |

---

## Project Structure

```
IBVAP/
├── src/                          # Core Python source code
│   ├── main.py                   # Standalone license-plate detection CLI pipeline
│   ├── detect.py                 # Legacy detection script (direct execution)
│   ├── detect_krushna.py         # Structured detection engine (config-driven)
│   ├── config.py                 # Centralized, validated Settings dataclass + CLI parser
│   ├── models.py                 # Core data models (Detection, SecurityEvent, SecurityAlert, PlateReading, etc.)
│   ├── alerts.py                 # Alert engine — fence crossing logic, severity, deduplication, throttling
│   ├── anpr.py                   # ANPR pipeline — plate ROI detection, preprocessing, OCR, registry lookup
│   ├── anpr_krushna.py           # Extended ANPR module with async worker, tracker, and plate normalization
│   ├── database.py               # SQLite persistence layer (Database class + legacy helpers)
│   ├── channels.py               # Alert notification channels (Console, JSON, Webhook, Log)
│   ├── analytics.py              # Night vision enhancement + suspicious activity tracker (loitering, velocity)
│   ├── blockchain.py             # SHA-256 blockchain audit ledger with proof-of-work mining
│   ├── server.py                 # FastAPI REST API + MJPEG live stream + CYPHER dashboard server
│   ├── registry.py               # Vehicle whitelist registry (add/list vehicles in SQLite)
│   └── weights/                  # YOLO model weights directory
│
├── static/                       # Static web dashboard (CYPHER UI v1)
│   ├── index.html                # Main dashboard HTML
│   ├── styles.css                # Military-themed CSS
│   └── app.js                    # Dashboard JavaScript (fetch API data, render tables, SITREP)
│
├── nextWeb/                      # Next.js dashboard (v2 — TypeScript + TailwindCSS)
│   ├── src/
│   │   ├── app/                  # Next.js App Router pages
│   │   ├── components/           # React components
│   │   └── lib/                  # Utility libraries
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── tests/                        # Test suite (54 tests)
│   ├── test_anpr.py              # ANPR unit tests
│   ├── test_anpr_pipeline_integration.py   # End-to-end ANPR integration tests
│   ├── test_channels.py          # Notification channel tests
│   ├── test_config.py            # Configuration validation tests
│   └── test_engine.py            # Alert engine tests
│
├── videos/                       # Input video files (gitignored)
├── output/                       # Generated artifacts (gitignored)
│   ├── fence_detection.mp4       # Annotated output video
│   ├── events.json               # Security events JSON feed
│   ├── alerts.json               # Alerts JSON feed
│   ├── ibvap.db                  # SQLite database
│   └── evidence/                 # Captured evidence frame images (JPG)
│
├── yolo26n.pt                    # YOLOv8-Nano model weights
├── requirements.txt              # Python dependencies
├── PHASE3_REPORT.md              # Phase 3 (ANPR) development report
├── .gitignore
└── README.md                     # ← You are here
```

---

## Getting Started

### Prerequisites

- **Python 3.14+** (with `pip`)
- **Node.js 18+** and **npm** (only if using the Next.js dashboard)
- A test video file (e.g., `videos/test.mp4`)
- ~6 GB free disk space (for PyTorch + model weights)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/abhay0805/IBVAP.git
cd IBVAP

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. (Optional) Install FastAPI + Uvicorn for the dashboard server
pip install fastapi uvicorn
```

### Running the Detection Pipeline

The structured pipeline (`detect_krushna.py`) uses validated configuration, the alert engine, multi-channel output, and ANPR:

```bash
# Basic run with defaults (reads videos/test.mp4, writes to output/)
python src/detect_krushna.py

# Customized run
python src/detect_krushna.py \
  --video videos/border_cam.mp4 \
  --model yolo26n.pt \
  --fence-y 700 \
  --confidence 0.45 \
  --anpr-enabled \
  --webhook-url https://ops.example.com/alerts \
  --verbose
```

### Running the Dashboard & API Server

```bash
cd src
python server.py
# Server starts at http://127.0.0.1:8000
```

Open `http://127.0.0.1:8000` in your browser to access the **CYPHER Command Dashboard**.

### Running the Next.js Dashboard

```bash
cd nextWeb
npm install
npm run dev
# Dashboard available at http://localhost:3000
```

---

## Usage & CLI Reference

### Detection Engine (Structured Pipeline)

```
python src/detect_krushna.py [OPTIONS]

Options:
  -c, --config PATH           JSON config file (CLI flags take precedence)
  -v, --video PATH            Input video or camera source (default: videos/test.mp4)
  -m, --model PATH            YOLO weights file (default: yolo26n.pt)
  -o, --output-dir PATH       Output directory (default: output)
      --confidence FLOAT      Min detection confidence 0-1 (default: 0.40)
      --fence-y INT           Virtual fence Y coordinate (default: 700)
      --camera-id TEXT         Camera identifier (default: BOP-CAM-01)
      --min-observations INT  Frames before crossing is trusted (default: 3)
      --alert-cooldown FLOAT  Seconds between alerts per object (default: 10.0)
      --classes INT [INT...]  Restrict to COCO class IDs
      --limit-frames INT      Stop after N frames (0 = entire video)
      --anpr-enabled          Enable ANPR (default: True)
      --anpr-model PATH       Fine-tuned YOLO plate detector
      --anpr-confidence FLOAT Min OCR confidence (default: 0.35)
      --anpr-interval INT     OCR job per track every N frames (default: 5)
      --webhook-url TEXT      POST alerts to this endpoint
      --webhook-token TEXT    Bearer token for webhook auth
      --show-video            Display live annotated window
      --verbose               Enable debug logging
```

### Standalone License Plate Pipeline

```
python src/main.py [OPTIONS]

Options:
      video_pos               Input video path (positional)
  -v, --video PATH            Input video path (named flag)
  -m, --model PATH            YOLO plate detection weights
  -o, --output PATH           Output video path
      --confidence FLOAT      Min YOLO confidence (default: 0.4)
      --min-reads INT         Consistent OCR reads to confirm (default: 15)
      --gpu                   Enable GPU acceleration for EasyOCR
      --show                  Display live preview window
      --limit-frames INT      Stop after N frames
```

The standalone pipeline auto-downloads a community plate-detection model from HuggingFace if no local weights are found.

### Legacy Detection Script

```bash
# Direct execution (uses hardcoded paths)
cd src
python detect.py
```

---

## Configuration

Configuration is resolved in three layers (lowest → highest precedence):

1. **Dataclass defaults** — Defined in `src/config.py`
2. **JSON config file** — Passed via `--config config.json`
3. **CLI flags** — Override everything

Example JSON config:

```json
{
  "video_path": "videos/border_cam.mp4",
  "model_path": "yolo26n.pt",
  "confidence": 0.45,
  "fence_y": 700,
  "camera_id": "BOP-CAM-01",
  "anpr_enabled": true,
  "anpr_frame_interval": 5,
  "webhook_url": "https://ops.example.com/alerts",
  "webhook_token": "secret-bearer-token"
}
```

---

## API Reference

The FastAPI server (`src/server.py`) exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | CYPHER Dashboard HTML page |
| `GET` | `/api/events` | All recorded fence breach events |
| `GET` | `/api/analytics` | Real-time analytics metrics & threat level |
| `GET` | `/api/vehicles` | Registered whitelist vehicles |
| `POST` | `/api/vehicles` | Register a new vehicle (form data: `plate_number`, `vehicle_type`, `owner`, `status`) |
| `GET` | `/api/suspicious` | Suspicious activity logs (loitering, velocity anomalies) |
| `GET` | `/api/blockchain/ledger` | Full blockchain audit ledger |
| `GET` | `/api/blockchain/verify` | Cryptographic integrity verification of the ledger |
| `POST` | `/api/llm/sitrep` | Generate an AI military situation report |
| `GET` | `/video_feed` | Live MJPEG surveillance stream |

---

## Testing

Run the full test suite (54 tests):

```bash
python -m unittest discover -s tests
```

Test modules:
- **`test_engine.py`** — Alert engine: fence crossing, deduplication, throttling, track persistence
- **`test_anpr.py`** — ANPR: plate normalization, classical CV detector, OCR preprocessing, tracker
- **`test_anpr_pipeline_integration.py`** — End-to-end: worker thread → tracker → DB → JSON evidence path
- **`test_channels.py`** — Console, JSON, Log, and Webhook notification channels
- **`test_config.py`** — Settings validation, JSON loading, CLI precedence

---

## Module Reference

| Module | Purpose |
|---|---|
| [`config.py`](src/config.py) | Centralized `Settings` dataclass with validation, CLI parser, and JSON config loader |
| [`models.py`](src/models.py) | Immutable data models: `Detection`, `TrackState`, `SecurityEvent`, `SecurityAlert`, `PlateReading` |
| [`alerts.py`](src/alerts.py) | `AlertEngine` — per-frame fence crossing detection, observation verification, dedup, cooldown |
| [`anpr.py`](src/anpr.py) | ANPR pipeline — plate ROI detection via contour heuristics, CLAHE preprocessing, EasyOCR, registry lookup |
| [`database.py`](src/database.py) | `Database` class — SQLite with WAL mode, schema migration, event/alert CRUD |
| [`channels.py`](src/channels.py) | `AlertChannel` protocol + `ConsoleChannel`, `JsonChannel`, `WebhookChannel`, `LogChannel` |
| [`analytics.py`](src/analytics.py) | Night vision enhancement (CLAHE + thermal colormap), `SuspiciousActivityTracker` (loitering + velocity) |
| [`blockchain.py`](src/blockchain.py) | SHA-256 blockchain ledger — genesis block, proof-of-work mining, full chain integrity verification |
| [`server.py`](src/server.py) | FastAPI REST API, MJPEG stream, static file serving, SITREP generator |
| [`registry.py`](src/registry.py) | Vehicle whitelist CRUD (add/list) |
| [`main.py`](src/main.py) | Standalone plate-detection pipeline with HuggingFace model auto-download |
| [`detect.py`](src/detect.py) | Legacy detection script — direct execution with hardcoded config |

---

## License

This project was built for the **Smart India Hackathon (SIH)** under the CYPHER AI border surveillance initiative.

---

<p align="center">
  <strong>IBVAP</strong> — AI-Powered Border Security. Built with 🇮🇳 for a safer nation.
</p>
