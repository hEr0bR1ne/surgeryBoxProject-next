# 电机常转独立程序

只用于电机与卷线负载机械脱离后的台架测试。此程序按用户要求去掉编码器、限位、定时停止与上位机控制。不要带导管/卷线负载运行；断开外部24V才能停止电机。旧测试窗口的停止按钮对本程序无效。

板型 WEMOS D1 R1：D7/GPIO13 → AIN1，D8/GPIO0 → AIN2，共地。默认上电后 D7 恒高、D8 恒低，固定一个方向、100%输出，不使用PWM。具体机械旋转方向取决于电机线序。需要反向时，在源码中把 REVERSE_DIRECTION 改为 true 再烧录。

原主程序保留在仓库 src/include 中；烧录前另已备份源代码ZIP和旧firmware.bin/elf，位于 hardware_backups/before_motor_continuous_日期时间/，附SHA256校验清单。备份为先前烧录的本地编译产物，不是板载Flash全量读取。

## 手动烧录

1. 断开整套24V、保留USB，确保电机已脱离卷线负载。关闭其他串口工具。
2. Arduino IDE：打开 MotorContinuous/MotorContinuous.ino，选择 WEMOS D1 R1 / ESP8266，端口COM4，然后上传。
3. 或在仓库根目录执行：

```powershell
python -m platformio run -d hardware_tests/motor_continuous -t upload --upload-port COM4
```

4. 上传完成后，程序输出已经是常转状态；恢复24V时电机应立即连续转动。停止请断开24V。

## 恢复旧程序

保持24V断开，用esptool把备份firmware.bin写入地址0，或重新编译上传仓库根目录的原主程序。恢复后重新确认机械零点；之前的RAM物理位置和PWM设置不保留。
