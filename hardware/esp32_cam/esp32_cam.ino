/*
  esp32_cam.ino

  Role: AI Thinker ESP32-CAM connects to Wi-Fi and serves an MJPEG video
  stream that the Python backend (camera.py) reads via OpenCV:

      http://ESP32_IP:81/stream

  The board's IP address is printed to the Serial Monitor at 115200 baud
  after Wi-Fi connects, so it can be copied into the project's .env file
  as ESP32_STREAM_URL.

  Board: AI Thinker ESP32-CAM
  Required library: "ESP32" board package (Arduino IDE Boards Manager),
  which provides esp_camera.h and the camera pin definitions below.

  IMPORTANT: Replace YOUR_WIFI_NAME / YOUR_WIFI_PASSWORD with your actual
  credentials before flashing. Do not commit real credentials to version
  control.
*/

#include "esp_camera.h"
#include <WiFi.h>

// ---------------------------------------------------------------------
// Wi-Fi credentials — replace before flashing, do not commit real values
// ---------------------------------------------------------------------
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";

// ---------------------------------------------------------------------
// AI Thinker ESP32-CAM pin map
// ---------------------------------------------------------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// Forward declaration from app_httpd.cpp-style server (implemented below)
void startCameraServer();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Use higher resolution + quality only if PSRAM is present (AI Thinker has it)
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;   // 640x480 — good balance for AI inference
    config.jpeg_quality = 12;            // lower number = higher quality
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;  // 320x240 fallback without PSRAM
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("Wi-Fi connected");

  startCameraServer();

  Serial.print("Camera stream ready at: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");
}

void loop() {
  // Camera server runs on its own task; nothing needed here.
  delay(10000);
}
