#ifndef SERVO_BRAKE_H
#define SERVO_BRAKE_H

#include <Arduino.h>

void servoBrakeInit();
void servoBrakeLock();
void servoBrakeWeak();
void servoBrakeRelease();
bool handleBrakeCalibrationCommand(const String& command);

#endif
