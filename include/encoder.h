#ifndef ENCODER_H
#define ENCODER_H

void encoderInit();
float readDistance();
long readTicks();
long readRawTicks();
int readEncoderPinA();
int readEncoderPinB();
unsigned long readEncoderEdgesA();
unsigned long readEncoderEdgesB();
void resetEncoderDiagnostics();
void resetEncoder();
long readPhysicalTicks();
void confirmPhysicalHome();

#endif
