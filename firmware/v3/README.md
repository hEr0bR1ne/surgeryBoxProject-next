# SurgeryBox V3 固件 3.1.6 / protocol=8

WEMOS D1 R1 通过 USB 串口连接上位机，115200 波特。首个有效编码器样本设为回卷零点，`HOME:SET` 可在空闲时更新目标。D8 驱动回卷，D7 释放摩擦轮。舵机预置为 180°、90°、30°，缓动速度 75°/秒。

```powershell
platformio run -d firmware/v3
platformio run -d firmware/v3 -t upload --upload-port COM4
```

烧录前隔离驱动板 VM/VCC 和舵机正极，D8/GPIO0 是启动脚。

[硬件接口](../../docs/v3-hardware-api.md) · [镜像与验证记录](../../releases/surgerybox-v3-3.1.6/)
