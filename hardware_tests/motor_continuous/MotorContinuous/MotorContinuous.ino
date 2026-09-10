#include <Arduino.h>
#include <ESP8266WiFi.h>

// WEMOS D1 R1: physical D7 = GPIO13; physical D8 = GPIO0.
// Bench test ONLY with motor mechanically disconnected from winding load.
// On power-up: AIN1 direction LOW, AIN2 continuous 500 Hz / 50% PWM.
// No encoder limit, automatic stop, or serial stop command in this sketch.
// Disconnect external motor power to stop. Never use with catheter attached.
constexpr uint8_t MOTOR_IN1 = 13;
constexpr uint8_t MOTOR_IN2 = 0;
// Forward-only bench test; reverse PWM polarity/stop behavior is not validated.
constexpr uint16_t MOTOR_PWM = 512;
constexpr uint16_t MOTOR_PWM_RANGE = 1023;
constexpr uint16_t MOTOR_PWM_HZ = 500;

void setup() {
    digitalWrite(MOTOR_IN1, LOW);
    digitalWrite(MOTOR_IN2, LOW);
    pinMode(MOTOR_IN1, OUTPUT);
    pinMode(MOTOR_IN2, OUTPUT);
    WiFi.persistent(false);
    WiFi.mode(WIFI_OFF);
    Serial.begin(115200);

    analogWriteRange(MOTOR_PWM_RANGE);
    analogWriteFreq(MOTOR_PWM_HZ);
    digitalWrite(MOTOR_IN1, LOW);
    analogWrite(MOTOR_IN2, MOTOR_PWM);
    Serial.println("MOTOR_DIR_PWM: forward test; stop by disconnecting external power");
}

void loop() {
    // PWM continues between logs; no time limit or other peripherals.
    delay(1000);
    Serial.printf("MOTOR_DIR_PWM: DIR_GPIO13=%d PWM_GPIO0=%u/%u freq=%uHz\n",
                  digitalRead(MOTOR_IN1), MOTOR_PWM, MOTOR_PWM_RANGE, MOTOR_PWM_HZ);
}
