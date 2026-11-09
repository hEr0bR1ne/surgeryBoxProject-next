# 历史工作记录（不作为当前指令）

# 当前入口：第三代统一硬件API（2026-11-09）

**最新用户要求覆盖下方旧端点/行程限制：当前COM4已烧录3.1.0 / protocol=8，290464字节Hash校验通过，boot=15e2c4-dd5d290c。25次只读检查通过，home有效、encoder errors0、deadzone_ticks0、extension_limit0、各路输出关闭。上电首个有效编码器样本自动记home=0；不需人工两端标定，无拉出上限、无最小行程、无提前停车死区，到零即关方向2再释放1秒。方向2的编码器符号已由日志验证为+1；舵机75°/秒，较3.0.1加快50%。保留编码器失效/失联/错向/堵转/120秒运行上限。显示ZERO与重连不改home，跟踪失效后本次home失效且不自动重设。最新接口见docs/v3-hardware-api.md。用户已重新确认执行器隔离并授权烧录；本轮未发送启动执行器的指令。退出发送SAFE并释放COM4。用户报告缓动后刹车不再断连，日志多次动作成功，但首次重新启用仍出现一次error5，不宣称根因已完全消除。以下3.0.0/3.0.1记录和历史标定要求不得覆盖本段与最新用户指令。**


**最新实机状态优先：用户随后明确“已隔离，USB已接好，可以烧录”。COM4现已烧录3.0.1（296128字节，Hash通过），boot=15e2c4-d57f700a；25次只读检查通过，编码器errors0、丢帧0、所有执行器输出关闭，端点已清空。未发送动作。镜像与证据在releases/surgerybox-v3-3.0.1-candidate/。13项GUI/12项SDK及策略检查通过；缓动与1%停止余量仍待实机动作验证，COM4错误5仍未确认修复。下方“仍3.0.0/不得重烧/未开串口”是先前保留现场阶段，不再是最新烧录状态；旧ZIP未更新。**

**源码候选现为3.0.1，板载仍3.0.0：按用户要求添加1°/20ms舵机缓动，最后一步后等500ms才启动回卷；停止余量10%→1%（最少32计数），近目标启动容差128→8。仅离线构建/测试，不开串口、不重烧，旧ZIP未更新。串口error5未解决；初次附加舵机实际角度未知，不能保证首次动作缓慢。**

**当前新增未解决项：用户实测舵机指令后COM4反复Windows串口error 5（GetOverlappedResult/WriteFile），测试端关闭连接，boot未变。不能把之前隔离验收等同于实际动作通信稳定性通过。用户明确选择暂不改线、保留现场，本轮不得继续发送执行器动作/重烧；不自动重连重放旧命令。证据和状态见docs/v3-hardware-validation.md最上方。**

配套全功能测试端：tools/StartHardwareTest.cmd / tools/v3_test_client.py，说明docs/v3-test-console.md。
已完成12项GUI测试和COM4只读连接检查；不改变MCU固件、不自动启动执行器。测试端打开连接时会占用COM4，其他工具先关闭它。

已按用户要求完成四路硬件接口整合、烧录与隔离执行器下验收。**当前COM4运行firmware/v3，固件3.0.0 / API v1 / protocol=7**。
先读docs/v3-hardware-api.md与docs/v3-hardware-validation.md，再读docs/v3-bringup.md；本文件下方旧型号/固件/GUI状态为历史。
完整交接包：releases/surgerybox-v3-hardware-api-20261109.zip（23文件，包内SHA256已核验，包含已烧录镜像/源码/SDK/接口文档/验收证据）。
当前电机输出低、舵机脉冲OFF、灯OFF、两端未登记、I2C0x06有效，COM4释放。用户再次确认驱动板和舵机正极断开。
上位机只用host_sdk/surgerybox_v3.py；旧根目录主程序、旧训练事件、单项调试GUI均不兼容。旧根目录MOTOR_OUTPUT_ENABLED=false未改，不适用于本次新入口。
回卷API需当前有效人工端点、心跳与刹车释放准备；绝不恢复旧机械参考。完整带负载回卷/1秒释放和停车惯性仍待上位机联调，不能把软件接口验收说成该机械流程已实测通过。
新代码不依赖hardware_tests目录，不写编码器EEPROM，不输出未标定毫米值。不执行旧输入组合试验，不在当前隔离状态恢复执行器供电。

---
历史记录（以以上当前入口及验收文档为准）：

> **2026-11-09 最新100%版：用户反馈25%长按仍不动、确认VM取主板5V且电机本体此前直连5V能转，明确要求最大驱动；已再次确认隔离驱动板/舵机后烧录COM4。当前MOTOR_I2C_PROBE protocol=4、PWM1023/1023，286048字节Hash通过；15s/500ms无进展/250ms心跳/30ms反馈及行程方向保护保留。18项GUI回归通过，实机CAPS=pwm1023，缺端点时HOLD/PROBE拒绝、旧KEEP不启动，最终D7/D8及active/holding/armed=0，编码器errors=0；COM4已释放，本轮未发有效驱动。tools/StartMotorProbe.cmd为100%新版，先断电重登两端后用户手动测试。实际驱动芯片仍未核实，100%不升压；若A4950则5V仍不符合VBB规格。详见docs/v3-bringup.md。**

> **2026-09-15 新板更换：原板据用户反馈损坏，已为新WEMOS D1 R1烧录同一电机禁用联调固件。COM4，ESP8266EX，MAC 80:7d:3a:11:d5:8b，写入校验通过。串口确认motor_enabled=0、active=0、home=0、D7/D8低，Winding被拒绝；BRAKE:ANGLE:0、LIGHT:OFF、ENC?查询正常。24V断开时核对，未验证外设实际动作；COM4已释放。**

> **最新实物状态：2026-09-11T01:08:29（本机北京时间），电机禁用的上位机联调主程序已烧录COM4，写入校验通过。实测19条电机命令全部返回ERROR: motor_disabled_handoff；motor_enabled=0、matrix=0、active=0、D7/D8均低。舵机指令0°、LIGHT:OFF及ENC?查询正常。24V断开期间核对，未测试外设实际动作。COM4已释放。**

> **2026-09-11 上位机联调交接：电机输出已在源码中禁用（MOTOR_OUTPUT_ENABLED=false），Winding及全部电机测试命令均拒绝。舵机、编码器和血迹灯保留。实际烧录状态见 docs/main-firmware-restoration.md；最新交接见 docs/AI-HANDOFF.md。不要恢复电机测试固件或通过串口尝试解锁。**

> **2026-11-03 第三代当前固件：用户已确认隔离电机驱动板及舵机供电，并明确要求先调舵机。COM4已完成4MB板载Flash备份，随后烧录hardware_tests/servo_tuner固件，写入校验通过；HELLO_TUNER返回TUNER:1，STATUS/OFF返回STATE:0,90,90，输出关闭，未发送SET。当前板上不是主程序。原固件备份及恢复说明见hardware_backups/before_servo_tuner_20261103_v3/。当前硬件与供电变更先读docs/v3-bringup.md；下述第二代烧录/供电记录为历史。**

> **2026-11-03 后续更新：当前COM4已改烧ENCODER_I2C_14BIT，写入校验及串口验证通过。用户用一转二接D4/GPIO4→M+Z，VDD仍3.3V，A/SDA→D5、B/SCL→D6。D4读回高，0x06通信；运动采样1030帧全部有效、errors=0，约一圈累计约1.6万计数，跨零正常。停流回执丢失经重试恢复，工具已加重试；最终复核21帧静止稳定，COM4已释放。未写EEPROM。主程序仍是A/B读取，尚不兼容新接线；刹车180°/120°/50°只整合源码。新距离/原点/行程未标定，电机及舵机保持用户确认的供电隔离。详见docs/v3-bringup.md。**

> **2026-11-05 最新用户要求：仅需编码器相对位置，取消毫米距离换算及尺量标定，不再要求其测量200/50mm。执行器隔离及接线保持已由用户重新确认。板上仍为ENCODER_I2C_14BIT，无新烧录。已打开相对位置GUI（PID 3448），占用COM4，握手/诊断ZERO/STREAM通过，相对0、I2C errors=0。tools/StartEncoderRelative.cmd可重开。不要把诊断归零当作机械原点；打开其他串口工具前关闭该GUI。详见docs/v3-bringup.md。**

> **2026-11-05 电机最新：当前COM4为MOTOR_I2C_PROBE短点动固件（写入校验及未解锁拒绝测试通过），主程序电机禁用配置未改。用户在断电下登记允许端点0~18949，控制区间1894~17055，中段8034。用户确认恢复驱动板原5V后静止；仅执行一次官方IN1=PWM/IN2=LOW短脉冲，no_progress停机，位置无变化。随后MS确认D7/D8低、armed/active=0，COM4释放，驱动板仍按用户报告供5V，后续刷机须重新隔离。用户明确禁用旧输入组合遍历，只按实际型号官方指引。芯片型号仍未实查；若为A4950，5V低于官方8~40V工作范围，先核实型号/供电，不再盲目增PWM或延时。两端参考在RAM中，复位失效。详见docs/v3-bringup.md。**

> **2026-11-09 用户现场最新确认：100%测试成功，方向2能回卷；不按方向1则摩擦轮锁住、线无法拉出。方向1是短按后保持释放还是必须按住尚未确认，不自动添加反向脉冲或持续放线。日志motor_gui_20261109_133056.txt显示signB=+1、signA=0，末尾输出关闭。固件仍protocol=4，未改或重烧。详见docs/v3-bringup.md最新段。**

> **补充确认：用户明确方向1短按一次即可，松开后可拉出，无需持续通电。正常回卷完成的目标流程是方向2回卷→停→方向1短暂释放→停；具体释放时长未标定，尚未改固件/执行动作。故障或急停不自动反向释放。**

> **2026-11-09 最新protocol=5：用户指定方向1释放1秒（逆向不触碰线卷），已在当前隔离确认后烧录COM4，287792字节Hash通过。正常回卷结束先停50ms→方向1/100%1000ms→关闭；急停/故障/失联不自动反向。释放允许无位移，仍有250ms心跳/编码器/128计数异常位移及物理区间保护。GUI新增独立1秒释放按钮，23项GUI回归/编译策略检查通过，实机缺端点拒绝释放、输出低、I2C errors=0，COM4释放。旧RAM端点失效，用户须重登后测试；本轮未执行有效驱动。以docs/v3-bringup.md最新段为准，前述protocol=4为历史。**

> **2026-11-09 当前protocol=6灯检查：用户确认隔离驱动板/舵机供电后，COM4已烧录288000字节Hash通过；新增D3/GPIO5的LIGHT:ON/OFF/?。实机D3读回0→1，电机输出低、I2C正常，但用户明确灯“没有亮”，不能宣布整机通过。当前D3保持HIGH供测量，串口释放；等待灯模块VCC-GND与IN-GND实测值，勿打开GUI连接导致关灯。见docs/v3-bringup.md最新段；protocol=5及更早为历史。**

> **2026-11-09 灯最终通过：用户修正线路后重发D3 HIGH，现场明确确认“亮了”。随后LIGHT:OFF/?回D3=0/OFF，COM4释放；此前灯未亮/等待测量/留HIGH均为历史。当前仍protocol=6，灯关闭，未烧录或发送电机动作。可以进入整机接口整合；主程序电机禁用、新I2C尚未整合，1秒自动释放完整机械流程及停车惯性仍待联调。详见docs/v3-bringup.md最新结果。**

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
