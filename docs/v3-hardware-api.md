# 第三代MCU硬件接口：上电零点版

当前板载3.1.0，API v1 / protocol=8。用户确认执行器供电隔离后已烧录COM4，290464字节写入校验通过。25次只读状态验证通过，随后用户完成舵机/灯/回卷测试；首次启用舵机仍有一次error5，详见交接记录。
固件入口`firmware/v3`，SDK入口`host_sdk/surgerybox_v3.py`，测试端`tools/StartHardwareTest.cmd`。
新版SDK只接受protocol=8，避免把旧手动端点模式误当成上电零点模式。旧交接ZIP仍是旧版本。

## 当前行为

- 上电后的第一个有效MT6701读数自动作为收回零点；不会自动运动找端点。
- 拉出方向在这台已验证机构上为编码器计数减小，方向2回卷时计数增加。固定rewind_sign=1，不进行输入组合试验或自动试方向。
- 无拉出距离上限、无手动登记两端、无最小行程要求、无百分比余量、无提前停车死区。
- 当前位置低于上电零点时，回卷一直到采样达到或越过零点，立即关断方向2，再停50ms、方向1释放1秒、关闭。
- 已在零点或其收回侧时，不再驱动方向2，只执行摩擦轮释放。不会为了寻找零点而反复正反运动。
- 舵机指令按每20ms交替1°/2°推进，平均75°/秒，比3.0.1的50°/秒快50%；60°约0.8秒。完成最后一步后等500ms再启动电机。
- 编码器累计跨圈，不限制为单圈。显示ZERO只改变relative_ticks，不移动上电零点或physical pos。
- 编码器中断/失去连续性时停止电机并使本次零点失效；恢复通信、重新连接或ZERO不能暗中重设零点，须重新上电。

上电零点是操作者选择的当前位置，不是测得的机械全收回端。希望卷回哪里，就在那个位置上电；重连电脑端不会改零点。
到零关断是软件指令行为，10ms采样间隔及机械惯性仍可能产生少量超调，不能声称物理位置绝不越过零点。没有新增隐藏余量。
首次启用舵机脉冲的实际位置未知，缓动不能保证首次附加时无跳动。

## 接线

WEMOS D1 R1（不是D1 mini），USB供主板；用户当前执行器取板载5V、编码器3.3V，共地。

| 板脚 | 信号 |
|---|---|
| D2 / GPIO16 | 舵机刹车 |
| D3 / GPIO5 | 血迹灯，高有效 |
| D4 / GPIO4 | 编码器M+Z模式选择，高电平；不供VDD |
| D5 / GPIO14 | 编码器A/SDA |
| D6 / GPIO12 | 编码器B/SCL |
| D7 / GPIO13 | 驱动AIN1，方向1释放 |
| D8 / GPIO0 | 驱动AIN2，方向2回卷 |

烧录会复位，D8属于启动配置脚；烧录前隔离驱动VM/VCC与舵机正极。上电无电机、舵机脉冲或灯输出。
实际驱动芯片仍未核实，不根据旧卖家型号推断5V符合规格。

## Python接入

Python3.10+，`pip install -r host_sdk/requirements.txt`。串口115200、8N1，无流控，DTR/RTS保持False，只有一个端口所有者。

```python
from surgerybox_v3 import SurgeryBox

box = SurgeryBox('COM4')       # 只握手；零点由MCU在上电时自动采集
print(box.identity)
print(box.status())
print(box.position())          # 相对计数/角度/圈数，没有毫米
# 按操作者按钮触发，不作为自动启动序列：
# box.set_brake('weak')        # 缓动到120°
# box.set_light(True)
# box.wind()                  # 返回任务token，无需登记两端
# box.wait_motor()            # 正常完成须reason=release_complete
box.close()                   # SAFE关闭输出，不自动反向
```

| SDK调用 | 行为 |
|---|---|
| status()/info()/position() | 查询状态/能力/相对位置 |
| set_brake('release'/'weak'/'lock'/'off') | 目标180°/120°/50°/取消缓动并停脉冲；off也停止电机 |
| set_brake_angle(n) | 50～180°，相对当前指令每次最多5°微调 |
| set_light(True/False) | D3高/低；不是光学反馈 |
| zero() | 仅重设显示相对零，不能改上电零点 |
| stream(True/False)/next_event() | 10Hz编码器上报，事件队列128条 |
| wind()/release() | 启动回零任务/仅摩擦轮释放1秒，返回token |
| finish() | 正常提前结束并释放，不代表已经回到零点 |
| wait_motor(timeout=130) | 等待成功；故障或超时抛异常 |
| stop() | 急停电机，不反向；保留舵机与灯 |
| safe_off()/close() | 关闭电机、灯、舵机脉冲和位置流，不反向 |

mark_endpoint()/clear_endpoints()已移除功能，调用会在本地抛ValueError，不发送串口命令。上位机不应再提供端点标定流程。
BRAKE回执只表示目标接受；moving=0且settled=1表示指令过渡及固定等待完成，仍非实测角度。
持续保留SDK对象，后台线程维持心跳；不要每点按钮都开关端口。主机失焦/退出可调用safe_off()。

## 回卷与故障停车

```text
WIND -> 有效编码器与本次上电零点
     -> 舵机缓动至180°，最后一步后500ms
     -> 若已回到/越过零点，跳过方向2
     -> 否则方向2满占空比，直到采样达到/越过零点
     -> 两输出LOW 50ms -> 方向1满占空比1000ms -> LOW
```

无拉出端限制。连续回卷硬上限从15秒改为120秒，避免稍长的正常拉出被旧超时中断；到时停止，可人工重新发任务，不自动续跑。
500ms没有4计数净进展、错误方向退回峰值8计数、编码器年龄超过30ms、丢失token KEEP达250ms，均停机。
主机1000ms无有效联系则SAFE；心跳与KEEP不能延长120秒回卷上限或1秒释放。
释放阶段无需线位移，但累计线移动达到128计数会停机；无拉出端/物理区间检查。
故障、急停、SAFE、失联不自动反向。重复FINISH同token不会重复或延长释放。

## 串口协议

请求`@<positive id> <boot> <command>\n`，响应`@id boot PAYLOAD`多行，以END:OK或END:ERROR结束。
HELLO使用boot='-'；非安全修改命令须boot匹配，最近16个危险修改ID禁止重复。输入上限160字符，过长帧丢弃后恢复下一行。
异步事件`! boot PAYLOAD`。通知`~boot PING`、`~boot KEEP:token`不回包；裸MS/SAFE为立即停止通知，不回包，随后用带编号查询确认。
只读或安全关闭可在旧boot上发送，危险命令不得重试。断线/重启客户端报错，不自动重连或重放。

| 命令 | 返回 |
|---|---|
| HELLO | product=SurgeryBoxV3,api=1,firmware=3.1.0,protocol=8,boot |
| STATUS? | I2CENC、MOTORPROBE、JOB、BRAKE、LIGHT、SYSTEM |
| INFO?/CAPS?/BUS? | 接线单位/电机能力/模式与I2C总线 |
| ENC?/MOTOR?/TRAVEL?/BRAKE?/LIGHT? | 对应状态 |
| BRAKE:RELEASE/WEAK/LOCK/OFF | 舵机目标及当前指令 |
| BRAKE:ANGLE:n / LIGHT:ON/OFF | 微调/灯 |
| ZERO / STREAM:ON/OFF | 显示归零/10Hz上报 |
| MOTOR:WIND:token / MOTOR:RELEASE:token | ACCEPTED、MOTORPROBE、JOB |
| MOTOR:FINISH:token / KEEP:token | 正常结束/维持租期 |
| STOP / MS / SAFE | 立即停止/全部关闭 |

旧BOUND:RETRACT、BOUND:EXTEND、BOUNDS:CLEAR明确拒绝，不会改变零点。
MOTORPROBE主要字段：pos、home、home_valid、home_captured、home_source=power_on、rewind_sign=1、extension_limit=0、deadzone_ticks=0、active、holding、releasing、id、reason、D7、D8、encoder_ok。
JOB：preparing、token、kind。BRAKE：enabled、angle、target、moving、settled、step_ms=20、speed_deg_s=75、measured=0。
I2CENC：addr、valid、raw14、angle_deg、relative_valid、relative_ticks、age_ms、samples、errors、mode_pin。
SYSTEM：uptime_ms、free_heap、dropped_frames、host_timeout_ms=1000、motor_lease_ms=250。
主机不能用旧bounds/a/b/low/high判断可回卷，必须用home_valid和实时编码器有效性。
