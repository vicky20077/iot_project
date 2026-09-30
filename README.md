# AI-Based Real-Time Obstacle Detection and Spatial Awareness Assistance for Visually Impaired People

> **⚠️ PROTOTYPE DISCLAIMER**
> This is a hardware + software **prototype**, not a certified medical or
> safety device. It does **not** guarantee collision prevention or reliable
> navigation for a visually impaired person. The Roboflow model only
> recognizes four object classes (**Chair, Table, Person, Stairs**) —
> any other obstacle will not be identified by name, though the ultrasonic
> sensor will still report raw distance regardless of what the object is.
> Always use this system under supervision and alongside proven mobility
> aids (cane, guide dog, trained orientation & mobility techniques).

---

## 1. Project Overview

This system combines:
- A **ESP32-CAM** streaming live video over Wi-Fi
- A **Roboflow** object-detection model (`forblind-p23lj/1`) that recognizes
  Chair, Table, Person, and Stairs
- An **Arduino UNO + HC-SR04** ultrasonic sensor measuring real-time distance
- A **Python/Flask** backend that fuses object detection + distance into a
  risk level, speaks warnings aloud, and serves a live web dashboard

Pipeline:

```
ESP32-CAM --Wi-Fi MJPEG--> Flask (OpenCV) --> Roboflow inference
                                            \
Arduino UNO --Serial(9600)--> distance ------+--> risk_engine --> voice.py (speaks)
                                            \                 \--> alerts.py (log)
                                             --> annotated video --> browser dashboard
```

---

## 2. Hardware Components

| Component | Purpose |
|---|---|
| ESP32-CAM (AI Thinker) | Live video stream over Wi-Fi |
| Arduino UNO | Reads ultrasonic sensor, drives local buzzer |
| HC-SR04 ultrasonic sensor | Distance measurement |
| Mini Mylar magnetic speaker/buzzer | Local audible alert (on Arduino) |
| Computer speakers | Spoken voice warnings (from Python/pyttsx3) |
| USB cables / FTDI programmer | Flashing ESP32-CAM and UNO |

---

## 3. Wiring

### HC-SR04 → Arduino UNO
| HC-SR04 pin | Arduino pin |
|---|---|
| VCC | 5V |
| GND | GND |
| TRIG | D10 |
| ECHO | D9 |

### Speaker/Buzzer → Arduino UNO
| Speaker pin | Arduino pin |
|---|---|
| + | D3 |
| − | GND |

### ESP32-CAM
Standard AI Thinker ESP32-CAM module. Flashing requires a USB-to-serial
(FTDI) adapter wired to GPIO0/GND during upload (see step 9).

---

## 4. Software Requirements

- **Python 3.10+** (Windows)
- **Arduino IDE** (2.x recommended) with:
  - "ESP32 by Espressif Systems" board package installed (Boards Manager)
  - AI Thinker ESP32-CAM board selected
- A **Roboflow account** and API key
- Git (optional, for cloning)

---

## 5. Python Installation (Windows)

Open **PowerShell** or **Command Prompt** in the project folder.

```powershell
py --version
```

If Python is not recognized, install it from python.org and re-open the terminal.

---

## 6. Virtual Environment Creation

```powershell
py -m venv venv
venv\Scripts\activate
```

You should see `(venv)` appear in your prompt.

---

## 7. Package Installation

Because `pip` alone can be unreliable on some Windows setups, always use:

```powershell
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

---

## 8. Roboflow API Key Setup

1. Copy the example environment file:
   ```powershell
   copy .env.example .env
   ```
2. Log into [Roboflow](https://roboflow.com), open your account/workspace
   settings, and copy your **Private API Key**.
3. Open `.env` in a text editor and set:
   ```
   ROBOFLOW_API_KEY=your_real_key_here
   ROBOFLOW_MODEL_ID=forblind-p23lj/1
ROBOFLOW_API_URL=https://serverless.roboflow.com
   ```
4. **Never** commit `.env` to version control — it's already in `.gitignore`.

---

## 9. Using Your Laptop's Webcam Instead of the ESP32-CAM

If you can't power the ESP32-CAM yet (it needs a stable 5V/500mA+ supply —
USB from a laptop is often not enough on its own, especially during WiFi
transmission), you can develop and test the entire pipeline using your
laptop's built-in or USB webcam instead. Everything downstream — Roboflow
detection, distance fusion, risk engine, voice, dashboard — works exactly
the same either way; only where the video comes from changes.

In `.env`, set:

```
CAMERA_SOURCE=laptop
LAPTOP_CAM_INDEX=0
```

`LAPTOP_CAM_INDEX=0` is almost always your default built-in webcam. If you
have multiple cameras and `0` opens the wrong one, try `1`, `2`, etc.

Run as normal:

```powershell
py app.py
```

Open `http://localhost:5000/dashboard` — the "Camera" status dot should go
green using your laptop's webcam, with real Roboflow detections drawn on
real video (this needs `TEST_MODE=false` and a valid `ROBOFLOW_API_KEY`).

**Switching back to the ESP32-CAM later:** once you've sorted out power
(a dedicated 5V/1A+ supply or FTDI programmer with an external supply
usually fixes it), just change two lines in `.env`:

```
CAMERA_SOURCE=esp32
ESP32_STREAM_URL=http://YOUR_ESP32_IP:81/stream
```

No code changes needed — `camera.py` reads this setting and switches
sources automatically.

---

## 10. ESP32-CAM Setup

1. Open `hardware/esp32_cam/esp32_cam.ino` in the Arduino IDE (the
   `app_httpd.cpp` file in the same folder will be compiled automatically).
2. Edit the Wi-Fi credentials near the top:
   ```cpp
   const char* ssid = "YOUR_WIFI_NAME";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
3. In **Tools**, select:
   - Board: **AI Thinker ESP32-CAM**
   - Partition Scheme: **Huge APP (3MB No OTA/1MB SPIFFS)**
4. Wire GPIO0 to GND to put the board in flashing mode, connect the FTDI
   adapter, and click **Upload**.
5. After upload, disconnect GPIO0 from GND and reset the board.
6. Open the **Serial Monitor** at **115200 baud**. After Wi-Fi connects you
   will see:
   ```
   Camera stream ready at: http://192.168.x.x:81/stream
   ```
7. Copy that IP address into your `.env` file:
   ```
   ESP32_STREAM_URL=http://192.168.x.x:81/stream
   ```

---

## 11. Arduino UNO Setup

1. Open `hardware/arduino_ultrasonic/arduino_ultrasonic.ino` in the Arduino IDE.
2. Select **Board: Arduino UNO** and the correct **Port**.
3. Click **Upload**.
4. Open the Serial Monitor at **9600 baud** to confirm you see lines like:
   ```
   DISTANCE:75.4
   ```

---

## 12. COM Port Configuration

1. Open **Device Manager → Ports (COM & LPT)** on Windows to find which
   COM port the Arduino UNO is on (e.g. `COM3`).
2. Set it in `.env`:
   ```
   ARDUINO_PORT=COM3
   ```

---

## 13. Running the Application

With the virtual environment active and `.env` filled in:

```powershell
py app.py
```

Then open a browser to:

```
http://localhost:5000/dashboard
```

You should see the live video feed, system status indicators, current
detection, and recent alerts.

### Running without any hardware (TEST_MODE)

To try the dashboard and pipeline without an ESP32-CAM, Arduino, or
Roboflow key connected, set in `.env`:

```
TEST_MODE=true
```

This simulates a camera feed, distance readings, and rotating detections
(Chair/Table/Person/Stairs) so you can verify the full software stack
end-to-end. Set it back to `false` for real hardware.

---

## 14. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Dashboard shows "Camera: Offline" (ESP32 mode) | Check ESP32_STREAM_URL, confirm ESP32-CAM is powered and on the same Wi-Fi network, visit the stream URL directly in a browser |
| ESP32-CAM keeps browning out / resetting | It's a power problem, not a code problem — USB from a laptop is often not enough once WiFi is transmitting. Use a dedicated 5V/1A+ power supply, or set `CAMERA_SOURCE=laptop` in `.env` to develop with your webcam in the meantime (see section 9) |
| Dashboard shows "Camera: Offline" (laptop mode) | Check `LAPTOP_CAM_INDEX` (try 0, 1, 2), make sure no other app (Zoom, Teams, browser tab) is already holding the webcam, and check Windows camera privacy settings allow desktop apps to access it |
| Dashboard shows "Arduino: Offline" | Check ARDUINO_PORT matches Device Manager, close any other program (Serial Monitor) that has the port open |
| Dashboard shows "Roboflow: Offline" | Check ROBOFLOW_API_KEY is correct and you have internet access; check `logs/system.log` for the exact error |
| No spoken voice output | Confirm `pyttsx3` installed correctly; on some systems a working SAPI5 (Windows) voice is required — this is built into Windows by default |
| Video feed is choppy | Lower `INFERENCE_FPS` in `.env`, or reduce ESP32-CAM resolution in `esp32_cam.ino` |
| `py` not recognized | Reinstall Python from python.org and check "Add python.exe to PATH" during setup |
| Serial port access denied | Make sure the Arduino Serial Monitor / other apps aren't also holding the COM port open |

---

## 15. Project Architecture

```
ai-obstacle-assistance/
│
├── app.py                    # Flask entry point, fuses detection+distance, serves dashboard/API
├── config.py                 # Loads all settings from .env
├── camera.py                 # Reads ESP32-CAM MJPEG stream (threaded)
├── roboflow_detector.py      # Runs Roboflow inference at a controlled FPS (threaded)
├── distance_sensor.py        # Reads Arduino serial distance data (threaded)
├── risk_engine.py            # Pure risk-calculation logic (unit-testable)
├── voice.py                  # pyttsx3 TTS with cooldown (threaded)
├── alerts.py                 # Rolling recent-alerts log
├── requirements.txt
├── .env.example
├── README.md
│
├── hardware/
│   ├── arduino_ultrasonic/arduino_ultrasonic.ino
│   └── esp32_cam/
│       ├── esp32_cam.ino
│       └── app_httpd.cpp     # MJPEG /stream server for the ESP32-CAM
│
├── templates/dashboard.html
├── static/css/style.css
├── static/js/dashboard.js
└── logs/                     # system.log written here at runtime
```

### API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` , `GET /dashboard` | Web dashboard |
| `GET /video_feed` | Processed MJPEG stream with bounding boxes |
| `GET /api/status` | `{camera, arduino, roboflow, test_mode}` |
| `GET /api/detection` | `{object, confidence, distance, risk}` |
| `GET /api/distance` | `{distance}` |
| `GET /api/alerts` | `{alerts: [...]}` |

---

## 16. Testing Each Part

**Object detection:** with real hardware connected, hold a chair, table, or
stand in front of the camera; watch `/api/detection` update and boxes
appear on `/video_feed`. In `TEST_MODE`, detections rotate automatically
every few seconds.

**Voice:** speak-aloud warnings play through your computer's speakers when
the highest-risk obstacle first becomes alert-worthy, its risk meaningfully
increases, its identity changes, or it becomes critical; check
`logs/system.log` for `[VOICE]` entries if you're unsure it fired.

**Ultrasonic distance:** open the Arduino Serial Monitor at 9600 baud and
wave your hand in front of the HC-SR04 — you should see `DISTANCE:` values
change; the same values should appear at `/api/distance`.

---

## 17. Limitations

- Recognizes only **Chair, Table, Person, Stairs** — any other object is
  not identified by class, even though distance is still reported.
- Ultrasonic distance is a single straight-line reading and is **independent
  of what Roboflow thinks the object is** — it does not confirm object identity.
- Requires stable Wi-Fi between the ESP32-CAM and the computer running Flask.
- Voice output requires a working local TTS voice engine.
- This is a **prototype** and must not be relied upon as a sole means of
  navigation or collision avoidance.


## Important behavior in the fixed version

- Every confident camera detection receives an object-risk, distance, box-size,
  box-growth, position, approach-speed, TTC, and weighted risk-score result.
- The one HC-SR04 reading is associated only with the closest-to-center box.
  Other boxes use an approximate apparent-size camera distance estimate; this
  is not a measured distance and is labeled `camera_estimate` in the API.
- Only the highest-scoring object is presented as the current danger and
  included in automatic safety speech.
- Close-distance HIGH/CRITICAL alerts work on the first distance sample and do
  not depend on approach speed or TTC being available.
- A single persistent background TTS worker drains a queue for both automatic
  safety alerts and Gemini conversation. It continues after speech errors.
- `GET /api/detection` additionally provides `danger_object`, `risk_level`,
  `risk_score`, `distance_source`, `approach_speed`, `ttc`, `direction`,
  `box_area`, `box_growth`, and per-object scored details.
- The five risk levels are `SAFE`, `WATCH`, `WARNING`, `HIGH`, and `CRITICAL`.
  Weights, thresholds, class weights, and camera-distance estimate parameters
  can be tuned in `.env`; see `.env.example`.
- Automatic warning format is concise, for example:
  "Warning. Car ahead. Approaching."
- `/api/diagnostics` shows the camera, Arduino, Roboflow model, API URL and
  last Roboflow error.
- `py test_hardware.py` checks the laptop camera and Arduino distance sensor
  before starting Flask.

### Roboflow model note

The included `forblind-p23lj/1` model is a small four-class model:
Chair, Table, Person and Stairs. It does **not** contain a `car` class.
If you need cars, buses, motorcycles and other COCO classes, switch to a
COCO object-detection model rather than expecting the four-class model to
detect a car.

---

## 18. Added optional Gemini + Wake-Word Companion (interface unchanged)

This version keeps the existing project objective, dashboard, camera pipeline,
Roboflow detector, HC-SR04 distance sensor, risk engine, voice-warning logic,
and all existing files. The Gemini companion is an additional layer.

### Safety is always active

The existing fusion loop continues to run automatically:

```text
Camera -> Roboflow -> Object
                   +
HC-SR04 -> Distance
                   |
                   v
              Existing Risk Engine
                   |
          relevant WARNING / HIGH / CRITICAL obstacle
                   |
             Voice warning
```

The safety path does **not** wait for `Hey Jarvis` and does not call Gemini to
decide whether an obstacle is dangerous.

### Wake word is only for conversation

When `WAKEWORD_ENABLED=true` and a Gemini API key is configured, the optional
listener waits for:

```text
Hey Jarvis
```

After activation it records a short voice command and sends the command to
Gemini. It can answer both current-environment questions and general questions.

Examples:

- "What is in front of me?"
- "Is the object nearby dangerous?"
- "Explain machine learning."
- "What is Python?"
- "Help me with my AI project."
- "Tell me a short joke."

For surroundings/safety questions, the agent receives the current local sensor
snapshot. For general conversation, it does not pretend to have live sensor
information.

### Important separation

`risk_engine.py` remains the safety decision layer. Gemini cannot override a
HIGH/CRITICAL result and cannot invent sensor distance or object information.
Gemini and wake-word processing are not called by the safety fusion loop.

### Risk scoring and hardware limits

The default weighted score considers object hazard potential (0.20), distance
(0.20), path overlap (0.15), obstruction evidence (0.15), approach speed (0.10),
TTC (0.10), and box size/growth (0.10). TTC is only populated for positive
approach speed, and speed/TTC affect the score only for objects intersecting
the configured walking-path corridor. Objects outside that corridor cannot
rise above WATCH by class, size, closeness, or movement alone.

Person detections are excluded from safety scoring and ranking entirely,
case-insensitively. They can remain visible in camera/debug detections, but
cannot become a voice or software safety alert. Other conditional hazards such
as chairs and tables retain low default object potential and require path
relevance/obstruction evidence. Automatic speech additionally requires the
object to satisfy the blocking-path heuristic (in the corridor, near enough,
near the bottom of the frame, and with sufficient box/corridor coverage).
Distance, apparent movement, or a high raw risk score alone cannot trigger
speech; non-blocking objects are limited to SAFE/WATCH. Alert phrases stay
short and omit distance and approach commentary. Thresholds, class values,
corridor width, and obstruction evidence are configurable in `.env`.

The HC-SR04 measures only one point in front of the device, so camera-derived
distances for non-central objects are rough estimates and must not be treated
as sensor-grade measurements. The Arduino's local buzzer remains a separate
distance-only function and can sound without camera-based object filtering.

### New files

```text
agent.py              # Gemini general + environment conversation
wake_word.py          # Hey Jarvis listener and voice-command capture
test_gemini.py        # Gemini connection test
setup_wakeword.py     # Wake-word model loading test
```

### Existing interface files were intentionally not changed

The following dashboard files are kept from the original fixed project:

```text
templates/dashboard.html
static/css/style.css
static/js/dashboard.js
```

No new Gemini panel or redesigned dashboard is required. The companion works
through the microphone/wake word and the existing local voice output. Two
additional backend API endpoints are available for testing:

```text
POST /api/assistant
GET  /api/assistant/status
```

### Setup

Add these values to `.env`:

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash
WAKEWORD_ENABLED=true
WAKEWORD_MODEL=hey_jarvis
WAKEWORD_THRESHOLD=0.55
COMMAND_SECONDS=5
```

Install the additional packages from `requirements.txt` and test Gemini:

```powershell
py -m pip install -r requirements.txt
py test_gemini.py
```

Then test the wake-word model:

```powershell
py setup_wakeword.py
```

Finally run the existing application normally:

```powershell
py app.py
```

If Gemini or wake-word configuration is missing, the original obstacle
assistance system still remains the primary project; the optional companion
simply stays inactive.
