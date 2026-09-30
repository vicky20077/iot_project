/*
  arduino_ultrasonic.ino

  Role: Arduino UNO reads distance from an HC-SR04 ultrasonic sensor and
  reports it over serial in a strict, machine-readable format that the
  Python backend (distance_sensor.py) parses:

      DISTANCE:75.4
      DISTANCE:-1        <- sent when no valid echo is received

  Also drives a small buzzer/speaker for local audible feedback on
  CRITICAL-zone obstacles, independent of the Python/TTS voice system.

  Wiring:
    HC-SR04:
      VCC  -> 5V
      GND  -> GND
      TRIG -> D10
      ECHO -> D9

    Speaker/buzzer:
      +    -> D3
      -    -> GND

  Baud rate: 9600

  IMPORTANT: Do not add extra Serial.println() debug lines elsewhere in
  this sketch — the Python serial parser expects ONLY "DISTANCE:<value>"
  lines on this port.
*/

const int TRIG_PIN = 10;
const int ECHO_PIN = 9;
const int SPEAKER_PIN = 3;

const unsigned long MEASURE_INTERVAL_MS = 150;   // how often to measure + report
const unsigned long PULSE_TIMEOUT_US = 30000UL;  // ~5m max range before we call it invalid

// Distance zones (must match config.py defaults)
const float ZONE_CRITICAL_MAX = 30.0;
const float ZONE_HIGH_MAX = 60.0;
const float ZONE_MEDIUM_MAX = 100.0;

unsigned long lastMeasureTime = 0;

void setup() {
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(SPEAKER_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  noTone(SPEAKER_PIN);
}

float readDistanceCm() {
  // Trigger a 10us pulse
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, PULSE_TIMEOUT_US);

  if (duration == 0) {
    return -1.0;  // no echo received within timeout -> invalid reading
  }

  // Speed of sound ~ 0.0343 cm/us, round trip -> divide by 2
  float distanceCm = (duration * 0.0343) / 2.0;

  if (distanceCm <= 0 || distanceCm > 500) {
    return -1.0;  // out of sane range
  }

  return distanceCm;
}

void updateSpeaker(float distanceCm) {
  if (distanceCm > 0 && distanceCm <= ZONE_CRITICAL_MAX) {
    tone(SPEAKER_PIN, 2000);   // continuous urgent tone for CRITICAL zone
  } else if (distanceCm > 0 && distanceCm <= ZONE_HIGH_MAX) {
    tone(SPEAKER_PIN, 1200, 80);  // short beep for HIGH zone
  } else {
    noTone(SPEAKER_PIN);
  }
}

void loop() {
  unsigned long now = millis();

  if (now - lastMeasureTime >= MEASURE_INTERVAL_MS) {
    lastMeasureTime = now;

    float distanceCm = readDistanceCm();

    if (distanceCm < 0) {
      Serial.println("DISTANCE:-1");
    } else {
      Serial.print("DISTANCE:");
      Serial.println(distanceCm, 1);  // one decimal place
    }

    updateSpeaker(distanceCm);
  }
}
