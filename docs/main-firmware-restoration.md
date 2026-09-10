# 当前交接固件：电机禁用

2026-09-11T01:08:29（Asia/Shanghai）。用户确认24V断开、USB保留、串口关闭后执行烧录；COM4初次被占用，正常关闭活动motor_tuner窗口后烧录成功，写入哈希校验通过。ESP8266EX，MAC e8:db:84:c2:d2:8c。

固件328592字节，SHA256 `58404b3f851a89a8c64b9d8907906a0cdec2e712b91f9ebf6b93ed4a1b243842`。源码 `include/config.h` 的MOTOR_OUTPUT_ENABLED=false，串口不能解锁。更改前源码和固件备份在本机忽略目录hardware_backups/before_motor_disabled_时间戳。

实测拒绝：Winding、MF、MR、MotorForward、MotorReverse、MOTOR:PWM:512、PROBE F/R、JOG F/R、MATRIX 0～8，共19条，均返回 `ERROR: motor_disabled_handoff`。没有发送TRAVEL:HOME或解除禁用。

只读状态：

```text
TRAVEL:home=0,pos=0,low=1745,high=33146,stop=1945,direction=unknown,active=0,pwm=300,control=dir_pwm_v1,pwm_mode=same_positive,motor_enabled=0,matrix=0,combo=-1,duration_ms=2000,reason=motor_disabled_handoff
MS -> ACK: MotorStop
BRAKE? -> BRAKE:ANGLE:0
LIGHT? -> LIGHT:OFF
ENC? -> ENC:raw=0,ticks=0,dist_m=0.0000,A=1,B=1,edgeA=0,edgeB=0,seq=0
PINS? -> PINS:D0=0,D1=0,D2=0,D3=0,D4=0,D5=1,D6=1,D7=0,D8=0
```

HELLO_PC握手成功，末次TRAVEL仍active=0、motor_enabled=0。串口已关闭释放。GUI15项测试通过；当前编译成功。外部24V保持断开，未验证舵机实际动作、灯亮灭或编码器移动，完整训练交接给上位机协作者。历史驱动异常未解决。

---

以下为历史恢复记录，不能当作当前板上固件：

> **2026-09-11 输入组合测试版已烧录：** D7→AIN1、D8→AIN2恢复原接法。固件支持LOW/PWM/HIGH的9种组合逐项点动，状态matrix=1；普通组合最多2秒，全驱动组合2/6最多200ms，双向150计数限位及原机械行程保护保留。用户确认烧录准备完成；COM4烧录校验成功，未登记零点的9种组合均已实测拒绝，非法编号和时长拒绝，D7/D8均低。GUI14项测试和编译期保护断言通过。未执行动力测试，用户随后逐项观察；先前方向假设不能视为已证实。固件SHA256 `8be5b99a683ca12312bbac9b0cb80a9f3339941512387451fe10e6e3ca78935f`。

> **2026-09-10 15:53 最新实物状态：同PWM对照版保护固件已烧录COM4并通过写入校验。正反转只切换D7低/高，D8使用相同正数PWM，不做占空比反相。串口确认 pwm_mode=same_positive、home=0、active=0、direction=unknown，D7/D8均低。24V断开时核对，未执行运动；实际正反转效果待测试。固件SHA256：47d8aa8b1e1b7dc5cb6d9616f44e5457e214840af82424a165fd481031af5544。**

# 最新恢复状态

## 2026-09-10 15:27 正反点动版再次恢复

用户确认整套24V断开、USB连接、串口工具关闭后，已将新版根目录保护固件烧录COM4并校验成功。固件328720字节，SHA256 `c62bb5e80ff2148a8a012c26af647a4c89da08ed0a41e759a8e9cbe0a6fbcc92`。此前常转测试固件已替换。

只读回执：

```text
TRAVEL:home=0,pos=1,low=1745,high=33146,stop=1945,direction=unknown,active=0,pwm=300,control=dir_pwm_v1,reason=boot_unreferenced
BRAKE:ANGLE:0
LIGHT:OFF
PINS:D0=0,D1=0,D2=0,D3=0,D4=1,D5=1,D6=1,D7=0,D8=0
```

HELLO_PC握手成功。pos=1是编码器未供电、未建立原点时的计数，不代表物理位置。未发送HOME/JOG/PROBE/Winding，未执行外设动作。工具12项测试通过，主固件编译和行程/点动编译期断言通过；通用测试15项通过，2项Qt测试因该解释器缺少PySide6跳过。实际动力停止、离合器行为仍待现场验证。工具用的PySide6环境已单独完成12项测试。

## 以下为历史恢复记录

# 保护主程序恢复记录

时间：2026-09-09 22:53（Asia/Shanghai）。用户授权恢复主程序，并确认整套24V断开、USB保留、COM4释放；随后重插USB。发现残留Arduino串口监视器后，仅结束该监视器进程，保留编辑器，烧录成功。

- 源码提交：`4371a515285b13515ce1f99e9d374afbe6112ffb`
- 工程：仓库根目录，PlatformIO `env:d1`，WEMOS D1 R1
- 设备：COM4，ESP8266EX，MAC `e8:db:84:c2:d2:8c`
- 固件：328144字节；SHA256 `2ba47082ab17aeb61ff525247a4f475564dd4bf14d9e6841d2bec1f90e180a61`
- 上传结果：`Hash of data verified.` / `[SUCCESS]`，随后复位启动。
- 旧保护主程序源码和构建产物备份仍保留于本机 `hardware_backups/before_motor_continuous_20260909_221550/`，未发布到GitHub；独立常转测试源码保留于 `hardware_tests/motor_continuous/`。

只读串口核对（115200，无动作指令）：

```text
HELLO_PC -> ACK: HELLO_PC
TRAVEL? -> TRAVEL:home=0,pos=0,low=1745,high=33146,stop=1945,direction=unknown,active=0,pwm=300,reason=boot_unreferenced
BRAKE? -> BRAKE:ANGLE:0
LIGHT? -> LIGHT:OFF
ENC? -> ENC:raw=0,ticks=0,dist_m=0.0000,A=1,B=1,edgeA=0,edgeB=0,seq=0
PINS? -> PINS:D0=0,D1=0,D2=0,D3=0,D4=1,D5=1,D6=1,D7=0,D8=0
```

串口已关闭释放。未发送HOME、Start、PROBE或Winding；`pos=0`是未建立参考时的计数，不代表机械原点。外部24V保持断开，以上是软件读回，不是万用表测量或外设动作验证。电机异常、方向、制动惯性和完整上位机联调仍未验证。接手时先读 [AI-HANDOFF.md](AI-HANDOFF.md)。
