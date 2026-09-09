# Hardware development constraints

## Handoff entry point

Read `docs/AI-HANDOFF.md` first. It is the current human/AI handoff, including wiring, calibration, verified observations, unresolved motor faults, and the upper-computer integration tasks assigned to the next collaborator. Earlier bring-up notes are chronological history and may describe superseded states.

The last user-confirmed on-device firmware is `hardware_tests/motor_continuous`, NOT the guarded main application. It has no serial stop or encoder limits. Do not assume GitHub source matches the running device, send actuator commands, flash, or restore external power without verifying current physical conditions. All peripherals derive power from the external 24V through appropriate circuits; the MCU uses USB. Do not recreate the reported accidental 5V/GND short.

The user explicitly requested the independent continuous test; retain its source as a bench diagnostic, not as a replacement for guarded winding. The main application and its limits remain in `src/` and `include/`.

The user requires every future motor/winding operation to stay within the calibrated physical travel. Read `docs/encoder-travel-calibration.md` and `hardware_tests/encoder_range_calibration.json` before changing or testing motor control.

- Use the calibrated encoder counts as the travel limit; the historical metres-per-tick factor is not yet measured for this assembly.
- Preserve the physical home reference independently of training-relative zero. A restart, reconnect, or training Start must not silently establish a new physical home at an arbitrary position.
- Do not run powered winding until both travel boundaries, motor direction, stop margin, and loss-of-encoder stopping are implemented and validated. The existing firmware has not yet been validated for these constraints.
- The measured endpoint is an upper bound, not a target to exceed or a reason to remove a stopping margin. Do not use the existing automatic direction-reversal trial at a physical endpoint.
