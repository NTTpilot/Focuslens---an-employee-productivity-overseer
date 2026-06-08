"""
CameraThread  –  grabs frames from the webcam in a background thread
and makes the latest frame available to the GUI via a thread-safe queue.
"""

import threading
import queue
import time
import cv2

from config import CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS


class CameraThread(threading.Thread):
    """
    Runs as a daemon thread.  Call start(), then read frames from .frame_queue.
    Each item in the queue is a BGR numpy array.
    Call stop() to shut down cleanly.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.frame_queue: queue.Queue = queue.Queue(maxsize=2)
        self._stop_event = threading.Event()
        self.fps_actual: float = 0.0
        self._cap: cv2.VideoCapture | None = None
        self.error: str | None = None

    # public API

    def stop(self):
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    # thread body

    def run(self):
        self._cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self.error = "Could not open camera. Check index in config.py."
            return

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS,          CAMERA_FPS)

        frame_count = 0
        t_start = time.perf_counter()

        while not self._stop_event.is_set():
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # drop stale frames 
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass

            self.frame_queue.put(frame)

            frame_count += 1
            elapsed = time.perf_counter() - t_start
            if elapsed >= 1.0:
                self.fps_actual = frame_count / elapsed
                frame_count = 0
                t_start = time.perf_counter()

        self._cap.release()
