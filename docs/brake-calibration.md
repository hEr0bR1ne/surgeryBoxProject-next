> 当前正式接口在`firmware/v3`，请读[v3-hardware-api.md](v3-hardware-api.md)。下文BR/BW/BL与calibrate_brake.py是历史主程序接口，不能用于protocol=8。

# 刹车角度标定

2026-11-03 已整合第三代用户导出的 hardware_tests/servo_tuner/servo_calibration.json，
并同步主标定文件 hardware_tests/servo_calibration.json。
板型 WEMOS D1 R1，舵机信号 D2 / GPIO16。

| 状态 | 指令角度 | 命令 |
| --- | ---: | --- |
| 释放（主程序上电默认） | 180° | BR |
| 弱阻尼 | 120° | BW |
| 锁紧 | 50° | BL |

训练事件使用同一组角度。Stop 仍锁紧，现为 50°。这些是用户记录的指令角度，不是轴角或刹车力的传感器测量。
第三代安装方向与上代相反：角度增大趋向释放。微调范围取释放与锁紧角的最小/最大值，不假定释放角更小。
BRAKE? 查询最后指令角度；BRAKE:ANGLE:175 等微调允许 50–180° 的整数，单次最大 5°，训练或回卷期间拒绝。
配套 tools/calibrate_brake.py 已同步范围。微调仅保存在RAM，重启新主固件回到180°。

本次仅整合源码，未烧录主程序、未发送舵机动作；当前板上仍是独立ServoTuner固件，其复位默认内部指令90°且输出关闭。
独立编码器固件不控制舵机。后续切换固件前仍须核实执行器供电隔离与现场状态。

历史第二代（2026-09-09）标定为释放0°、弱阻尼55°、锁紧125°，不再适用于第三代安装。
