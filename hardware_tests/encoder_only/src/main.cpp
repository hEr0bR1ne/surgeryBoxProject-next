#include <Arduino.h>
#include <ESP8266WiFi.h>
#include "encoder.h"

static String input;
static bool discardLine = false;
static bool streaming = false;
static unsigned long lastReport = 0;

static void report() {
    extern volatile long encoderTicks;
    extern volatile unsigned long encoderEdgesA, encoderEdgesB;
    noInterrupts();
    const long raw = encoderTicks;
    const unsigned long a = encoderEdgesA, b = encoderEdgesB;
    interrupts();
    // Production direction convention is ENCODER_SIGN = -1.
    Serial.printf("ENC:raw=%ld,ticks=%ld,A=%d,B=%d,edgeA=%lu,edgeB=%lu\n",
                  raw, -raw, readEncoderPinA(), readEncoderPinB(), a, b);
}

static void command(const String& value) {
    if (value == "HELLO_PC") Serial.println("ACK: ENCODER_ONLY");
    else if (value == "ENC?") report();
    else if (value == "ZERO") {
        resetEncoderDiagnostics();
        report();
    } else if (value == "STREAM:ON") {
        streaming = true;
        Serial.println("ACK: STREAM:ON");
    } else if (value == "STREAM:OFF") {
        streaming = false;
        Serial.println("ACK: STREAM:OFF");
    } else Serial.println("ERROR: use HELLO_PC, ENC?, ZERO, STREAM:ON, STREAM:OFF");
}

void setup() {
    Serial.begin(115200);
    WiFi.persistent(false);
    WiFi.mode(WIFI_OFF);
    encoderInit();
    Serial.println("READY: ENCODER_ONLY D5=GPIO14/A D6=GPIO12/B");
}

void loop() {
    while (Serial.available()) {
        const char c = Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            if (!discardLine && input.length()) command(input);
            input = "";
            discardLine = false;
        } else if (!discardLine) {
            if (input.length() >= 48) { discardLine = true; input = ""; }
            else input += c;
        }
    }
    if (streaming && millis() - lastReport >= 200) {
        lastReport = millis();
        report();
    }
    delay(1);
}
