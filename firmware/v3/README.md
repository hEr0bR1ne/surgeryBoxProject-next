# SurgeryBox V3固件3.1.0 / protocol=8

当前源码为上电零点版：第一次有效编码器读取自动记收回零点；无人工两端标定、无拉出上限、无提前停车死区。
舵机75°/秒，较3.0.1加快50%；回卷等待缓动结束后500ms。方向2回到上电零点即关闭，50ms后方向1释放1秒。
方向2在本机已验证为编码器计数增加。保留编码器/失联/错向/堵转停止，连续回卷上限120秒。
当前COM4已在用户确认执行器隔离后烧录3.1.0，290464字节Hash通过，25次只读状态检查通过。不能使用旧protocol=7的SDK或测试端连接新版。

```powershell
platformio run -d firmware/v3
platformio run -d firmware/v3 -t upload --upload-port COM4
```

烧录前隔离驱动板VM/VCC与舵机正极；D8/GPIO0在复位期间不能保证低电平。
用户选择当前上电位置为目标，不自动寻找机械端点。10ms采样及惯性可能造成少量物理超调，不能保证绝不越零。
接口见`docs/v3-hardware-api.md`，状态证据见`docs/v3-hardware-validation.md`。
