> 最新交接状态请先读 [AI-HANDOFF.md](AI-HANDOFF.md)。本文包含历史说明或逐次测试记录，部分状态已被后续记录更新。

# 硬件固件与通信协议

本文档说明 MCU 侧固件结构、硬件引脚、WiFi/HTTP/UDP 协议、事件状态机和调试方式。

## 固件入口

入口文件：

```text
src/main.cpp
```

`setup()` 主要初始化：

| 调用 | 作用 |
| --- | --- |
| `Serial.begin(115200)` | 串口日志 |
| `initWiFiHotspotUDP("surgeryBox", "12345678", 4210)` | 创建 WiFi 热点并监听 UDP |
| `initHttpEchoServer()` | 启动 HTTP `/echo` |
| `encoderInit()` | 初始化编码器 |
| `servoBrakeInit()` | 初始化刹车舵机 |
| `motorInit()` | 初始化回卷电机 |
| `eventsInit()` | 初始化事件距离数组 |
| `signalTesterInit()` | 初始化串口到 UDP 测试工具 |

`loop()` 持续处理：

| 调用 | 作用 |
| --- | --- |
| `handleUDPMessages()` | 处理上位机 UDP 指令 |
| `handleHttpServer()` | 处理 HTTP echo |
| `processEncoderEvents()` | 根据距离触发事件 |
| 实时距离日志 | 每 200ms 检查位置变化并发送 `POS` / `SPEED` |
| `signalTesterLoop()` | 串口输入转 UDP |

## 硬件引脚

当前代码中的引脚定义如下：

| 模块 | 引脚 | 文件 |
| --- | --- | --- |
| 编码器 A | `D5` | `src/encoder.cpp` |
| 编码器 B | `D6` | `src/encoder.cpp` |
| 刹车舵机 | `D2` | `src/servo_brake.cpp` |
| 电机 A | `D7` | `src/motor.cpp` |
| 电机 B | `D8` | `src/motor.cpp` |
| IMU 串口接收 | `D1` | `src/imu_bridge.cpp` |

IMU 体位传感器由 ESP8266 统一接入电脑。当前接线：

| IMU | ESP8266 Wemos D1 |
| --- | --- |
| `3V3` | `3.3V`，可与其他模块共用 |
| `GND` | `GND`，可与其他模块共用 |
| `TX` | `D1` |
| `RX` | 暂不接 |

ESP8266 固件使用 `SoftwareSerial` 从 `D1` 读取 IMU 数据，并把原始二进制帧转发到 USB 串口。桌面端仍读取 `COM3 / 115200`，继续用原有欧拉角解析和侧卧判断逻辑。`D5/D6`、`D7/D8`、`D2` 已被现有硬件占用，不要再接 IMU。

## 编码器换算

`src/encoder.cpp` 中当前参数：

```cpp
float distancePerTick = 0.0000507;
const int ENCODER_SIGN = -1;
```

注释说明：

```text
29589 ticks for 1.5 m => 1 tick ≈ 0.0000507 m
```

`readDistance()` 返回米，`readTicks()` 返回带方向修正后的 tick。

主循环中会换算为厘米发送：

```text
POS:<cm>
SPEED:<cm/s>
```

## 刹车舵机

`src/servo_brake.cpp` 中当前角度：

| 状态 | 函数 | 角度 |
| --- | --- | --- |
| 锁死 | `servoBrakeLock()` | `150` |
| 弱阻尼 | `servoBrakeWeak()` | `120` |
| 释放 | `servoBrakeRelease()` | `90` |

## 电机回卷

`src/motor.cpp` 中：

| 函数 | 作用 |
| --- | --- |
| `motorForward()` | 正转 |
| `motorReverse()` | 反转 |
| `motorStop()` | 停止 |
| `motorWindBack()` | 回卷直到 `readDistance() <= 0.5` |

注意：`motorWindBack()` 中停止条件是 `readDistance() > 0.5`，单位为米。是否符合实际回卷终点，需要结合机械结构复核。

## WiFi 与 HTTP

当前主流程使用 UDP 方案：

| 项目 | 值 |
| --- | --- |
| SSID | `surgeryBox` |
| Password | `12345678` |
| Board IP | `192.168.4.1` |
| UDP Port | `4210` |
| HTTP Port | `80` |
| Echo Path | `/echo` |

HTTP echo 用于桌面端连接测试：

```text
POST /echo
Body: Hello
Response: Hello
```

## UDP 基础行为

MCU 使用最近一次发来 UDP 包的远端地址和端口作为回包目标。

因此 PC 端应该先发送：

```text
HELLO_PC
```

或者任意 UDP 消息，让 MCU 记录：

```cpp
lastRemoteIp
lastRemotePort
```

否则 MCU 调用 `sendUDPMessageToLast()` 时可能没有目标。

## 上位机到 MCU 指令

| 指令 | MCU 行为 | 回包 |
| --- | --- | --- |
| `Start` | 启动事件序列 | Echo、`SEQ:...`、`ACK: Start` |
| `Stop` | 舵机锁死 | Echo、`ACK: Stop` |
| `Winding` | 电机回卷 | Echo、`ACK: Winding` |
| `OK` | 高阻力解除等待中使用 | 通常被 `waitForCmd("OK")` 消费 |
| `OK1` | 低阻力后直接释放 | 通常被 `waitForCmdAny({"OK1","Continue"})` 消费 |
| `Continue` | 低阻力后继续短拉 | 通常被 `waitForCmdAny({"OK1","Continue"})` 消费 |
| `OK2` | `Keep` 后释放 | 通常被 `waitForCmd("OK2")` 消费 |
| 其他 | Echo + ACK | `ACK: <msg>` |

## MCU 到上位机消息

| 消息 | 含义 |
| --- | --- |
| `SEQ:<idx>,<pain>,<pain2>,<highDamp>,<lowDamp>` | 本次随机事件距离，单位 cm |
| `POS:<value>` | 当前拉出位置，单位 cm |
| `SPEED:<value>` | 当前拉出速度，单位 cm/s |
| `Pain` | 第一次疼痛/尖叫事件 |
| `Pain2` | 第二次疼痛/尖叫事件 |
| `HighDamp` | 高阻力事件，MCU 会锁死刹车并等待 `OK` |
| `LowDamp` | 低阻力事件，MCU 会弱阻尼并等待 `OK1` 或 `Continue` |
| `Keep` | 低阻力后继续短拉仍需处理，等待 `OK2` |
| `ACK: ...` | MCU 对收到指令的确认 |

## 事件距离

`src/events.cpp` 预设 10 组距离，单位为米：

```text
Pain:     0.05 - 0.15 m
Pain2:    0.15 - 0.25 m
HighDamp: 0.25 - 0.35 m
LowDamp:  0.35 - 0.45 m
```

收到 `Start` 时 MCU 随机选择一组，设置为 `currentArray`，并发送 `SEQ` 给上位机。

## 事件状态机

### Start

```text
PC -> MCU: Start
MCU:
  1. random(0, 10) 选择距离数组
  2. sequenceRunning = true
  3. eventTriggered[] = false
  4. 发送 SEQ
  5. 发送 ACK: Start
```

### Pain / Pain2

```text
if distance >= currentArray[0]:
    send Pain

if distance >= currentArray[1]:
    send Pain2
```

这两个事件只发送信号，不控制刹车。

### HighDamp

```text
if distance >= currentArray[2]:
    send HighDamp
    servoBrakeLock()
    waitForCmd("OK")
    servoBrakeRelease()
```

### LowDamp

```text
if distance >= currentArray[3]:
    send LowDamp
    servoBrakeWeak()
    waitForCmdAny("OK1", "Continue")

    if OK1:
        servoBrakeRelease()

    if Continue:
        waitShortPull()
        send Keep
        waitForCmd("OK2")
        servoBrakeRelease()

    sequenceRunning = false
```

注意：`waitShortPull()` 当前等待距离增加 `0.5` 米。若产品设计中“短拉”应是更短距离，应调整或标定。

## 串口调试

`signalTesterLoop()` 支持在串口监视器中输入一行文本并通过 UDP 发给最近客户端。

示例：

```text
Pain
OK1
Start
```

这对快速测试上位机接收逻辑很有用。

## 旧 TCP 方案

仓库中仍保留：

```text
include/wifi_server.txt
src/wifi_server.txt
```

这两个文件是旧 TCP WiFi server 方案，端口 `1234`，SSID `SurgeryBox`。当前 `src/main.cpp` 中 legacy TCP 调用已经注释，主流程使用 `wifi_udp_server`。

后续建议：

- 如果不再使用，移动到 `docs/archive/` 或删除。
- 如果仍需保留，改名为 `.h/.cpp` 之外的明确归档文件，并在 README 标注“非当前主流程”。

## 推荐调试顺序

1. 串口确认固件启动成功。
2. PC 连接 `surgeryBox` 热点。
3. 使用桌面端 `Simulator` 页面测试 HTTP echo。
4. 使用 `udp_echo_tester.py` 测试基础 UDP 收发。
5. 使用 `udp_flow_tester.py --start --auto` 测试完整事件流。
6. 最后进入桌面端 `Removal of epidural catheter (Simulator)` 测试 UI 集成。

