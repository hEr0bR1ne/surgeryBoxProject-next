# 独立舵机自动往返测试

本程序上电即输出舵机脉冲，不需要发送串口指令。请先将舵机与刹车机械连杆/负载脱开，让轴能自由转动；不要在夹紧机构上直接运行自动往返。烧录时外部舵机电源先断开，板子只由 USB 供电。

适用开发板：WEMOS D1 R1，GPIO16 对应板上 D2。舵机信号接 D2；舵机使用符合自身额定电压的外部降压电源；降压电源负极、舵机负极和 ESP8266 GND 共地。不向开发板接入24V。

上电动作：命令90° → 缓慢到80° → 停1.5秒 → 缓慢到100° → 停1.5秒 → 循环。每25ms改变1°。角度是软件请求值，不是轴位置反馈。断开舵机电源停止测试。

## PlatformIO

在 VS Code / PlatformIO 中打开本目录，选择 d1_servo_manual 环境编译上传。或者在 surgeryBoxProject-next 根目录执行：

```powershell
pio run -d hardware_tests/servo_manual -e d1_servo_manual -t upload --upload-port COM4
pio device monitor -p COM4 -b 115200
```

烧录前关闭串口监视器；如果新板端口不是COM4，请替换。该项目不会编译或上传主训练工程。

## Arduino IDE

打开 `ServoManual/ServoManual.ino`。选择 ESP8266 开发板包中的 WEMOS D1 R1 和实际串口，使用该包自带的 Servo 库。GPIO使用数字16，不能换成另一块板的D2映射。

## 观察

串口115200应循环打印80/100目标角度；这仅证明程序执行。若日志正常而轴完全不动，继续查舵机端实际供电、共地、信号接线或舵机本体，不应只扩大角度。

该程序与之前默认禁用脉冲的 servo_only 工程不同，切勿混淆：本项目会自动持续往返。
