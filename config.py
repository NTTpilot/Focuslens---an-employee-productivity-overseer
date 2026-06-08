"""
FocusLens configuration constants.
Edit these to tune detection behaviour.
"""

# Window
WINDOW_TITLE   = "FocusLens"
WINDOW_WIDTH   = 1060
WINDOW_HEIGHT  = 680
WINDOW_BG      = "#0d0f12"

# Camera
CAMERA_INDEX   = 0
CAMERA_WIDTH   = 640
CAMERA_HEIGHT  = 480
CAMERA_FPS     = 30

# Face detection
FACE_MIN_DETECTION_CONFIDENCE = 0.6

# Focus mapping (populated in Stage 2 with real emotions)
# Maps raw emotion label → focus state
EMOTION_TO_STATE = {
    "neutral":    "focused",
    "happy":      "focused",
    "surprise":   "focused",
    "sad":        "distracted",
    "angry":      "distracted",
    "fear":       "distracted",
    "disgust":    "distracted",
    "no_face":    "away",
}

# Session logging
SESSIONS_DIR   = "sessions"
LOG_INTERVAL_S = 1          # log a state snapshot every N seconds

# Colours
COL_BG         = "#0d0f12"
COL_SURFACE    = "#13161b"
COL_BORDER     = "#1f2328"
COL_TEXT       = "#e2e4e8"
COL_MUTED      = "#5a6070"
COL_ACCENT     = "#00e5a0"   # focused / active
COL_WARN       = "#f59e0b"   # distracted
COL_DANGER     = "#ef4444"   # away / no face
COL_PURPLE     = "#a78bfa"   # neutral highlight

# Timeline segment colours (match above)
STATE_COLOURS  = {
    "focused":    COL_ACCENT,
    "distracted": COL_WARN,
    "away":       "#2a2f38",
}
STATE_ICONS    = {
    "focused":    "🎯",
    "distracted": "😵",
    "away":       "👤",
    "idle":       "⏸",
}
