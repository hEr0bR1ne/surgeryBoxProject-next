> **最新实物状态：2026-09-11T01:08:29（本机北京时间），电机禁用的上位机联调主程序已烧录COM4，写入校验通过。实测19条电机命令全部返回ERROR: motor_disabled_handoff；motor_enabled=0、matrix=0、active=0、D7/D8均低。舵机指令0°、LIGHT:OFF及ENC?查询正常。24V断开期间核对，未测试外设实际动作。COM4已释放。**

# SurgeryBox 硬件与上位机交接（AI 首读）

更新日期：2026-09-09。本文件是本次交接的状态摘要。较早文档中的引脚、角度、测试计划和“尚未烧录”记录可能已经过时，以本文件的状态和对应源码为准；不能把已写代码等同于实机验证通过。

## 给接手者 / AI 的任务

用户已完成下面列出的硬件单项测试，上位机联调由接手者负责。请先阅读本文件、根目录 `AGENTS.md` 和对应代码，不要求用户重新口述所有历史。先在无电机输出条件下检查上位机流程；电机异常单独处理。涉及实物状态、接线变更、上电或刷写，必须先核实现场现状，不能默认仍是本文记录的状态。

可直接把这段作为 AI 初始任务：

> 请先阅读 AGENTS.md 和 docs/AI-HANDOFF.md，区分“已实测”“仅实现”“未解决”。接手上位机与 ESP8266 联调，保留舵机标定和物理行程限制。不要启动电机、假定电机方向已确认或假定当前板上是主程序；先核实运行固件。在不涉及电机动作的范围内完成代码检查和测试，列出完整训练流程还缺哪些实机验证，再继续推进。

## 当前上位机联调版（2026-09-11）

用户决定暂停电机故障排查，交由另一位协作者开展上位机联调。当前源码在 `include/config.h` 固定 `MOTOR_OUTPUT_ENABLED=false`；本次烧录结果另见 `main-firmware-restoration.md`，不能用代码完成代替烧录确认。

- 电机D7/D8启动为低。`Winding`、MF/MR、MotorForward/MotorReverse以及所有 `MOTOR:` 设置、PROBE、JOG、MATRIX命令均拒绝，返回 `ERROR: motor_disabled_handoff`。内部启动函数也拒绝输出，不能通过串口解锁。
- `TRAVEL?` 返回 `motor_enabled=0`、`matrix=0`、`active=0`。MS和Stop仍可用；Stop依然锁紧舵机125°，不是仅停电机。
- 舵机0°/55°/125°标定、编码器读数和训练事件、实体血迹灯、USB串口/UDP接口保留。电机物理零点不是开展灯/舵机/编码器联调的前提；不要为了联调在任意位置登记机械原点。
- 上位机应显示“电机暂不可用”，不能把Winding拒绝当作完成回卷，也不能无限等待成功回执。现有 `training_remove_needle_mcu.py` 有发送Winding的入口，接手者需据此处理提示/跳过电机步骤；未伪造完成回执。
- 电机故障仍未解决。用户最终组合反馈：AIN2低（0/3/6）不转，AIN2为PWM（1/4/7）同向转，AIN2高（2/5/8）高速同向转；这是用户观察，不是示波器实测。此前输入反插曾观察到离合器脱离，之后恢复D7→AIN1、D8→AIN2进行组合测试。不能认定正常反向回卷已验证。
- 当前GUI电机测试工具遇到禁用固件会明确提示不可用。独立常转固件和旧组合固件仅保留为历史排查资料，不用于本次上位机联调。

## 硬件接线与电源

板型：**WEMOS D1 R1 / PlatformIO `board = d1`，不是 D1 mini。** 本机串口曾为COM4，其他电脑须自行枚举。

| 功能 | 板上引脚 | ESP8266 GPIO | 说明 |
| --- | --- | --- | --- |
| 舵机刹车信号 | D2 | 16 | 用户已验证可转，完成角度标定 |
| 血迹灯 MOS 控制 | D3 | 5 | 高电平亮，低电平灭 |
| 编码器 A 相 | D5 | 14 | 双边沿计数 |
| 编码器 B 相 | D6 | 12 | 双边沿计数 |
| 电机 AIN1 | D7 | 13 | 当前配置，电机故障未解决 |
| 电机 AIN2 | D8 | 0 | GPIO0 是启动配置脚；复位/下载期不受程序限位保护 |
| USB 串口 | D0 / D1 | 3 / 1 | RX / TX，不能误认成其他板型的D1/D2映射 |

电源事实：主板连接电脑USB。**编码器、电机、舵机、灯全部最终来自外部24V，经各自所需的降压/驱动电路供电。** 不是所有元件的输入端都直接接24V。切断整套24V也会切断编码器供电，期间移动不会被记录。

用户万用表确认：驱动板VCC由降压输出供电，实测4.98V；VM为24V；主板与驱动板GND导通；D7↔AIN1、D8↔AIN2导通；电机与控制输入属于同一A通道。

## 标定值与验证范围

| 项目 | 结果 | 验证程度 |
| --- | --- | --- |
| 舵机释放 / 弱阻尼 / 锁紧 | **0° / 55° / 125°** | 用户用舵机调试工具实测并导出，已整合 `src/servo_brake.cpp` |
| 血迹灯 | GPIO5高电平亮；LIGHT:ON/OFF | 用户确认看见实体灯亮灭；上位机完整训练联动尚待验证 |
| 编码器 | 手动正反转计数增减，两相信号均有反馈，停住计数稳定 | 已实测 |
| 最大手动行程 | **34891 ticks** | 在用户指定原机械零点清零后拉到底、停留再回转；串口采样峰值 |
| 控制上下限 | **1745～33146 ticks** | 两端各内缩约5%；软件配置，不是实测动力停止范围 |
| 暂定回卷提前断驱动点 | **1945 ticks** | 比下限提前200ticks；停机惯性尚未验证 |
| 距离系数 | **0.0000507 m/tick** | 历史值，本次未用尺重新标定；不要把显示米数当实测 |
| 电机方向、收线、停车惯性 | 未确认 | 见下文故障；完整回卷未通过 |

机器可读记录：`hardware_tests/servo_calibration.json`、`hardware_tests/encoder_range_calibration.json`。舵机角度是指令值，不是角度传感器或刹车力测量。

## 电机未解决问题：已确认观察，不是诊断结论

模块商品名称为“A4950双路电机驱动模块 直流有刷电机驱动板模块 超TB6612”。淘宝短链接无法从检索工具读取完整原理图，**实物模块是否与标准A4950外围电路完全一致尚未核实**。

1. 曾以PWM300/1023约29%输出，在中段分别测试R/F方向，先150ms、再500ms；编码器没有位移。用户曾观察到声音/轻微抖动或轴转，但不卷线。
2. 改为最多2秒、PWM512约50%，F方向测试前位置14680，结束仍14680。用户后来使用GUI自行调至PWM663等，反馈电机仍无明显动作。GUI日志确认命令被接收、进入probing，约2秒后MS停止，不是按钮没有发命令。
3. 用独立常转固件排除PWM、串口定时、编码器限位。串口确认GPIO13=1、GPIO0=0；用户在驱动板端测得AIN1约3.3V、AIN2约0V，但电机仍不转，电机两端报告0V。
4. **D7/D8两根控制线接上时不转，拔掉后电机反而转。** 拔线后的两路输入电平、输出电压、持续转动方向尚未记录。不能据此就认定是反相控制或普通悬空。
5. **用户意外短接ESP8266主板5V与GND时，电机转；解除短接后立即不转。** 短接的是主板，不是驱动板。未确认短接时主控是否复位、引脚状态和各路电压。不得重复短接作为诊断手段。
6. 用户已确认供电、共地、同通道与连线导通。不要把这些当作从未检查过；如需重测应说明新的目的。没有证据可以直接认定某个器件损坏，也不能因软件读回高低就认定真实驱动波形完全正确。

官方参考：[Allegro A4950 datasheet](https://www.allegromicro.com/-/media/files/datasheets/a4950-datasheet.pdf)，第3页：高电平门限2V，低电平上限0.8V，内部约50kΩ下拉；第4页：10/01方向相反，00高阻滑行/待机，11制动。一路PWM、另一路低属于标准控制方式。两输入断开后主动持续转动不是标准默认行为。模块厂商[同类双路板说明](https://easyelecmodule.com/product/a4950-dual-motor-drive-module/)区分VCC5V和VM，但不能把同类说明当成该淘宝实物的原理图。

罗老师将协助判断。后续应根据实物电路/真实输入输出状态定位，不要只提高PWM、延长时间或无依据更换接线。常转程序只用于与卷线负载机械脱离后的空载台架验证。

## 主程序目前实现的协议与限制

固件115200波特率，换行结束命令；根目录主程序也支持UDP4210和HTTP echo。WiFi/串口具体入口见 `src/wifi_udp_server.cpp`。

| 命令 | 行为 / 注意事项 |
| --- | --- |
| HELLO_PC | 回复ACK: HELLO_PC；连接成功须核实身份 |
| ENC? | 相对计数、旧系数距离、A/B电平与边沿次数、训练状态 |
| ZERO / Start | 重置训练相对计数，不重置新增物理限位计数；电机运行时拒绝 |
| TRAVEL? | home、pos物理计数、low/high/stop、direction、active、pwm、reason |
| TRAVEL:HOME | 用户在原机械零点确认后登记物理零点；必须电机/训练空闲，禁止自动发送 |
| MOTOR:PWM / PROBE / JOG / MATRIX | 当前联调版全部拒绝：ERROR: motor_disabled_handoff |

| Winding | 当前联调版拒绝，不返回回卷成功；上位机需显示暂不可用 |
| MF / MR | 旧直驱命令已禁止，不能绕过保护 |
| MS | 保持两路低电平并回复ACK: MotorStop；不等于断开24V |
| Stop | 停电机并锁紧刹车125°；不同于仅停止电机的MS |
| BR / BW / BL | 舵机释放0° / 弱阻尼55° / 锁紧125° |
| BRAKE? / BRAKE:ANGLE:n | 查询指令角度 / 空闲时0～125°、单次最多5°微调 |
| LIGHT:ON / OFF / LIGHT? | 实体灯控制和指令状态回读，不是光传感器测量 |

`encoder.cpp` 中物理计数与相对计数分开，`motor.cpp` 上电物理参考无效；不能用断电后的旧计数恢复绝对位置。电机保护在主循环和原等待循环调用；完整回卷的无净反馈上限500ms、总时长15s，方向反向超过8ticks停机。试转无反馈等待单独为2s。保护是软件逻辑，尚不能保证实际机械停车不超界。

## 上位机交接重点

- `simulator/app/hardware/serial_connector.py`：串口握手与收发；USB串口默认COM4，可用 `SURGERYBOX_SERIAL_PORT` 覆盖，避免默认DTR/RTS引起复位，但仍需读回实际固件/零点。
- `simulator/app/hardware/blood_light.py`：实体灯指令确认、重试和退出关闭。
- `simulator/app/ui/blood_light_training.py`：训练界面灯控制接入。
- `training_remove_needle.py` 与 `training_remove_needle_mcu.py`：阶段3.5用实体灯替代虚拟血迹，默认 `SURGERYBOX_BLOOD_LIGHT=1`；设0回退虚拟显示。
- 带相机流程仍保留原约8秒自动擦拭完成逻辑，灯灭不一定代表视觉识别擦拭成功；纯MCU模式 `disable_camera` 会跳过阶段1～3.5，所以不能假定该模式一定点灯。
- 目前代码存在并有自动测试，不代表已经验证过真实相机/IMU/完整训练；当前主固件的IMU桥初始化与循环处于禁用状态。
- 接手者应补测：真实串口握手、灯确认与阶段切换、传感器距离事件、刹车预设、中途退出/停止/断连、完整训练与数据记录。先隔离电机动作，不能直接拿常转固件联调。

## 工具、备份与复现

| 路径 | 用途 |
| --- | --- |
| hardware_tests/servo_tuner | 舵机GUI与配套独立固件 |
| hardware_tests/motor_tuner | 电机GUI，使用主程序；F/R、PWM、时间、位置、停止原因、JSON导出；不自动连接或启动 |
| hardware_tests/encoder_only | 编码器独立固件，复用主解码代码，无执行器初始化 |
| hardware_tests/motor_continuous | 用户手动烧录的常转程序；无软件停止功能 |
| hardware_tests/servo_manual、servo_only | 早期单舵机测试，不是主程序 |
| tools/encoder_logs | 手动量程与短脉冲测试原始记录；部分早期脚本会操作硬件，运行前读源码 |

主固件源码始终保留在 `src/`、`include/`。常转测试之前已做本地备份：`hardware_backups/before_motor_continuous_20260909_221550/`，含源码ZIP、firmware.bin/elf及哈希清单。**该目录被Git忽略，不在GitHub中**；需要原二进制可向用户索取，或从本仓库编译主固件。备份是本地构建产物，不是设备Flash全量读取。旧firmware.bin SHA256：`2ba47082ab17aeb61ff525247a4f475564dd4bf14d9e6841d2bec1f90e180a61`。RAM中的零点、PWM和方向确认不随备份恢复。

无硬件验证命令（仓库根目录）：

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s hardware_tests/motor_tuner -p test_motor_tuner.py -v
python -m unittest discover -s hardware_tests/servo_tuner -p test_tuner.py -v
python tools/check_python_sources.py
python -m platformio run
```

GUI测试需要PySide6，可使用 `QT_QPA_PLATFORM=offscreen`。板型工具链需PlatformIO；本次实际版本为espressif8266 4.2.1 / Arduino core 3.1.2。`tests/travel_limits_compile_test.cpp` 可用ESP8266工具链的g++以 `-std=c++11 -fsyntax-only -I include` 检查。不要把upload或硬件测试脚本当普通CI测试自动运行。

本次尚未完成：真实完整上位机训练联调、准确长度换算、电机驱动异常定位、收线方向确认、惯性停止余量、动力回卷全程验证。

交接发布前检查：主项目17项、电机GUI9项、舵机GUI7项测试全部通过；61个已跟踪Python文件语法与凭据模式检查通过；限位C++编译期检查通过。测试未连接或驱动现场硬件，不能替代上面的待完成实机验证。
