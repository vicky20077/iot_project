"""Queued voice alerts and conversational speech on one persistent TTS worker."""

import logging
import queue
import threading
import time

import config

logger = logging.getLogger("obstacle_assistance.voice")


class VoiceAnnouncer:
    def __init__(self, cooldown=None, rate=None, enabled=None):
        self.cooldown = config.VOICE_COOLDOWN if cooldown is None else cooldown
        self.rate = config.VOICE_RATE if rate is None else rate
        self.enabled = config.VOICE_ENABLED if enabled is None else enabled

        self._queue = queue.Queue(maxsize=20)
        self._engine = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_danger = None
        self._last_queued_at = 0.0
        self._last_announced_score = None
        self._last_announced_risk = None
        self._active_risk = None

        self._worker = threading.Thread(
            target=self._run,
            name="persistent-tts-worker",
            daemon=True,
        )
        self._worker.start()

    def _init_engine(self):
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        self._engine = engine

    def _run(self):
        logger.info("[VOICE] Worker started")
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            text, done_event = item
            try:
                logger.info("[VOICE] Speaking: %s", text)
                if not self.enabled:
                    logger.info("[VOICE] TTS disabled; speech skipped")
                else:
                    if self._engine is None:
                        self._init_engine()
                    self._engine.say(text)
                    self._engine.runAndWait()
                logger.info("[VOICE] Completed: %s", text)
            except Exception as exc:
                logger.exception("[VOICE] Error: %s", exc)
                self._engine = None
            finally:
                if done_event is not None:
                    done_event.set()
                self._queue.task_done()

    @staticmethod
    def build_message(object_name, distance, direction, approach_speed, ttc,
                      risk):
        direction_text = {
            "left": "to your left",
            "right": "to your right",
            "center": "ahead",
        }.get(direction, "ahead")
        if risk == "CRITICAL":
            return f"Critical. {object_name} {direction_text}. Stop."
        return f"Warning. {object_name} {direction_text}."

    def update_danger(self, danger, risk=None):
        """Update the selected danger without extending speech to lower-risk objects."""
        with self._lock:
            if danger != self._active_danger:
                self._active_danger = danger
                self._last_announced_score = None
                self._last_announced_risk = None
            self._active_risk = risk

    def announce(self, object_name, distance, risk, direction=None,
                 approach_speed=None, ttc=None, risk_score=0.0, track_id=None,
                 blocking_path=False):
        if (
            not object_name or
            str(object_name).strip().casefold() == "person" or
            not blocking_path or
            risk not in ("WARNING", "HIGH", "CRITICAL")
        ):
            return False

        danger = (track_id, object_name.lower())
        now = time.monotonic()
        with self._lock:
            if danger != self._active_danger:
                self._active_danger = danger
                self._last_announced_score = None
                self._last_announced_risk = None
                self._active_risk = None

            previous_active_risk = self._active_risk
            danger_changed = self._last_announced_score is None
            meaningfully_increased = (
                self._last_announced_score is not None and
                risk_score - self._last_announced_score >= config.RISK_CHANGE_REANNOUNCE_DELTA
            )
            became_alert_worthy = (
                risk in ("WARNING", "HIGH", "CRITICAL") and
                previous_active_risk not in ("WARNING", "HIGH", "CRITICAL")
            )
            became_critical = (
                risk == "CRITICAL" and
                (previous_active_risk != "CRITICAL" or self._last_announced_risk != "CRITICAL")
            )
            if not (
                danger_changed or meaningfully_increased or
                became_alert_worthy or became_critical
            ):
                return False
            cooldown_active = (
                self._last_queued_at and now - self._last_queued_at < self.cooldown
            )
            if cooldown_active and not (danger_changed or became_critical):
                return False

            message = self.build_message(
                object_name, distance, direction, approach_speed, ttc, risk
            )
            try:
                self._queue.put_nowait((message, None))
            except queue.Full:
                logger.error("[VOICE] Alert queue full; failed to queue: %s", message)
                return False

            self._last_queued_at = now
            self._last_announced_score = risk_score
            self._last_announced_risk = risk
            self._active_risk = risk
            logger.info("[VOICE] Alert queued: %s", message)
            return True

    def speak_text(self, text, wait=False):
        """Queue conversational speech without blocking the detection loop."""
        text = (text or "").strip()
        if not text:
            return False

        done_event = threading.Event() if wait else None
        try:
            self._queue.put_nowait((text, done_event))
        except queue.Full:
            logger.error("[VOICE] Queue full; conversational speech not queued")
            return False

        if done_event is not None:
            done_event.wait(timeout=max(2.0, len(text) / 8.0 + 5.0))
        return True

    def shutdown(self):
        self._stop_event.set()
