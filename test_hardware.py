"""
Quick hardware checks.

Run:
    py test_hardware.py

This does NOT require Flask or Roboflow. It checks:
1) webcam index 0 can open
2) Arduino COM port can be opened and prints DISTANCE values
"""

import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

camera_index = int(os.getenv("LAPTOP_CAM_INDEX", "0"))
arduino_port = os.getenv("ARDUINO_PORT", "COM3")
baud = int(os.getenv("ARDUINO_BAUDRATE", "9600"))

print("\n=== CAMERA TEST ===")
try:
    import cv2
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if cap.isOpened():
        ok, frame = cap.read()
        print("Camera opened:", ok, "shape:", getattr(frame, "shape", None))
    else:
        print("Camera FAILED to open. Try LAPTOP_CAM_INDEX=1 or 2.")
    cap.release()
except Exception as e:
    print("Camera error:", e)

print("\n=== ARDUINO / ULTRASONIC TEST ===")
try:
    import serial
    ser = serial.Serial(arduino_port, baud, timeout=1)
    time.sleep(2)
    print(f"Arduino opened on {arduino_port}. Reading for 5 seconds...")
    deadline = time.time() + 5
    pattern = re.compile(r"DISTANCE\s*:\s*(-?\d+(?:\.\d+)?)")
    count = 0
    while time.time() < deadline:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        print("Arduino:", line)
        if pattern.search(line):
            count += 1
    ser.close()
    print("Valid DISTANCE lines:", count)
    if count == 0:
        print("No distance data. Check TRIG=D10, ECHO=D9, 5V, GND and sketch upload.")
except Exception as e:
    print("Arduino error:", e)

print("\nIf both tests pass, run: py app.py")
