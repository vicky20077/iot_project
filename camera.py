"""
camera.py
Reads live video into the pipeline, from one of two interchangeable
sources (set via config.CAMERA_SOURCE):

    "esp32"  -> the ESP32-CAM's MJPEG stream (http://ESP32_IP:81/stream)
    "laptop" -> the PC's own webcam, opened locally via OpenCV

Runs in a background thread so frame capture is decoupled from both AI
inference and the Flask response cycle. Reconnects automatically if the
source drops.
"""

import logging
import threading
import time

import cv2
import numpy as np

import config

logger = logging.getLogger("obstacle_assistance.camera")


class CameraStream:
    def __init__(self, stream_url=None, camera_source=None, laptop_cam_index=None, test_mode=None):
        self.stream_url = config.ESP32_STREAM_URL if stream_url is None else stream_url
        self.camera_source = config.CAMERA_SOURCE if camera_source is None else camera_source
        self.laptop_cam_index = config.LAPTOP_CAM_INDEX if laptop_cam_index is None else laptop_cam_index
        self.test_mode = config.TEST_MODE if test_mode is None else test_mode

        self._capture = None
        self._connected = False
        self._latest_frame = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def connected(self):
        with self._lock:
            return self._connected

    def get_frame(self):
        """Return the most recent BGR frame (numpy array), or None if unavailable."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def shutdown(self):
        self._stop_event.set()
        if self._capture is not None:
            self._capture.release()

    def _run(self):
        if self.test_mode:
            self._run_test_mode()
            return
        self._run_hardware_mode()

    def _run_test_mode(self):
        """Generate a synthetic placeholder frame so the dashboard/video_feed
        work without any hardware attached."""
        logger.info("CameraStream running in TEST_MODE (synthetic frames)")
        with self._lock:
            self._connected = True
        t0 = time.time()
        while not self._stop_event.is_set():
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (30, 30, 30)
            elapsed = time.time() - t0
            cv2.putText(frame, "TEST MODE - NO CAMERA CONNECTED", (30, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            cv2.putText(frame, time.strftime("%H:%M:%S"), (30, 260),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
            # a gently moving circle so it's visually obvious the feed is "live"
            x = int(320 + 200 * np.sin(elapsed))
            cv2.circle(frame, (x, 350), 20, (0, 150, 255), -1)
            with self._lock:
                self._latest_frame = frame
            time.sleep(1 / 15.0)

    def _open_capture(self):
        """Open the configured video source and return (VideoCapture, label)."""
        if self.camera_source == "laptop":
            # cv2.CAP_DSHOW opens noticeably faster and more reliably on Windows;
            # OpenCV ignores it harmlessly on platforms where it doesn't apply.
            if hasattr(cv2, "CAP_DSHOW"):
                capture = cv2.VideoCapture(self.laptop_cam_index, cv2.CAP_DSHOW)
            else:
                capture = cv2.VideoCapture(self.laptop_cam_index)
            label = f"laptop webcam (index {self.laptop_cam_index})"
        else:
            capture = cv2.VideoCapture(self.stream_url)
            label = f"ESP32-CAM stream ({self.stream_url})"
        return capture, label

    def _run_hardware_mode(self):
        while not self._stop_event.is_set():
            try:
                self._capture, label = self._open_capture()
                if not self._capture.isOpened():
                    raise ConnectionError(f"Could not open {label}")

                with self._lock:
                    self._connected = True
                logger.info("Camera connected: %s", label)

                while not self._stop_event.is_set():
                    ok, frame = self._capture.read()
                    if not ok or frame is None:
                        raise ConnectionError(f"{label} read failed")
                    with self._lock:
                        self._latest_frame = frame

            except Exception as exc:
                with self._lock:
                    self._connected = False
                    self._latest_frame = None
                if self._capture is not None:
                    self._capture.release()
                logger.warning("Camera source unavailable (%s). Retrying in 3s...", exc)
                time.sleep(3)
