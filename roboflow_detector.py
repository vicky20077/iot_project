"""
roboflow_detector.py
Roboflow object detection for the live camera.

The detector keeps ALL confident predictions so the fusion layer can choose
the object closest to the ultrasonic sensor's center line.  This matters
because the HC-SR04 is a single forward-facing distance sensor; its reading
cannot be reliably associated with a random highest-confidence object at the
edge of the camera frame.
"""

import logging
import threading
import time

import cv2
import config

logger = logging.getLogger("obstacle_assistance.roboflow")


class RoboflowDetector:
    def __init__(self, camera_stream, api_key=None, model_id=None,
                 inference_fps=None, test_mode=None):
        self.camera_stream = camera_stream
        self.api_key = config.ROBOFLOW_API_KEY if api_key is None else api_key
        self.model_id = config.ROBOFLOW_MODEL_ID if model_id is None else model_id
        self.inference_fps = config.INFERENCE_FPS if inference_fps is None else inference_fps
        self.test_mode = config.TEST_MODE if test_mode is None else test_mode

        self._client = None
        self._connected = False
        self._last_error = None
        self._latest_detections = []
        self._latest_annotated_frame = None
        self._latest_inference_at = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        if not self.test_mode:
            self._init_client()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def connected(self):
        with self._lock:
            return self._connected

    @property
    def last_error(self):
        with self._lock:
            return self._last_error

    @property
    def latest_inference_at(self):
        with self._lock:
            return self._latest_inference_at

    def get_latest_detections(self):
        with self._lock:
            return [dict(d) for d in self._latest_detections]

    def get_latest_detection(self):
        """Compatibility helper: highest-confidence prediction."""
        detections = self.get_latest_detections()
        return max(detections, key=lambda d: d.get("confidence", 0), default=None)

    def get_detection_for_ultrasonic(self, frame_width):
        """
        Prefer a confident detection near the horizontal center of the camera,
        because the ultrasonic sensor is normally mounted pointing forward.
        """
        detections = self.get_latest_detections()
        if not detections or frame_width <= 0:
            return None

        center_x = frame_width / 2.0
        tolerance = config.ULTRASONIC_CENTER_TOLERANCE * frame_width

        candidates = []
        for d in detections:
            x1, _, x2, _ = d["box"]
            box_center = (x1 + x2) / 2.0
            offset = abs(box_center - center_x)
            if offset <= tolerance:
                # Strong preference for confidence, with a smaller preference
                # for being on the ultrasonic center line.
                center_score = 1.0 - (offset / max(tolerance, 1.0))
                score = 0.75 * d["confidence"] + 0.25 * center_score
                candidates.append((score, d))

        if candidates:
            return max(candidates, key=lambda x: x[0])[1]

        # No central object: do not pretend an edge object is paired with the
        # ultrasonic reading. The dashboard can still show the best detection.
        return None

    def get_annotated_frame(self):
        with self._lock:
            if self._latest_annotated_frame is not None:
                return self._latest_annotated_frame.copy()
        return self.camera_stream.get_frame()

    def shutdown(self):
        self._stop_event.set()

    def _init_client(self):
        if not self.api_key:
            with self._lock:
                self._connected = False
                self._last_error = "ROBOFLOW_API_KEY is empty"
            logger.error("ROBOFLOW_API_KEY is empty.")
            return

        try:
            from inference_sdk import InferenceHTTPClient
            self._client = InferenceHTTPClient(
                api_url=config.ROBOFLOW_API_URL,
                api_key=self.api_key,
            )
            with self._lock:
                self._connected = True
                self._last_error = None
            logger.info("Roboflow client initialized: %s / %s",
                        config.ROBOFLOW_API_URL, self.model_id)
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = str(exc)
            logger.exception("Failed to initialize Roboflow client")

    def _run(self):
        interval = 1.0 / max(self.inference_fps, 0.1)
        while not self._stop_event.is_set():
            start = time.time()
            frame = self.camera_stream.get_frame()

            if frame is None:
                time.sleep(interval)
                continue

            if self.test_mode:
                self._simulate_inference(frame)
            else:
                self._run_inference(frame)

            elapsed = time.time() - start
            time.sleep(max(0.0, interval - elapsed))

    def _resize_for_inference(self, frame):
        h, w = frame.shape[:2]
        target_w = config.FRAME_RESIZE_WIDTH
        if w <= target_w:
            return frame, 1.0
        scale = target_w / float(w)
        resized = cv2.resize(frame, (target_w, int(h * scale)))
        return resized, scale

    def _run_inference(self, frame):
        if self._client is None:
            with self._lock:
                self._latest_annotated_frame = frame
                self._latest_detections = []
            return

        try:
            resized, scale = self._resize_for_inference(frame)
            result = self._client.infer(resized, model_id=self.model_id)

            if not isinstance(result, dict):
                raise RuntimeError(f"Unexpected Roboflow response type: {type(result).__name__}")

            predictions = result.get("predictions", [])
            if not isinstance(predictions, list):
                predictions = []

            inv = 1.0 / scale if scale else 1.0
            detections = []

            for pred in predictions:
                try:
                    confidence = float(pred.get("confidence", 0))
                except (TypeError, ValueError):
                    continue

                if confidence < config.CONFIDENCE_THRESHOLD:
                    continue

                class_name = str(pred.get("class", "Unknown")).strip()
                cx = float(pred.get("x", 0))
                cy = float(pred.get("y", 0))
                bw = float(pred.get("width", 0))
                bh = float(pred.get("height", 0))

                x1 = max(0, int((cx - bw / 2) * inv))
                y1 = max(0, int((cy - bh / 2) * inv))
                x2 = min(frame.shape[1] - 1, int((cx + bw / 2) * inv))
                y2 = min(frame.shape[0] - 1, int((cy + bh / 2) * inv))

                detections.append({
                    "class": class_name,
                    "confidence": confidence,
                    "box": (x1, y1, x2, y2),
                })

            annotated = self._draw_boxes(frame.copy(), detections)

            with self._lock:
                self._connected = True
                self._last_error = None
                self._latest_detections = detections
                self._latest_annotated_frame = annotated
                self._latest_inference_at = time.time()

        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = str(exc)
                self._latest_annotated_frame = frame
                self._latest_detections = []
            logger.warning("Roboflow inference failed: %s", exc)

    def _simulate_inference(self, frame):
        import math
        t = time.time()
        classes = config.VALID_CLASSES
        idx = int(t / 6) % len(classes)
        class_name = classes[idx]
        confidence = 0.75 + 0.2 * abs(math.sin(t))
        h, w = frame.shape[:2]
        box = (int(w * 0.35), int(h * 0.3), int(w * 0.65), int(h * 0.75))
        detections = [{"class": class_name, "confidence": confidence, "box": box}]
        annotated = self._draw_boxes(frame.copy(), detections)
        with self._lock:
            self._connected = True
            self._last_error = None
            self._latest_detections = detections
            self._latest_annotated_frame = annotated
            self._latest_inference_at = time.time()

    @staticmethod
    def _draw_boxes(frame, detections):
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            label = f'{det["class"]} {det["confidence"]*100:.0f}%'
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(
                frame, (x1, max(0, y1 - th - 10)),
                (x1 + tw + 6, y1), (0, 200, 255), -1
            )
            cv2.putText(
                frame, label, (x1 + 3, max(15, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2
            )
        return frame
