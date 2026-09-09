#pragma once

// User measurement: 34891 ticks. Both ends inset by 5%.
constexpr long TRAVEL_MEASURED_MAX = 34891;
constexpr long TRAVEL_LOW = 1745;
constexpr long TRAVEL_HIGH = 33146;
// Additional provisional coast allowance; validate before long winding.
constexpr long TRAVEL_STOP = TRAVEL_LOW + 200;
constexpr long PROBE_LOW = 14000;
constexpr long PROBE_HIGH = 20000;
constexpr long PROBE_MAX_DELTA = 150;
constexpr unsigned long PROBE_MS = 2000;
constexpr unsigned long MOTOR_STALL_MS = 500;
constexpr unsigned long MOTOR_MAX_MS = 15000;

enum class TravelStop { None, Boundary, WrongWay, NoFeedback, Timeout, ProbeDone };

constexpr TravelStop checkTravel(bool probe, long position, long start,
                             long best, unsigned long elapsed, unsigned long stalled) {
    return (position <= TRAVEL_STOP || position > TRAVEL_HIGH) ? TravelStop::Boundary :
        (!probe && position > best + 8) ? TravelStop::WrongWay :
        stalled >= (probe ? PROBE_MS : MOTOR_STALL_MS) ? TravelStop::NoFeedback :
        elapsed >= MOTOR_MAX_MS ? TravelStop::Timeout :
        (probe && (elapsed >= PROBE_MS || position - start >= PROBE_MAX_DELTA ||
                    start - position >= PROBE_MAX_DELTA)) ? TravelStop::ProbeDone : TravelStop::None;
}
