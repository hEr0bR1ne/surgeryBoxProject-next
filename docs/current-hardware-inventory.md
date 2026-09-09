> 最新交接状态请先读 [AI-HANDOFF.md](AI-HANDOFF.md)。本文包含历史说明或逐次测试记录，部分状态已被后续记录更新。

# 当前 ESP8266 功能、接线与扩展基线

核对日期：2026-09-09。源码基线：Next `6449c23`。这是代码规定的接线，不等于已经检查过实物。

## 开发板与引脚映射

`platformio.ini` 使用 `board = d1`，本机 PlatformIO 配置解析为 WEMOS D1 R1。Arduino ESP8266 3.1.2 的 `variants/d1/pins_arduino.h` 定义如下。不要套用 D1 mini / NodeMCU 的 D 编号表。

| 外设信号 | 代码引脚 | 当前编译的 GPIO | 状态 |
| --- | --- | --- | --- |
| 编码器 A | D5 | 14 | 输入上拉，CHANGE 中断 |
| 编码器 B | D6 | 12 | 输入上拉，CHANGE 中断 |
| 刹车舵机信号 | D2 | 16 | Servo 输出；源码 GPIO4 注释不符合当前配置 |
| 电机驱动器控制 A | D7 | 13 | 数字输出 |
| 电机驱动器控制 B | D8 | 0 | 数字输出；GPIO0 同时参与启动模式选择 |
| USB 串口 TX | D1 / TX | 1 | Serial 输出 |
| USB 串口 RX | D0 / RX | 3 | Serial 输入 |
| 历史 IMU RX / 占位 TX | D1 / D0 | 1 / 3 | 初始化已关闭；按 R1 映射与硬件串口冲突 |

电机表中的 A/B 是驱动器逻辑输入，不是电机两根电源线。仓库不能确认驱动器型号、EN/STBY 接法、舵机额定电源和编码器供电/输出电平，因此不能从软件反推出完整电源接线。电机和舵机应按其驱动器/器件规格供电，信号侧需共同参考地。

依据：[Arduino R1 引脚定义](https://raw.githubusercontent.com/esp8266/Arduino/3.1.2/variants/d1/pins_arduino.h)。GPIO0 复位时拉低会进入下载模式，电机驱动输入不能破坏正常启动要求，见 [Espressif 启动说明](https://docs.espressif.com/projects/esptool/en/latest/esp8266/advanced-topics/boot-mode-selection.html)。

## 已实现的功能

| 功能 | 当前行为 |
| --- | --- |
| 编码器测量 | 双相计数、方向判断、拉出距离；系数 0.0000507 m/tick，符号 -1，仍需实物标定 |
| 实时遥测 | 序列运行时约每 200 ms 发送 POS（cm）和 SPEED（cm/s） |
| 训练序列 | Start 清零并从 10 组固定阈值中随机选择一组，发送 SEQ |
| Pain / Pain2 | 到距离后发送事件；不是力传感器或疼痛检测 |
| HighDamp | 锁刹车，等待 OK，再释放 |
| LowDamp | 弱刹车；OK1 释放，Continue 进入继续拉出分支 |
| Keep | Continue 后额外拉出 0.5 m 才发送 Keep，再等 OK2 释放；虽函数名叫 short pull，实际是 50 cm |
| 舵机刹车 | 释放 0°、弱阻尼 55°、锁定 125°（2026-09-09 实机标定）；上电初始化为释放 |
| 电机手动控制 | 正转、反转、停止；没有已接入的速度调节，PWM_SPEED 常量未使用 |
| 电机回卷 | ticks≤25 停止，超过 15 s 停止，计数错误增加超过初值 200 ticks 时切换一次方向；采用软件位置判定，无实体限位输入 |
| Stop | 停电机并锁刹车；普通处理分支不直接清除 sequenceRunning，不能等同于完整训练状态复位 |
| 诊断 | 原始/带符号计数、距离、AB 电平、边沿次数、序列状态、D0–D8 电平快照、编码器清零 |
| USB 串口 | 默认 PC COM6 / 115200，按行发送文本指令，支持精确 HELLO_PC 握手检查 |
| WiFi UDP | 热点 surgeryBox，密码 12345678，默认板 IP 192.168.4.1、端口 4210；PC 通常监听 4211 |
| HTTP | 80 端口 /echo 原样回显；没有执行电机/训练命令 |

预设实际阈值范围：Pain 5–14 cm，Pain2 17–25 cm，HighDamp 26–35 cm，LowDamp 36–45 cm。

## 指令全集

指令区分大小写。USB 串口以换行结束；UDP 每个数据报一条指令。

| 指令 / 别名 | 意义 |
| --- | --- |
| HELLO_PC | 连通性探测，普通处理状态回复 ACK: HELLO_PC |
| Start | 清零并启动距离事件序列 |
| Stop | 电机停止、锁刹车 |
| Winding | 启动回卷 |
| MF / MotorForward | 释放刹车、正转 |
| MR / MotorReverse | 释放刹车、反转 |
| MS / MotorStop | 停电机，不主动改变刹车角度 |
| BR / BrakeRelease | 释放刹车 |
| BL / BrakeLock | 锁刹车 |
| BW / BrakeWeak | 弱阻尼 |
| ENC / ENC? | 编码器诊断 |
| ZERO / RSTENC / RESET_ENC | 清零计数及边沿诊断；不是机械回零 |
| PINS / PINS? | D0–D8 电平快照 |
| OK | HighDamp 等待阶段确认 |
| OK1 | LowDamp 等待阶段确认释放 |
| Continue | LowDamp 等待阶段继续拉出 |
| OK2 | Keep 后确认释放 |

上报包括原始命令回显、ACK、SEQ、POS、SPEED、Pain、Pain2、HighDamp、LowDamp、Keep、ENC、PINS 和串口日志。回卷完成/超时目前是日志输出，没有统一的独立完成事件。

普通命令分支也会对未知命令回复 ACK，因此 ACK 不保证实现了动作。旧 TestFlow 已禁用；HTTP reset 仅回显，不能复位硬件。阻塞等待阶段的命令处理与普通状态并不完全一致。

## IMU、摄像头与上位机

当前默认拓扑：PC USB → ESP8266（COM6）；PC 另一串口 → IMU 数据源（COM3）；摄像头由 PC 读取。

- IMU 数据读者位于 PC，115200 baud，解析 roll/pitch/yaw；默认 abs(roll) 在 55°–125° 判为侧卧，持续 3 秒通过体位门控。偏离时暂停桌面训练，恢复侧卧保持后继续；不应将桌面暂停等同于固件独立硬件互锁。
- 固件的 IMU 桥接初始化与主循环调用已注释。历史注释“IMU TX 接 D1”不是当前可直接照接的方案；R1 的 D1 又是 GPIO1/串口 TX。
- 摄像头、手势识别、语音/音乐、AI 报告与训练记忆在 PC，未通过 ESP8266 采集图像或执行 AI。
- `SURGERYBOX_HARDWARE_TRANSPORT` 默认 serial，`SURGERYBOX_SERIAL_PORT` 默认 COM6，`SURGERYBOX_SERIAL_BAUDRATE` 默认 115200。IMU 使用独立 `IMU_PORT`、`IMU_BAUD`、`IMU_AXIS`。
- MCU 训练类有 `SURGERYBOX_AUTO_REWIND` 开关，默认 0；不能把“训练结束自动回卷”视为默认开启。

## 新增功能前的资源边界

R1 上 GPIO4（D4/D14）、GPIO5（D3/D15）未被当前启用的外设占用，可作为扩展候选；GPIO2（D9）、GPIO15（D10）涉及启动要求。别名 D11/D12/D13 对应已占用的 GPIO13/12/14，不是额外独立引脚。A0 未使用，但量程取决于实物板分压电路，暂不指定接法。

当前没有力/压力传感器、实体回零限位、独立急停输入、断线自动停机状态机或电机闭环调速实现。上述是待开发能力，不能作为现有能力使用。

在决定扩展接线前，需要确认实物板完整型号（D1 R1、D1 R2、D1 mini 或 NodeMCU）以及要新增的器件型号/功能。此次仅整理文档，未改变固件或刷机。
