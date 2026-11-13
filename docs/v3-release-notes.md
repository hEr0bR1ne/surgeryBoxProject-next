# SurgeryBox V3 3.1.6

面向训练上位机交接，包含 MCU 固件、Python SDK、桌面测试端、接线与接口说明。固件 API v1，串口 protocol=8。

- 上电自动设回卷零点。测试端「设为回卷零点」、SDK `set_home()` 和串口 `HOME:SET` 可把当前位置设为实际回卷目标，同步清零显示，重启后重新采集。
- 适配当前绕线方向。向外拉出时计数增加，D8 回卷时计数递减，到零后停 50 ms，再由 D7 释放摩擦轮 1 秒。
- 舵机预置为释放 180°、弱阻尼 90°、锁紧 30°，速度 75°/秒。
- 通过固件写入校验、28 项 SDK 与测试端测试，以及从 11913 计数回到手动零点的实机测试。任务返回 `release_complete`，最终位置与零点均为 0。

下载归档 ZIP 可以取得已烧录镜像、固件源码、测试端、SDK、交接说明与校验记录。解压后先读 `docs/AI-HANDOFF.md`，Windows 测试入口为 `tools/StartHardwareTest.cmd`。

过往舵机首次启用的串口 error5 根因尚未确认。训练业务界面接入由上位机开发者完成。

[交接说明](AI-HANDOFF.md) · [实机验证](v3-hardware-validation.md)
