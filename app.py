"""
app.py
AI Obstacle Assistance:
camera -> Roboflow -> ultrasonic distance -> approach/risk fusion -> voice.
"""

import logging
import os
import time
from threading import Lock, Thread

import cv2
from flask import Flask, Response, jsonify, render_template

import config
import risk_engine
from alerts import alert_log
from camera import CameraStream
from distance_sensor import DistanceSensor
from roboflow_detector import RoboflowDetector
from voice import VoiceAnnouncer
from agent import GeminiAgent
from wake_word import WakeWordAssistant

os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("obstacle_assistance.app")

app = Flask(__name__)

camera_stream = CameraStream()
distance_sensor = DistanceSensor()
detector = RoboflowDetector(camera_stream)
voice = VoiceAnnouncer()
agent = GeminiAgent(history_limit=config.GEMINI_HISTORY_LIMIT)

_state_lock = Lock()
_latest_state = {
    "object": None,
    "confidence": 0.0,
    "distance": None,
    "risk": risk_engine.RISK_UNKNOWN,
    "approaching": False,
    "danger_object": None,
    "risk_level": risk_engine.RISK_UNKNOWN,
    "risk_score": 0.0,
    "approach_speed": None,
    "ttc": None,
    "direction": None,
    "distance_source": None,
    "objects": [],
}

_risk_engine = risk_engine.RiskEngine()


def assistant_context():
    """Return a compact snapshot for Gemini scene questions."""
    with _state_lock:
        state = dict(_latest_state)

    detections = detector.get_latest_detections()
    labels = []
    for item in detections:
        label = item.get("class")
        if label and label not in labels:
            labels.append(label)

    lines = [
        f"Primary object: {state.get('object') or 'none'}",
        f"Confidence: {state.get('confidence', 0):.2f}",
        f"Distance: {state.get('distance')} cm "
        f"(source: {state.get('distance_source') or 'unavailable'})",
        f"Risk: {state.get('risk', 'UNKNOWN')}",
        f"Approaching: {bool(state.get('approaching'))}",
        f"Camera detections: {', '.join(labels) if labels else 'none'}",
    ]
    return "\n".join(lines)


wake_assistant = WakeWordAssistant(
    agent=agent,
    voice=voice,
    context_provider=assistant_context,
)


def fusion_loop():
    logger.info("Fusion loop started")
    last_detection_signature = None
    last_top_signature = None
    last_logged_score = None

    while True:
        try:
            now = time.monotonic()
            distance = distance_sensor.get_distance()
            if distance is None or distance < 0:
                distance = None
            frame = camera_stream.get_frame()
            frame_width = frame.shape[1] if frame is not None else 0
            frame_height = frame.shape[0] if frame is not None else 0
            detections = detector.get_latest_detections()
            inference_at = detector.latest_inference_at
            if not inference_at or time.time() - inference_at > config.DETECTION_STALE_SEC:
                detections = []
            detection_signature = tuple(sorted(
                item.get("class", "") for item in detections
                if item.get("class")
            ))
            if detection_signature != last_detection_signature:
                logger.info(
                    "[SAFETY] Objects detected: count=%d classes=%s",
                    len(detection_signature),
                    ", ".join(detection_signature) if detection_signature else "none",
                )
                last_detection_signature = detection_signature

            result, scored_objects = _risk_engine.evaluate(
                detections,
                distance,
                frame_width,
                frame_height,
                now=now,
            )
            if result is None:
                state = {
                    "object": None,
                    "confidence": 0.0,
                    "distance": None,
                    "risk": risk_engine.RISK_SAFE,
                    "approaching": False,
                    "danger_object": None,
                    "risk_level": risk_engine.RISK_SAFE,
                    "risk_score": 0.0,
                    "approach_speed": None,
                    "ttc": None,
                    "direction": None,
                    "distance_source": None,
                    "distance_change": None,
                    "box_area": None,
                    "box_growth": None,
                    "objects": [],
                }
                voice.update_danger(None)
            else:
                approaching = (
                    result["approach_speed"] is not None and
                    result["approach_speed"] > 0
                )
                state = {
                    **result,
                    "risk_level": result["risk"],
                    "danger_object": result["object"],
                    "approaching": approaching,
                    "objects": scored_objects,
                }
                danger_key = (result["track_id"], result["object"].lower())
                if (
                    result["risk"] == risk_engine.RISK_SAFE or
                    not result["blocking_path"]
                ):
                    voice.update_danger(None, risk=result["risk"])
                elif result["risk"] in (
                    risk_engine.RISK_WATCH,
                    risk_engine.RISK_WARNING,
                ):
                    voice.update_danger(danger_key, risk=result["risk"])

                if result["blocking_path"] and result["risk"] in (
                    risk_engine.RISK_WARNING,
                    risk_engine.RISK_HIGH,
                    risk_engine.RISK_CRITICAL,
                ):
                    spoken = voice.announce(
                        result["object"],
                        result["distance"],
                        result["risk"],
                        direction=result["direction"],
                        approach_speed=result["approach_speed"],
                        ttc=result["ttc"],
                        risk_score=result["risk_score"],
                        track_id=result["track_id"],
                        blocking_path=result["blocking_path"],
                    )
                    if spoken:
                        alert_log.add(
                            result["object"],
                            result["distance"],
                            result["risk"],
                            direction=result["direction"],
                            risk_score=result["risk_score"],
                            ttc=result["ttc"],
                        )
                else:
                    spoken = False

            with _state_lock:
                _latest_state.clear()
                _latest_state.update(state)

            if result is not None:
                top_signature = (result["track_id"], result["risk"])
                score_changed = (
                    last_logged_score is None or
                    result["risk_score"] - last_logged_score >=
                    config.RISK_CHANGE_REANNOUNCE_DELTA
                )
                if top_signature != last_top_signature or score_changed:
                    logger.info(
                        "[SAFETY] Highest risk object: %s | "
                        "[SAFETY] Risk score: %.3f | level=%s | "
                        "distance=%.1f cm (%s) | direction=%s | speed=%s cm/s | TTC=%s",
                        result["object"],
                        result["risk_score"],
                        result["risk"],
                        result["distance"],
                        result["distance_source"],
                        result["direction"],
                        result["approach_speed"],
                        result["ttc"],
                    )
                    last_top_signature = top_signature
                    last_logged_score = result["risk_score"]
            else:
                last_top_signature = None
                last_logged_score = None

        except Exception:
            logger.exception("Fusion loop error")

        time.sleep(0.2)


Thread(target=fusion_loop, daemon=True).start()
wake_assistant.start()


def generate_video_frames():
    while True:
        frame = detector.get_annotated_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buffer.tobytes()
            + b"\r\n"
        )
        time.sleep(1 / 20.0)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_video_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "camera": camera_stream.connected,
        "arduino": distance_sensor.connected,
        "roboflow": detector.connected,
        "test_mode": config.TEST_MODE,
        "roboflow_error": detector.last_error,
    })


@app.route("/api/detection")
def api_detection():
    with _state_lock:
        state = dict(_latest_state)

    return jsonify({
        "object": state["object"],
        "confidence": state["confidence"],
        "distance": state["distance"],
        "risk": state["risk"],
        "approaching": state["approaching"],
        "danger_object": state["danger_object"],
        "risk_level": state["risk_level"],
        "risk_score": state["risk_score"],
        "approach_speed": state["approach_speed"],
        "ttc": state["ttc"],
        "direction": state["direction"],
        "movement_direction": state.get("movement_direction"),
        "path_overlap": state.get("path_overlap", False),
        "blocking_path": state.get("blocking_path", False),
        "distance_source": state["distance_source"],
        "distance_change": state.get("distance_change"),
        "box_area": state.get("box_area"),
        "box_growth": state.get("box_growth"),
        "objects": state["objects"],
    })


@app.route("/api/distance")
def api_distance():
    return jsonify({
        "distance": distance_sensor.get_distance(),
        "arduino_connected": distance_sensor.connected,
    })


@app.route("/api/diagnostics")
def api_diagnostics():
    return jsonify({
        "camera_connected": camera_stream.connected,
        "arduino_connected": distance_sensor.connected,
        "distance_cm": distance_sensor.get_distance(),
        "roboflow_connected": detector.connected,
        "roboflow_model": config.ROBOFLOW_MODEL_ID,
        "roboflow_api_url": config.ROBOFLOW_API_URL,
        "roboflow_error": detector.last_error,
        "camera_source": config.CAMERA_SOURCE,
        "camera_index": config.LAPTOP_CAM_INDEX,
        "arduino_port": config.ARDUINO_PORT,
        "confidence_threshold": config.CONFIDENCE_THRESHOLD,
        "voice_enabled": config.VOICE_ENABLED,
        "near_distance_cm": config.NEAR_DISTANCE_MAX,
        "approach_window_sec": config.APPROACH_WINDOW_SEC,
        "approach_min_change_cm": config.APPROACH_MIN_CHANGE_CM,
        "risk_weights": config.RISK_WEIGHTS,
        "risk_thresholds": {
            "watch": config.RISK_WATCH_THRESHOLD,
            "warning": config.RISK_WARNING_THRESHOLD,
            "high": config.RISK_HIGH_THRESHOLD,
            "critical": config.RISK_CRITICAL_THRESHOLD,
        },
        "camera_distance_estimate": {
            "reference_distance_cm": config.CAMERA_REFERENCE_DISTANCE_CM,
            "reference_height_ratio": config.CAMERA_REFERENCE_HEIGHT_RATIO,
        },
    })


@app.route("/api/alerts")
def api_alerts():
    return jsonify({"alerts": alert_log.recent()})


@app.route("/api/assistant", methods=["POST"])
def api_assistant():
    from flask import request
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    context = assistant_context() if agent.is_scene_question(question) else ""
    answer = agent.ask(question, context)
    voice.speak_text(answer)
    return jsonify({
        "answer": answer,
        "gemini_configured": agent.configured,
        "gemini_connected": agent.connected,
        "error": agent.last_error,
    })


@app.route("/api/assistant/status")
def api_assistant_status():
    return jsonify({
        "gemini_configured": agent.configured,
        "gemini_connected": agent.connected,
        "gemini_model": config.GEMINI_MODEL,
        "wake_word_enabled": config.WAKEWORD_ENABLED,
        "wake_word_running": wake_assistant.running,
        "wake_word_model": config.WAKEWORD_MODEL,
        "error": agent.last_error,
    })


if __name__ == "__main__":
    logger.info(
        "Starting AI Obstacle Assistance | TEST_MODE=%s | camera=%s | model=%s",
        config.TEST_MODE, config.CAMERA_SOURCE, config.ROBOFLOW_MODEL_ID
    )
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        threaded=True,
    )
