# SurgeryBox Next 0.1.0

**接手开发 / 使用 AI 阅读：请先看 [硬件与上位机交接](docs/AI-HANDOFF.md) 和 [AGENTS.md](AGENTS.md)。** 包含最新接线、舵机和编码器标定、已测/未测范围、电机异常及后续任务。2026-09-09 已恢复保护主程序并完成串口状态核对；机械零点和电机方向未确认，电机故障及完整联调仍待解决。

基于 [ZiliShao222/surgeryBoxProject](https://github.com/ZiliShao222/surgeryBoxProject) 的 `5d58073` 继续迭代；该工程继承自 [hEr0bR1ne/surgeryBoxProject](https://github.com/hEr0bR1ne/surgeryBoxProject) 的 `0187e78`（2.1.1）。

请先阅读 [两版比较与迭代计划](docs/comparison-and-next.md)。本次修复串口连接误报成功，清理当前源码中的硬编码 AI 密钥和被跟踪缓存，并加入回归测试。保留师生界面、双语、IMU、相机与 AI 训练记忆等上游功能。

AI 配置通过环境变量提供，示例（仅占位，需自行设置有效密钥）：

```powershell
$env:DASHSCOPE_API_KEY="YOUR_KEY"
$env:DASHSCOPE_MODEL="qwen-plus"
cd simulator
python main.py
```

本地 `app/ai_config_local.py` 可从 `app/ai_config_example.py` 复制，不再纳入 Git。历史提交可能保留旧密钥，密钥持有人需要撤销旧密钥。

开发检查（仓库根目录，无需连接设备）：

```powershell
python -m unittest discover -s tests -v
python tools/check_python_sources.py
```

下方为上游功能与操作说明。实体设备、摄像头、IMU 与完整 GUI 训练流程仍需实际验证。

---
# SurgeryBox Project 文档入口

本项目是一个面向硬膜外镇痛护理训练的软硬件一体化系统。它包含 ESP8266 外设固件、PySide6 桌面模拟训练端、拔除硬膜外导管的教学材料、题库练习、训练记录和 AI Nursing Mentor。

当前仓库的正式文档已经整理到 `docs/` 目录。建议从本文开始阅读，再按需要进入专题文档。

## 快速导航

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文档目录、维护规则、阅读路线 |
| [docs/project-overview.md](docs/project-overview.md) | 项目目标、模块划分、目录结构、当前状态 |
| [docs/setup-and-run.md](docs/setup-and-run.md) | Python 模拟器、PlatformIO 固件、UDP 测试脚本的运行方式 |
| [docs/hardware-and-protocol.md](docs/hardware-and-protocol.md) | ESP8266 固件、硬件引脚、WiFi/HTTP/UDP 协议、事件流程 |
| [docs/mobile-hardware-camera-architecture.md](docs/mobile-hardware-camera-architecture.md) | 最终有线训练站、人体模型硬件、外部摄像头、上位机低延迟融合架构 |
| [docs/simulator-training-flow.md](docs/simulator-training-flow.md) | 桌面端 UI、登录、训练流程、Quiz 与记录逻辑 |
| [docs/data-ai-and-maintenance.md](docs/data-ai-and-maintenance.md) | 数据目录、AI Mentor、配置、安全风险、维护建议 |

项目已有的教学资料仍保留在原位置：

| 资料 | 内容 |
| --- | --- |
| [simulator/assets/reading.md](simulator/assets/reading.md) | 硬膜外导管安全拔除学习材料 |
| [simulator/assets/epidural_quiz_questions.json](simulator/assets/epidural_quiz_questions.json) | Q1-Q5 题库 |

## 项目组成

```text
surgeryBoxProject/
├─ platformio.ini                  # ESP8266 / Wemos D1 PlatformIO 配置
├─ src/                            # MCU 固件实现
├─ include/                        # MCU 头文件
├─ simulator/                      # PySide6 桌面训练端
│  ├─ main.py                      # 桌面端入口
│  ├─ requirements.txt             # Python 依赖
│  ├─ app/                         # UI、训练、题库、AI、数据逻辑
│  ├─ assets/                      # 图片、音频、题库、阅读材料
│  └─ data/                        # 示例/本地训练记录
├─ models/                         # MediaPipe hand_landmarker.task
├─ udp_echo_tester.py              # UDP 基础连通测试
├─ udp_flow_tester.py              # UDP 全流程测试
├─ download_mediapipe_model.py     # MediaPipe 模型下载脚本
└─ docs/                           # 整理后的项目文档
```

## 一句话架构

ESP8266 固件创建 `surgeryBox` WiFi 热点，通过编码器检测导管拉出距离，控制舵机刹车和回卷电机，并通过 UDP 向桌面端发送 `Pain`、`HighDamp`、`LowDamp` 等事件；PySide6 桌面端负责训练 UI、Quiz、记录、学习材料和 AI 导师。当前 IMU 侧卧体位检测采用统一主控接入：IMU 接到 ESP8266，ESP8266 再通过 USB 串口 `COM3` 转发给桌面端。

## 常用运行命令

### 启动桌面模拟器

```powershell
cd D:\surgeryBoxProject\simulator
python main.py
```

注意：桌面端大量资源路径使用相对路径 `assets/...`，建议从 `simulator/` 目录启动。

### 安装 Python 依赖

```powershell
cd D:\surgeryBoxProject\simulator
pip install -r requirements.txt
```

AI Nursing Mentor 使用 `openai` SDK；当前 `requirements.txt` 已包含它。

```powershell
pip install openai
```

### 编译/上传 MCU 固件

```powershell
cd D:\surgeryBoxProject
pio run -e d1
pio run -e d1 -t upload
pio device monitor -b 115200
```

### 测试 UDP 通信

```powershell
python udp_echo_tester.py --mcu-ip 192.168.4.1 --mcu-port 4210 --local-port 4211
```

```powershell
python udp_flow_tester.py --mcu-ip 192.168.4.1 --mcu-port 4210 --local-port 4211 --start --auto
```

## 默认连接信息

| 项目 | 默认值 |
| --- | --- |
| MCU WiFi SSID | `surgeryBox` |
| MCU WiFi Password | `12345678` |
| MCU SoftAP IP | `192.168.4.1` |
| MCU UDP Port | `4210` |
| PC UDP Listen Port | `4211` |
| HTTP Echo | `http://192.168.4.1/echo` |

## 默认测试账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| Trainee | `training01` 至 `training20` | `train123` |
| Trainer | `trainer01` 至 `trainer10` | `teach123` |

## 当前重要注意事项

- 当前仓库没有统一交付版说明，`docs/` 是本次整理后的维护入口。
- Next 已停止跟踪本地 AI 配置，示例配置只读取环境变量。历史中的旧密钥需要由持有人撤销。
- `simulator/requirements.txt` 已包含 `openai`、`langgraph` 和 `pyserial`。
- `include/wifi_server.txt` 和 `src/wifi_server.txt` 是旧 TCP 方案，当前主流程使用 UDP。
- `simulator/data/UDP_Test.py` 仍测试 `TestFlow`，但当前固件 `runTestFlow()` 已禁用，UDP handler 也没有处理 `TestFlow`。
- 本次迭代范围和验证结果见 `docs/comparison-and-next.md`。

## 推荐阅读顺序

1. 先读 [docs/project-overview.md](docs/project-overview.md)，建立整体地图。
2. 如果要运行项目，读 [docs/setup-and-run.md](docs/setup-and-run.md)。
3. 如果要调硬件，读 [docs/hardware-and-protocol.md](docs/hardware-and-protocol.md)。
4. 如果要规划最终有线训练站、人体模型内硬件、外部摄像头和上位机，读 [docs/mobile-hardware-camera-architecture.md](docs/mobile-hardware-camera-architecture.md)。
5. 如果要改训练流程或 UI，读 [docs/simulator-training-flow.md](docs/simulator-training-flow.md)。
6. 如果要处理数据、AI、发布和维护，读 [docs/data-ai-and-maintenance.md](docs/data-ai-and-maintenance.md)。

## IMU 体位检测

桌面端现已支持高精度 IMU 姿态传感器的侧卧体位提示。进入拔管训练页面后，程序会从 ESP8266 的 USB 串口读取 IMU 原始数据，解析欧拉角 `roll / pitch / yaw`，并在页面中央显示：

```text
已侧卧
未侧卧，请将病人调整成侧卧状态
```

默认连接参数：

| 项目 | 默认值 |
| --- | --- |
| 串口 | `COM3` |
| 波特率 | `115200` |
| 判断轴 | `roll` |
| 合格范围 | `abs(roll)` 在 `55°` 到 `125°` 之间 |

当前 ESP8266 接线：

| IMU | ESP8266 Wemos D1 |
| --- | --- |
| `3V3` | `3.3V`，可与其他模块共用 |
| `GND` | `GND`，可与其他模块共用 |
| `TX` | `D1` |
| `RX` | 暂不接 |

`D5/D6` 已用于编码器，`D7/D8` 已用于电机，`D2` 已用于刹车舵机；IMU 不要接这些脚。

训练开始前需要连续保持侧卧 3 秒才会进入下一步。训练过程中如果检测到不再侧卧，当前任务会暂停并提示调整体位；重新侧卧并保持 3 秒后，会继续之前的任务进度。

运行前请先关闭 `UartAssist`、PlatformIO 串口监视器等串口工具，否则训练页面无法打开 `COM3`。

如果传感器侧放后仍然显示未达标，可能是安装方向导致侧卧变化体现在 `pitch` 上。启动桌面端前可以设置：

```powershell
$env:IMU_AXIS="pitch"
```

也可以修改串口号：

```powershell
$env:IMU_PORT="COM4"
```

独立传感器测试脚本：

```powershell
python tools/imu_posture_tester.py --port COM3
```
