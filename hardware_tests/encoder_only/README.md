# 编码器独立测试（WEMOS D1 R1）

直接编译主程序编码器实现，只初始化编码器和串口，不初始化电机、舵机或灯。

| 编码器线 | D1 R1 引脚 |
| --- | --- |
| A 相 | D5 / GPIO14 |
| B 相 | D6 / GPIO12 |
| GND | GND，与外部电源共地 |

信号应为 3.3V 兼容电平，编码器电源按模块规格连接，不能将 24V 信号直接接入 GPIO。
关闭占用 COM4 的舵机工具，在仓库根目录执行：

```powershell
python -m platformio run -d hardware_tests/encoder_only -t upload --upload-port COM4
python tools/check_encoder.py --port COM4 --seconds 20 --zero
```

工具先验证固件身份，读数保存到 tools/encoder_logs。也可使用 115200 波特率串口监视器，换行发送 ZERO、ENC?、STREAM:ON、STREAM:OFF。

1. 静止时 ticks、edgeA、edgeB 应稳定。
2. 单向缓慢转动：两相 edge 都增长，ticks 持续向同一方向变化。
3. 反转：ticks 变化方向反转，edge 仍增长。
4. 只有一相 edge 增长，检查另一相信号；都不增长，检查供电、共地、接线。
5. 清零后单向拉出已知长度，例如 100 mm，记录 ticks。米/计数 = 长度（m）/abs(ticks)。提供实测长度和 ticks 后再更新主程序系数。

主程序历史系数 0.0000507 m/计数尚未重新标定，本测试只显示计数。若机械刹车阻碍移动，先通过舵机工具释放到 0° 再测试。
