#include <Arduino.h>
#include <Servo.h>
#include <ESP8266WiFi.h>

// WEMOS D1 R1: physical D2 = GPIO16.
static constexpr uint8_t SERVO_PIN = 16;
static Servo servo;
static bool enabled = false;
static int outputAngle = 90;
static int targetAngle = 90;
static unsigned long lastContact = 0;
static unsigned long lastStep = 0;
static unsigned long lastReport = 0;
static String input;
static bool discardLine = false;

static void reportState() {
  Serial.printf("STATE:%d,%d,%d\n", enabled ? 1 : 0, outputAngle, targetAngle);
}

static void disableOutput() {
  servo.detach();
  pinMode(SERVO_PIN, INPUT);
  enabled = false;
  targetAngle = outputAngle;
}

static void handleCommand(const String& cmd) {
  if (cmd == "HELLO_TUNER") {
    lastContact = millis();
    Serial.println("TUNER:1");
    reportState();
  } else if (cmd == "PING" || cmd == "STATUS") {
    lastContact = millis();
    reportState();
  } else if (cmd == "OFF") {
    disableOutput();
    lastContact = millis();
    reportState();
  } else if (cmd.startsWith("SET:")) {
    String value = cmd.substring(4);
    bool valid = value.length() > 0 && value.length() <= 3;
    for (unsigned int i = 0; i < value.length(); ++i) {
      if (value[i] < '0' || value[i] > '9') valid = false;
    }
    int requested = value.toInt();
    if (!valid || requested < 0 || requested > 180) {
      Serial.println("ERROR: angle must be an integer from 0 to 180");
      return;
    }
    lastContact = millis();
    targetAngle = requested;
    if (!enabled) {
      servo.attach(SERVO_PIN);
      servo.write(outputAngle);
      enabled = true;
    }
    reportState();
  } else {
    Serial.println("ERROR: unknown tuner command");
  }
}

void setup() {
  pinMode(SERVO_PIN, INPUT);
  WiFi.mode(WIFI_OFF);
  Serial.begin(115200);
  Serial.println("READY: SERVO_TUNER_V1; output disabled");
}

void loop() {
  // Bound input work so servo stepping and the contact timeout keep running.
  for (int n = 0; n < 64 && Serial.available(); ++n) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r' || c == '\n') {
      if (!discardLine) {
        input.trim();
        if (input.length()) handleCommand(input);
      }
      input = "";
      discardLine = false;
    } else if (!discardLine) {
      if (input.length() >= 48) { discardLine = true; input = ""; }
      else input += c;
    }
  }
  unsigned long now = millis();
  if (enabled && now - lastContact >= 3000) {
    disableOutput();
    Serial.println("NOTICE: contact timeout; pulses disabled");
    reportState();
  }
  if (enabled && outputAngle != targetAngle && now - lastStep >= 20) {
    lastStep = now;
    outputAngle += (targetAngle > outputAngle) ? 1 : -1;
    servo.write(outputAngle);
    if (now - lastReport >= 100 || outputAngle == targetAngle) {
      lastReport = now;
      reportState();
    }
  }
  delay(1);
}
