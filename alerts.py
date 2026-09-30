"""
alerts.py
Stores only actual warning events, not every fusion-loop iteration.
"""

import threading
import time
from collections import deque

import config


class AlertLog:
    def __init__(self, max_alerts=None):
        self.max_alerts = config.MAX_ALERTS if max_alerts is None else max_alerts
        self._alerts = deque(maxlen=self.max_alerts)
        self._lock = threading.Lock()

    def add(self, object_name, distance, risk, direction=None,
            risk_score=None, ttc=None):
        if (
            not object_name or
            str(object_name).strip().casefold() == "person" or
            risk not in ("WARNING", "HIGH", "CRITICAL")
        ):
            return
        spoken_direction = {
            "center": "ahead",
            "left": "to your left",
            "right": "to your right",
        }.get(direction, "ahead")
        message = (
            f"Critical. {object_name} {spoken_direction}. Stop."
            if risk == "CRITICAL"
            else f"Warning. {object_name} {spoken_direction}."
        )
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
            "object": object_name,
            "distance": distance,
            "risk": risk,
            "direction": direction,
            "risk_score": risk_score,
            "ttc": ttc,
            "message": message,
        }
        with self._lock:
            self._alerts.appendleft(entry)

    def recent(self, limit=20):
        with self._lock:
            return list(self._alerts)[:limit]


alert_log = AlertLog()
