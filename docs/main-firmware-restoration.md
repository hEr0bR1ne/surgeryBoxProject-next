# 保护主程序恢复记录

时间：2026-09-09 22:53（Asia/Shanghai）。用户授权恢复主程序，并确认整套24V断开、USB保留、COM4释放；随后重插USB。发现残留Arduino串口监视器后，仅结束该监视器进程，保留编辑器，烧录成功。

- 源码提交：`4371a515285b13515ce1f99e9d374afbe6112ffb`
- 工程：仓库根目录，PlatformIO `env:d1`，WEMOS D1 R1
- 设备：COM4，ESP8266EX，MAC `e8:db:84:c2:d2:8c`
- 固件：328144字节；SHA256 `2ba47082ab17aeb61ff525247a4f475564dd4bf14d9e6841d2bec1f90e180a61`
- 上传结果：`Hash of data verified.` / `[SUCCESS]`，随后复位启动。
- 旧保护主程序源码和构建产物备份仍保留于本机 `hardware_backups/before_motor_continuous_20260909_221550/`，未发布到GitHub；独立常转测试源码保留于 `hardware_tests/motor_continuous/`。

只读串口核对（115200，无动作指令）：

```text
HELLO_PC -> ACK: HELLO_PC
TRAVEL? -> TRAVEL:home=0,pos=0,low=1745,high=33146,stop=1945,direction=unknown,active=0,pwm=300,reason=boot_unreferenced
BRAKE? -> BRAKE:ANGLE:0
LIGHT? -> LIGHT:OFF
ENC? -> ENC:raw=0,ticks=0,dist_m=0.0000,A=1,B=1,edgeA=0,edgeB=0,seq=0
PINS? -> PINS:D0=0,D1=0,D2=0,D3=0,D4=1,D5=1,D6=1,D7=0,D8=0
```

串口已关闭释放。未发送HOME、Start、PROBE或Winding；`pos=0`是未建立参考时的计数，不代表机械原点。外部24V保持断开，以上是软件读回，不是万用表测量或外设动作验证。电机异常、方向、制动惯性和完整上位机联调仍未验证。接手时先读 [AI-HANDOFF.md](AI-HANDOFF.md)。
