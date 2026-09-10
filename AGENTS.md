> **2026-09-11 输入组合测试版已烧录：** D7→AIN1、D8→AIN2恢复原接法。固件支持LOW/PWM/HIGH的9种组合逐项点动，状态matrix=1；普通组合最多2秒，全驱动组合2/6最多200ms，双向150计数限位及原机械行程保护保留。用户确认烧录准备完成；COM4烧录校验成功，未登记零点的9种组合均已实测拒绝，非法编号和时长拒绝，D7/D8均低。GUI14项测试和编译期保护断言通过。未执行动力测试，用户随后逐项观察；先前方向假设不能视为已证实。固件SHA256 `8be5b99a683ca12312bbac9b0cb80a9f3339941512387451fe10e6e3ca78935f`。

> **2026-09-10 15:53 最新实物状态：同PWM对照版保护固件已烧录COM4并通过写入校验。正反转只切换D7低/高，D8使用相同正数PWM，不做占空比反相。串口确认 pwm_mode=same_positive、home=0、active=0、direction=unknown，D7/D8均低。24V断开时核对，未执行运动；实际正反转效果待测试。固件SHA256：47d8aa8b1e1b7dc5cb6d9616f44e5457e214840af82424a165fd481031af5544。**

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
