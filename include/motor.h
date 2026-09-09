#ifndef MOTOR_H
#define MOTOR_H
#include <Arduino.h>

void motorInit();
void motorForward();
void motorReverse();
void motorStartWindBack();
void motorUpdateWindBack();
void motorWindBack();
void motorStop();
void motorAbortWindBack();
bool motorIsWindingBack();
bool handleMotorSafetyCommand(const String& command);

#endif

