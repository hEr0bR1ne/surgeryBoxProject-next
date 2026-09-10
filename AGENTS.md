> **2026-09-10 15:27 现场更新：新版方向＋PWM正反点动保护主程序已烧录COM4，上传校验通过；串口确认control=dir_pwm_v1、active=0、home=0、direction=unknown、D7/D8均低、BRAKE:ANGLE:0、LIGHT:OFF。此前常转固件已被替换。用户说明正转回卷，反转脱离离合器。烧录核对时整套24V断开、USB保留，未执行运动或登记机械零点；点动及实际离合器行为仍待用户测试。详见 [点动工具说明](hardware_tests/motor_tuner/README.md)。**

# Hardware development constraints

## Handoff entry point

Read `docs/AI-HANDOFF.md` first. It is the current human/AI handoff, including wiring, calibration, verified observations, unresolved motor faults, and the upper-computer integration tasks assigned to the next collaborator. Earlier bring-up notes are chronological history and may describe superseded states.

On 2026-09-09 the guarded main application from source commit `4371a51` was restored to the board on COM4; upload hash verification and read-only serial checks passed. See `docs/main-firmware-restoration.md`. The last checked state was motor inactive, D7/D8 low, light off, commanded servo angle 0, home unreferenced and direction unknown, with external 24V disconnected and USB connected. This replaces the earlier `hardware_tests/motor_continuous` firmware, which has no serial stop or encoder limits. Do not assume the recorded state persists: verify current physical conditions before actuator commands, flashing, or restoring external power. All peripherals derive power from the external 24V through appropriate circuits; the MCU uses USB. Do not recreate the reported accidental 5V/GND short.

The user explicitly requested the independent continuous test; retain its source as a bench diagnostic, not as a replacement for guarded winding. The main application and its limits remain in `src/` and `include/`.

The user requires every future motor/winding operation to stay within the calibrated physical travel. Read `docs/encoder-travel-calibration.md` and `hardware_tests/encoder_range_calibration.json` before changing or testing motor control.

- Use the calibrated encoder counts as the travel limit; the historical metres-per-tick factor is not yet measured for this assembly.
- Preserve the physical home reference independently of training-relative zero. A restart, reconnect, or training Start must not silently establish a new physical home at an arbitrary position.
- Do not run powered winding until both travel boundaries, motor direction, stop margin, and loss-of-encoder stopping are implemented and validated. The existing firmware has not yet been validated for these constraints.
- The measured endpoint is an upper bound, not a target to exceed or a reason to remove a stopping margin. Do not use the existing automatic direction-reversal trial at a physical endpoint.
