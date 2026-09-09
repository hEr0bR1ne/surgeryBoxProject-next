#include <Arduino.h>
#include <Servo.h>
#include <ESP8266WiFi.h>

// GPIO16 is D2 on WEMOS D1 R1. Confirm the replacement board before wiring.
static constexpr uint8_t SERVO_PIN = 16;
static Servo servo;
static bool enabled = false;
static int angle = 90;
static String input;
static bool discardLine = false;

static void status() {
    Serial.printf("SERVO:ENABLED:%d,ANGLE:%d\n", enabled ? 1 : 0, angle);
}

static void command(const String& text) {
    if (text == "HELLO_PC") {
        Serial.println("ACK: SERVO_ONLY");
    } else if (text == "SERVO?") {
        status();
    } else if (text == "SERVO:OFF") {
        servo.detach();
        pinMode(SERVO_PIN, INPUT);
        enabled = false;
        status();
    } else if (text == "SERVO:ENABLE") {
        if (!enabled) {
            angle = 90;
            servo.attach(SERVO_PIN);
            servo.write(angle);
            enabled = true;
        }
        status();
    } else if (text.startsWith("SERVO:ANGLE:")) {
        String value = text.substring(12);
        bool valid = value.length() >= 2 && value.length() <= 3;
        for (unsigned int i = 0; i < value.length(); ++i) {
            if (value[i] < '0' || value[i] > '9') valid = false;
        }
        int requested = value.toInt();
        if (!enabled || !valid || requested < 60 || requested > 150 || abs(requested - angle) > 5) {
            Serial.println("ERROR: enable first; integer angle 60-150; max step 5 degrees");
            return;
        }
        angle = requested;
        servo.write(angle);
        status();
    } else {
        Serial.println("ERROR: unknown servo-only command");
    }
}

void setup() {
    pinMode(SERVO_PIN, INPUT); // No servo pulses until explicit enable.
    WiFi.mode(WIFI_OFF);
    Serial.begin(115200);
    Serial.println("READY: SERVO_ONLY; output disabled");
}

void loop() {
    while (Serial.available()) {
        char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            if (!discardLine) {
                input.trim();
                if (input.length()) command(input);
            }
            input = "";
            discardLine = false;
        } else if (!discardLine) {
            if (input.length() >= 64) {
                discardLine = true;
                input = "";
            } else {
                input += c;
            }
        }
    }
    delay(1);
}
