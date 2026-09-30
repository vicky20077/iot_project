"""
config.py
Central configuration for the AI Obstacle Assistance system.
All secrets/environment-specific values come from .env (never hardcoded).
"""

import math
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_float_map(name, default):
    values = dict(default)
    for entry in os.getenv(name, "").split(","):
        if not entry.strip():
            continue
        try:
            key, value = entry.split(":", 1)
            values[key.strip().lower()] = float(value)
        except (TypeError, ValueError):
            continue
    return values


# ---------------------------------------------------------------------------
# Core mode
# ---------------------------------------------------------------------------
TEST_MODE = _get_bool("TEST_MODE", False)

# ---------------------------------------------------------------------------
# Roboflow
# ---------------------------------------------------------------------------
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
ROBOFLOW_MODEL_ID = os.getenv("ROBOFLOW_MODEL_ID", "forblind-p23lj/1")
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")

# ---------------------------------------------------------------------------
# Camera source
# ---------------------------------------------------------------------------
# "esp32"  -> read MJPEG stream from the ESP32-CAM over WiFi (default target hardware)
# "laptop" -> read the PC's built-in/USB webcam via OpenCV (useful when the
#             ESP32-CAM can't be powered, e.g. during development/testing)
CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "esp32").strip().lower()
LAPTOP_CAM_INDEX = _get_int("LAPTOP_CAM_INDEX", 0)

ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://192.168.1.100:81/stream")

# ---------------------------------------------------------------------------
# Arduino / Serial
# ---------------------------------------------------------------------------
ARDUINO_PORT = os.getenv("ARDUINO_PORT", "COM3")
ARDUINO_BAUDRATE = _get_int("ARDUINO_BAUDRATE", 9600)
ARDUINO_TIMEOUT = _get_float("ARDUINO_TIMEOUT", 1.0)

# ---------------------------------------------------------------------------
# Detection / inference tuning
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = _get_float("CONFIDENCE_THRESHOLD", 0.50)
INFERENCE_FPS = _get_float("INFERENCE_FPS", 3.0)          # inference frames per second
FRAME_RESIZE_WIDTH = _get_int("FRAME_RESIZE_WIDTH", 640)  # resize before sending to Roboflow

VALID_CLASSES = ["Chair", "Table", "Person", "Stairs"]

# ---------------------------------------------------------------------------
# Risk / distance zones (centimeters)
# ---------------------------------------------------------------------------
DISTANCE_CRITICAL_MAX = _get_float("DISTANCE_CRITICAL_MAX", 30)
DISTANCE_HIGH_MAX = _get_float("DISTANCE_HIGH_MAX", 60)
DISTANCE_MEDIUM_MAX = _get_float("DISTANCE_MEDIUM_MAX", 100)
DISTANCE_RISK_RANGE_CM = _get_float("DISTANCE_RISK_RANGE_CM", 200)
CAMERA_REFERENCE_DISTANCE_CM = _get_float("CAMERA_REFERENCE_DISTANCE_CM", 70)
CAMERA_REFERENCE_HEIGHT_RATIO = _get_float("CAMERA_REFERENCE_HEIGHT_RATIO", 0.35)
CAMERA_DISTANCE_MIN_CM = _get_float("CAMERA_DISTANCE_MIN_CM", 20)
CAMERA_DISTANCE_MAX_CM = _get_float("CAMERA_DISTANCE_MAX_CM", 500)
BOX_AREA_RISK_MAX = _get_float("BOX_AREA_RISK_MAX", 0.35)
TTC_RISK_HORIZON_SEC = _get_float("TTC_RISK_HORIZON_SEC", 5)
TRACK_MAX_GAP_SEC = _get_float("TRACK_MAX_GAP_SEC", 2)
TRACK_CENTER_TOLERANCE = _get_float("TRACK_CENTER_TOLERANCE", 0.25)
RISK_WEIGHTS = {
    "object": _get_float("RISK_WEIGHT_OBJECT", 0.20),
    "distance": _get_float("RISK_WEIGHT_DISTANCE", 0.20),
    "path": _get_float("RISK_WEIGHT_PATH", 0.15),
    "obstruction": _get_float("RISK_WEIGHT_OBSTRUCTION", 0.15),
    "speed": _get_float("RISK_WEIGHT_SPEED", 0.10),
    "ttc": _get_float("RISK_WEIGHT_TTC", 0.10),
    "size": _get_float("RISK_WEIGHT_SIZE", 0.10),
}
_risk_weight_total = sum(RISK_WEIGHTS.values())
if (
    not all(math.isfinite(value) and value >= 0 for value in RISK_WEIGHTS.values())
    or _risk_weight_total <= 0
):
    raise ValueError("RISK_WEIGHT_* values must be finite, non-negative, and not all zero")
RISK_WEIGHTS = {
    key: value / _risk_weight_total
    for key, value in RISK_WEIGHTS.items()
}
RISK_WATCH_THRESHOLD = _get_float("RISK_WATCH_THRESHOLD", 0.30)
RISK_WARNING_THRESHOLD = _get_float("RISK_WARNING_THRESHOLD", 0.50)
RISK_HIGH_THRESHOLD = _get_float("RISK_HIGH_THRESHOLD", 0.70)
RISK_CRITICAL_THRESHOLD = _get_float("RISK_CRITICAL_THRESHOLD", 0.85)
OBJECT_RISK_SCORES = _get_float_map("OBJECT_RISK_SCORES", {})
FAST_APPROACH_CM_PER_SEC = _get_float("FAST_APPROACH_CM_PER_SEC", 35)
URGENT_TTC_SEC = _get_float("URGENT_TTC_SEC", 2)
RISK_CHANGE_REANNOUNCE_DELTA = _get_float("RISK_CHANGE_REANNOUNCE_DELTA", 0.15)
PATH_CORRIDOR_HALF_WIDTH = _get_float("PATH_CORRIDOR_HALF_WIDTH", 0.20)
PATH_LATERAL_MOTION_DELTA = _get_float("PATH_LATERAL_MOTION_DELTA", 0.04)
PATH_SUDDEN_ENTRY_SPEED = _get_float("PATH_SUDDEN_ENTRY_SPEED", 0.30)
VERTICAL_GROWTH_MOTION_DELTA = _get_float("VERTICAL_GROWTH_MOTION_DELTA", 0.025)
GROUND_CONTACT_START_RATIO = _get_float("GROUND_CONTACT_START_RATIO", 0.70)
OBSTRUCTION_SIZE_WEIGHT = _get_float("OBSTRUCTION_SIZE_WEIGHT", 0.45)
OBSTRUCTION_GROUND_WEIGHT = _get_float("OBSTRUCTION_GROUND_WEIGHT", 0.35)
OBSTRUCTION_ENTRY_WEIGHT = _get_float("OBSTRUCTION_ENTRY_WEIGHT", 0.20)
MAX_APPROACH_RISK_CM_PER_SEC = _get_float("MAX_APPROACH_RISK_CM_PER_SEC", 100)
BOX_GROWTH_RISK_PER_SEC = _get_float("BOX_GROWTH_RISK_PER_SEC", 0.15)
RISK_NON_PATH_MAX_SCORE = _get_float("RISK_NON_PATH_MAX_SCORE", 0.25)
BLOCKING_DISTANCE_CM = _get_float("BLOCKING_DISTANCE_CM", 120)
BLOCKING_SIZE_RISK_MIN = _get_float("BLOCKING_SIZE_RISK_MIN", 0.20)
BLOCKING_CORRIDOR_COVERAGE_MIN = _get_float("BLOCKING_CORRIDOR_COVERAGE_MIN", 0.35)
HIGH_HAZARD_RELEVANCE_DISTANCE_CM = _get_float("HIGH_HAZARD_RELEVANCE_DISTANCE_CM", 300)

# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------
VOICE_COOLDOWN = _get_float("VOICE_COOLDOWN", 3.0)          # seconds
VOICE_DISTANCE_DELTA = _get_float("VOICE_DISTANCE_DELTA", 15)  # cm change that forces a re-announce
VOICE_RATE = _get_int("VOICE_RATE", 165)
VOICE_ENABLED = _get_bool("VOICE_ENABLED", True)
# Voice should only fire for obstacles that are close or getting closer.
NEAR_DISTANCE_MAX = _get_float("NEAR_DISTANCE_MAX", 100)
APPROACH_WINDOW_SEC = _get_float("APPROACH_WINDOW_SEC", 1.5)
APPROACH_MIN_CHANGE_CM = _get_float("APPROACH_MIN_CHANGE_CM", 5)
VOICE_MIN_RISK = os.getenv("VOICE_MIN_RISK", "HIGH").strip().upper()
DETECTION_STALE_SEC = _get_float("DETECTION_STALE_SEC", 2.0)
ULTRASONIC_CENTER_TOLERANCE = _get_float("ULTRASONIC_CENTER_TOLERANCE", 0.35)

# ---------------------------------------------------------------------------
# Alerts log
# ---------------------------------------------------------------------------
MAX_ALERTS = _get_int("MAX_ALERTS", 50)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.path.join(LOG_DIR, "system.log")


# ---------------------------------------------------------------------------
# Optional Gemini conversational agent
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_HISTORY_LIMIT = _get_int("GEMINI_HISTORY_LIMIT", 8)

# ---------------------------------------------------------------------------
# Optional wake-word listener
# ---------------------------------------------------------------------------
WAKEWORD_ENABLED = _get_bool("WAKEWORD_ENABLED", True)
WAKEWORD_MODEL = os.getenv("WAKEWORD_MODEL", "hey_jarvis").strip()
WAKEWORD_THRESHOLD = _get_float("WAKEWORD_THRESHOLD", 0.55)
COMMAND_SECONDS = _get_float("COMMAND_SECONDS", 5.0)
WAKEWORD_TEMP_WAV = os.getenv("WAKEWORD_TEMP_WAV", "logs/voice_command.wav")

# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = _get_int("FLASK_PORT", 5000)
FLASK_DEBUG = _get_bool("FLASK_DEBUG", False)
