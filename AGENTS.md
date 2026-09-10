> **2026-09-10 现场更新：用户要求并已重新烧录电机常转测试固件 hardware_tests/motor_continuous。上传校验通过，COM4 串口连续确认 MOTOR_CONTINUOUS: GPIO13=1 GPIO0=0。此前恢复保护主程序的记录是历史状态。当前固件无行程限位或串口停止，停止需断开电机外部供电。烧录时用户确认24V断开、USB连接、电机脱离卷线负载；未验证电机实际转动。原主程序备份保留，交接联调前需再次恢复保护主程序。**

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
