# FocusLens

Emotion-aware productivity tracker. Monitors your webcam in the background,
detects focus state in real time, and generates a report of your productive hours.

## Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py
```

## Project Structure

```
focuslens/
├── main.py          – entry point
├── app.py           – GUI (tkinter)
├── config.py        – all tunable settings
├── requirements.txt
├── core/
│   ├── camera.py    – webcam capture thread
│   ├── detector.py  – MediaPipe face detection
│   └── logger.py    – session logging to CSV
├── models/          – emotion model weights go here (Stage 2)
└── sessions/        – saved session data (auto-created)
```

## Build Stages

| Stage | Status | What it adds |
|-------|--------|-------------|
| 1 | ✅ done | GUI shell, webcam feed, face detection, session logging |
| 2 | next   | Emotion classification model (EfficientNet fine-tuned) |
| 3 | later  | Fine-tuning pipeline on your own labelled data |
| 4 | later  | Calibration & threshold tuning per user |
| 5 | later  | PDF/HTML session report with charts |

## Configuration

Edit `config.py` to change:
- `CAMERA_INDEX` – if you have multiple cameras, try 1, 2, etc.
- `FACE_MIN_DETECTION_CONFIDENCE` – raise for fewer false positives
- `LOG_INTERVAL_S` – how often a state snapshot is saved (default: 1s)
- `EMOTION_TO_STATE` – which raw emotions map to focused/distracted

## Session Data

Each session is saved to `sessions/<timestamp>/`:
- `log.csv` – raw per-second state log
- `summary.json` – computed at session end (focus %, productive hours, etc.)

## planned content
- integrating a model that actually decides whether an employee is focused while on the desk or just going through the motions.