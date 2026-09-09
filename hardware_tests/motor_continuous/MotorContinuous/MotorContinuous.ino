#include <Arduino.h>
#include <ESP8266WiFi.h>

// WEMOS D1 R1: physical D7 = GPIO13; physical D8 = GPIO0.
// Bench test ONLY with motor mechanically disconnected from winding load.
// On power-up this continuously drives one direction at full duty.
// No encoder limit, automatic stop, or serial stop command in this sketch.
// Disconnect external motor power to stop. Never use with catheter attached.
constexpr uint8_t MOTOR_IN1 = 13;
constexpr uint8_t MOTOR_IN2 = 0;
constexpr bool REVERSE_DIRECTION = false; // true swaps electrical direction.

void setup() {
    digitalWrite(MOTOR_IN1, LOW);
    digitalWrite(MOTOR_IN2, LOW);
    pinMode(MOTOR_IN1, OUTPUT);
    pinMode(MOTOR_IN2, OUTPUT);
    WiFi.persistent(false);
    WiFi.mode(WIFI_OFF);
    Serial.begin(115200);

    digitalWrite(REVERSE_DIRECTION ? MOTOR_IN1 : MOTOR_IN2, LOW);
    digitalWrite(REVERSE_DIRECTION ? MOTOR_IN2 : MOTOR_IN1, HIGH);
    Serial.println("MOTOR_CONTINUOUS: full duty; stop by disconnecting external power");
}

void loop() {
    // Output levels remain constant. No PWM, time limit, or other peripherals.
    delay(1000);
    Serial.printf("MOTOR_CONTINUOUS: GPIO13=%d GPIO0=%d\n",
                  digitalRead(MOTOR_IN1), digitalRead(MOTOR_IN2));
}
