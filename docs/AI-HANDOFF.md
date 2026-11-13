# SurgeryBox V3 3.1.6 交接

主板已烧录 **3.1.6 / API v1 / protocol=8**。上位机开发使用 `host_sdk/surgerybox_v3.py`，固件使用 `firmware/v3` 的 PlatformIO 工程。

[GitHub 发布与归档下载](https://github.com/hEr0bR1ne/surgeryBoxProject-next/releases/tag/v3.1.6)

## 接手顺序

1. 阅读接线、状态与零点规则。[硬件接口](v3-hardware-api.md)
2. 安装 `host_sdk/requirements-gui.txt`，运行 `python tools/v3_test_client.py --port COM4`。Windows 可双击 `tools/StartHardwareTest.cmd`。
3. 从 `host_sdk/example.py` 接入上位机。由一个 `SurgeryBox` 实例持有 USB 串口，按操作触发动作。断线后重新查询状态，避免重发动作。

## 当前行为

- 启动时第一个有效编码器样本作为回卷目标。测试端「设为回卷零点」和 SDK `set_home()` 可在电机空闲、编码器跟踪有效时以当前位置更新目标并清零显示。重连保留目标，MCU 重启后重新取样。
- SDK `zero()` 仅重设相对显示。编码器失去连续性会使回卷零点失效，须重启主板以重新取样。
- 拉出时计数增加。D8 回卷时计数递减，到达零点关断，等待 50 ms 后用 D7 释放摩擦轮 1 秒。无拉出距离上限和提前停车死区。
- 舵机释放 180°、弱阻尼 90°、锁紧 30°，指令速度 75°/秒。回卷在释放缓动完成并等待 500 ms 后开始。
- 灯 D3 高有效。MT6701 I²C 地址为 0x06，每圈 16384 计数，累计跨圈。工程未标定毫米换算。
- 错向、编码器异常、无进展或失联会停车，连续回卷上限 120 秒。故障、STOP 和 SAFE 不触发自动反向。

## 上位机对接

用 `position()` 和 `status()` 显示位置与状态，用 `set_brake()`、`set_light()` 对接训练动作，用 `wind()`、`release()`、`finish()`、`stop()` 和 `safe_off()` 管理回卷。UI 需要交由用户设定回卷目标时调用 `set_home()`。

用同一任务 token 的 `preparing=0`、`active=0` 和 `reason=release_complete` 判断正常完成。`ACCEPTED` 表示固件已接单。训练界面与新 SDK 的业务整合由接手者完成。

## 验证

- PlatformIO 构建及策略静态检查、13 项 SDK 测试和 15 项测试端测试通过。290592 字节固件写入校验通过。
- 操作者以手动零点 0 从 11913 计数启动回卷。日志确认 D8 收线、D7 释放，任务结束时 `pos=home=0`、D7/D8 均低。释放中曾采到 −1 计数，机械采样与惯性仍可能带来超调。
- 3.1.0 曾记录首次舵机启用时一次 Windows COM4 error5。根因未确认，3.1.6 未针对该问题做专项复测。

[实机验证](v3-hardware-validation.md) · [镜像与证据](../releases/surgerybox-v3-3.1.6/)
