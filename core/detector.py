"""
FaceDetector  –  uses MediaPipe Tasks API (mediapipe >= 0.10)
"""

from dataclasses import dataclass
import numpy as np
import urllib.request
import os

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    _MP_AVAILABLE = True
except ImportError:
    _MP_AVAILABLE = False

from config import FACE_MIN_DETECTION_CONFIDENCE

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "blaze_face_short_range.tflite")
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"


@dataclass
class FaceResult:
    face_detected: bool
    bbox: tuple | None   # (x, y, w, h) in pixels
    confidence: float


class FaceDetector:

    def __init__(self):
        self._ready = False
        if not _MP_AVAILABLE:
            print("[FaceDetector] mediapipe not installed.")
            return

        # download model file if missing
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        if not os.path.exists(MODEL_PATH):
            print("[FaceDetector] downloading model (~800 KB)...")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            print("[FaceDetector] model downloaded.")

        options = vision.FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            min_detection_confidence=FACE_MIN_DETECTION_CONFIDENCE,
        )
        self._detector = vision.FaceDetector.create_from_options(options)
        self._ready = True

    def detect(self, frame_bgr: np.ndarray) -> FaceResult:
        if not self._ready:
            return FaceResult(face_detected=False, bbox=None, confidence=0.0)

        h, w = frame_bgr.shape[:2]
        rgb = frame_bgr[:, :, ::-1].copy()
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = self._detector.detect(mp_image)

        if not result.detections:
            return FaceResult(face_detected=False, bbox=None, confidence=0.0)

        best = max(result.detections, key=lambda d: d.categories[0].score)
        score = best.categories[0].score

        bb = best.bounding_box
        return FaceResult(
            face_detected=True,
            bbox=(bb.origin_x, bb.origin_y, bb.width, bb.height),
            confidence=score,
        )

    def close(self):
        if self._ready:
            self._detector.close()