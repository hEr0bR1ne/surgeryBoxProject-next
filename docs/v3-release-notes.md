# SurgeryBox V3 3.1.0 · 上位机交接

本版交付第三代MCU固件、Python SDK、全功能桌面测试端及接线/接口/验证文档，供上位机开发者接入。
固件3.1.0，API v1，protocol=8；已写入WEMOS D1 R1并完成写入校验。

## 功能

- MT6701 14位I2C编码器：每圈16384计数，累计跨圈，读取相对位置、角度和圈数。
- 上电位置自动作收回零点；无需登记两端，无拉出距离上限或提前停止死区。
- 回卷返回上电零点即关闭方向2，再停50ms、方向1释放摩擦轮1秒并停止。
- 舵机180°/120°/50°，75°/秒缓动；准备完成后500ms才允许回卷。
- D3高有效灯控制，独立状态查询、急停、全部关闭和日志导出。
- 串口指令ID/boot关联、独立心跳和任务租期；断线不自动重放动作。

## 接入

安装`host_sdk/requirements-gui.txt`后，运行`python tools/v3_test_client.py --port COM4`，或Windows双击`tools/StartHardwareTest.cmd`。
上位机开发者先读`docs/AI-HANDOFF.md`和`docs/v3-hardware-api.md`，使用`host_sdk/surgerybox_v3.py`。
只使用`firmware/v3`构建当前固件；根目录主程序和旧protocol=7 SDK不适用于新版。

ZIP内包含固件镜像/源码、SDK、测试端、文档、逐文件SHA256清单和烧录/现场验证证据。

## 验证与已知问题

构建和策略静态检查、13项SDK测试、13项GUI测试、25次隔离状态只读查询通过。
用户完成舵机、灯和回卷测试，回卷任务返回release_complete，编码器错误和固件丢帧均为0。

首次重新启用舵机仍记录过一次Windows串口error5，重连后操作成功，根因未完全排除。
一次回卷完成位置为pos=86、home=0，存在少量采样/惯性超零；未进行毫米标定。
训练界面与新SDK的业务流程整合由接手者完成；本版没有自动迁移旧模拟器流程。
