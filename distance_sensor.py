"""
distance_sensor.py
Reads HC-SR04 distance values from Arduino UNO over serial.

Expected Arduino output:
    DISTANCE:75.4
    DISTANCE:-1
"""

import logging
import re
import threading
import time

import config

logger = logging.getLogger("obstacle_assistance.distance")

_LINE_RE = re.compile(r"DISTANCE\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)


class DistanceSensor:
    def __init__(self, port=None, baudrate=None, timeout=None, test_mode=None):
        self.port = config.ARDUINO_PORT if port is None else port
        self.baudrate = config.ARDUINO_BAUDRATE if baudrate is None else baudrate
        self.timeout = config.ARDUINO_TIMEOUT if timeout is None else timeout
        self.test_mode = config.TEST_MODE if test_mode is None else test_mode

        self._serial = None
        self._connected = False
        self._latest_distance = -1.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def connected(self):
        with self._lock:
            return self._connected

    def get_distance(self):
        with self._lock:
            return self._latest_distance

    def shutdown(self):
        self._stop_event.set()
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass

    def _run(self):
        if self.test_mode:
            self._run_test_mode()
        else:
            self._run_hardware_mode()

    def _run_test_mode(self):
        import math
        logger.info("DistanceSensor TEST_MODE")
        with self._lock:
            self._connected = True

        t0 = time.time()
        while not self._stop_event.is_set():
            elapsed = time.time() - t0
            simulated = 90 + 70 * math.sin(elapsed / 3.0)
            with self._lock:
                self._latest_distance = max(5.0, simulated)
            time.sleep(0.15)

    def _run_hardware_mode(self):
        try:
            import serial
        except ImportError:
            logger.error("pyserial is not installed")
            return

        while not self._stop_event.is_set():
            try:
                logger.info("Opening Arduino serial port %s at %s baud",
                            self.port, self.baudrate)
                self._serial = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=self.timeout,
                )

                # Opening an UNO normally resets it. Give setup() time to run
                # and discard stale boot bytes.
                time.sleep(2)
                try:
                    self._serial.reset_input_buffer()
                except Exception:
                    pass

                with self._lock:
                    self._connected = True
                    self._latest_distance = -1.0

                logger.info("Arduino connected on %s", self.port)
                self._read_loop()

            except Exception as exc:
                with self._lock:
                    self._connected = False
                    self._latest_distance = -1.0

                logger.warning(
                    "Arduino unavailable on %s: %s. Retrying in 3s...",
                    self.port, exc
                )

                try:
                    if self._serial is not None:
                        self._serial.close()
                except Exception:
                    pass

                time.sleep(3)

    def _read_loop(self):
        while not self._stop_event.is_set():
            try:
                raw = self._serial.readline().decode(
                    "utf-8", errors="ignore"
                ).strip()
            except Exception as exc:
                logger.warning("Arduino serial read error: %s", exc)
                with self._lock:
                    self._connected = False
                return

            if not raw:
                continue

            match = _LINE_RE.search(raw)
            if not match:
                logger.debug("Ignoring Arduino line: %r", raw)
                continue

            try:
                value = float(match.group(1))
            except ValueError:
                continue

            if value < 0:
                distance = -1.0
            elif 2 <= value <= 500:
                distance = value
            else:
                distance = -1.0

            with self._lock:
                self._latest_distance = distance
