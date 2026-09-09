#include "travel_limits.h"

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
