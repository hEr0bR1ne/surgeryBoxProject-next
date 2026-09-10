#include "travel_limits.h"

static_assert(motorPwmHighDuty(false, 300) == 300, "Forward high duty");
static_assert(motorPwmHighDuty(true, 300) == 723, "Reverse drive uses LOW portion");
static_assert(checkJog(true, 17000, 17000, 17000, 499, 500) == TravelStop::None, "Clutch no-motion is expected");
static_assert(checkJog(true, 17000, 17000, 17000, 500, 500) == TravelStop::ProbeDone, "Firmware owns requested deadline");
static_assert(checkJog(false, 17000, 17000, 17000, 100, 100) == TravelStop::ProbeDone, "Shortest deadline without GUI");
static_assert(checkJog(true, 16992, 17000, 16992, 20, 500) == TravelStop::ClutchMoved, "Clutch must not wind");
static_assert(checkJog(true, 17008, 17000, 17000, 20, 500) == TravelStop::ClutchMoved, "Clutch must not unwind");
static_assert(checkJog(false, 17009, 17000, 17000, 20, 500) == TravelStop::WrongWay, "Forward must decrease ticks");
static_assert(checkJog(false, 16850, 17000, 16850, 20, 500) == TravelStop::ProbeDone, "150 tick cap");
static_assert(checkJog(false, 1945, 2000, 1945, 500, 500) == TravelStop::Boundary, "Boundary outranks deadline");
static_assert(checkJog(true, 33147, 33146, 33146, 500, 500) == TravelStop::Boundary, "Upper bound outranks clutch/deadline");
static_assert(checkJog(false, 17000, 17000, 17000, 2000, 9000) == TravelStop::ProbeDone, "Hard two second cap");

// Compiled against the actual policy by the ESP8266 toolchain; no hardware motion.
static_assert(TRAVEL_LOW > 0 && TRAVEL_HIGH < TRAVEL_MEASURED_MAX, "Both endpoints inset");
static_assert(checkTravel(false, 1945, 33146, 1945, 100, 0) == TravelStop::Boundary, "Stop before lower bound");
static_assert(checkTravel(false, 33147, 33146, 33146, 1, 0) == TravelStop::Boundary, "Reject upper overrun");
static_assert(checkTravel(false, 33146, 33146, 33146, 0, 0) == TravelStop::None, "Allow inward move from upper boundary");
static_assert(checkTravel(false, 10009, 20000, 10000, 100, 0) == TravelStop::WrongWay, "Detect reversal after initial progress");
static_assert(checkTravel(false, 10000, 20000, 10000, 600, 500) == TravelStop::NoFeedback, "Stall deadline");
static_assert(checkTravel(false, 10000, 20000, 10000, 15000, 0) == TravelStop::Timeout, "Overall deadline");
static_assert(checkTravel(true, 16000, 16000, 16000, 150, 0) == TravelStop::None, "Allow longer startup time");
static_assert(checkTravel(true, 16000, 16000, 16000, 500, 500) == TravelStop::None, "Probe allows longer startup than normal rewind");
static_assert(checkTravel(true, 16000, 16000, 16000, 1999, 1999) == TravelStop::None, "Probe allows up to two seconds");
static_assert(checkTravel(true, 16000, 16000, 16000, 2000, 0) == TravelStop::ProbeDone, "Probe always stops at two seconds");
static_assert(checkTravel(true, 16000, 16000, 16000, 2000, 2000) == TravelStop::NoFeedback, "No movement stops by two seconds");
static_assert(checkTravel(true, 16150, 16000, 16000, 20, 0) == TravelStop::ProbeDone, "Probe outward displacement bound");
static_assert(checkTravel(true, 15850, 16000, 15850, 20, 0) == TravelStop::ProbeDone, "Probe inward displacement bound");
static_assert(checkTravel(false, 2000, 20000, 2000, 500, 0) == TravelStop::None, "Normal inward progress");
