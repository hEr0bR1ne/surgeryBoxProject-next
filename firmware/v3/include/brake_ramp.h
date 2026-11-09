#pragma once
#include <stdint.h>

// Commanded angles only. A disconnected/unpowered servo has no position feedback.
struct BrakeRamp {
    static constexpr uint32_t stepMs=20, settleMs=500;
    int current=180, target=180;
    bool doubleStep=false;
    uint32_t stepAt=0, changedAt=0;
    constexpr bool moving() const { return current!=target; }
    constexpr void begin(int angle,uint32_t now) {
        target=angle; stepAt=changedAt=now; doubleStep=false;
    }
    constexpr bool update(uint32_t now) {
        if (!moving() || uint32_t(now-stepAt)<stepMs) return false;
        // Never catch up with a large jump after a delayed loop iteration.
        const int step=doubleStep ? 2 : 1;
        doubleStep=!doubleStep;
        const int remaining=target>current ? target-current : current-target;
        current+=(target>current ? 1 : -1)*(remaining<step ? remaining : step);
        stepAt=changedAt=now;
        return true;
    }
    constexpr bool settled(uint32_t now) const {
        return !moving() && uint32_t(now-changedAt)>=settleMs;
    }
    constexpr void cancel() { target=current; }
};
