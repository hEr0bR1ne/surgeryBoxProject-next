#include <Arduino.h>
#include <Servo.h>

// WEMOS D1 R1: board label D2 = GPIO16.
// This is NOT the D2 mapping of a D1 mini or NodeMCU.
const uint8_t SERVO_SIGNAL_PIN = 16;
const int LOW_ANGLE = 80;
const int HIGH_ANGLE = 100;

Servo testServo;
int currentAngle = 90;

void moveTo(int target) {
  Serial.print("Moving to requested angle: ");
  Serial.println(target);
  while (currentAngle != target) {
    currentAngle += (target > currentAngle) ? 1 : -1;
    testServo.write(currentAngle);
    delay(25);
  }
  delay(1500);
}

void setup() {
  Serial.begin(115200);
  Serial.println("SERVO MANUAL TEST: GPIO16 / D2 on D1 R1");
  Serial.println("Automatic motion starts now; disconnect brake linkage first.");
  testServo.attach(SERVO_SIGNAL_PIN);
  testServo.write(currentAngle);
  delay(1500);
}

void loop() {
  moveTo(LOW_ANGLE);
  moveTo(HIGH_ANGLE);
}
