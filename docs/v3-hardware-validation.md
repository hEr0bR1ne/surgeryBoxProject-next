# 第三代硬件接口验收与当前状态

## 3.1.0用户现场测试与发布（优先于下方历史记录）

用户已确认新版效果满意并要求发布GitHub交接。新版日志operator-test.log确认多次75°/秒缓动刹车、灯开关及回卷任务token1715103486完成，reason=release_complete、encoder errors0、dropped_frames0。
完成时pos86、home0，随后末次查询pos85：存在约1.89°编码器角位移的超零，不能说绝对无惯性超调。
首次20:42:36 BRAKE:WEAK仍发生一次COM4 GetOverlappedResult错误5，重连boot相同，后续动作成功；首次启用通信问题尚未完全消除。
证据与镜像统一在releases/surgerybox-v3-3.1.0/，旧candidate目录与此前协议属于历史。


## 3.1.0已烧录：自动上电零点 / protocol=8

用户明确取消所有软件停止死区、取消人工两端标定与拉出距离限制，采用上电位置作收回零点；舵机再加快50%。
源码与SDK/GUI已适配protocol=8：上电首个有效样本自动home=0，显示ZERO不改home；到零即关方向2、50ms后方向1释放1秒。
跟踪故障使home失效，不会在任意位置重新捕获。拉出再远不因长度拒绝回卷，保留120秒连续运行/500ms无进展/编码器/心跳/错向停机。
用户重新确认“已隔离，USB已接好，可以烧录”后，COM4已写入290464字节，Hash of data verified；boot=15e2c4-dd5d290c。25次只读状态检查通过：home=0/home_valid=1、extension_limit=0、deadzone_ticks=0、speed_deg_s=75，编码器errors=0，电机/舵机脉冲/灯输出关闭，丢帧0。没有发送启动执行器的指令，结束SAFE后释放COM4。
构建与策略静态检查、13项SDK测试和13项GUI测试通过。镜像SHA256为96112899e6bcc152d2ef908ca1a5b5bc54636bd88b687284ec51b12d625c8af9。证据在releases/surgerybox-v3-3.1.0-candidate/的upload.log、readonly-wire.log、readonly-check.json。
用户报告3.0.1缓动后刹车不再断连。日志hardware_20261109_202211_074432.txt显示后续多次WEAK/LOCK/RELEASE与回卷token1950616193成功，最后reason=release_complete，encoder errors0。
同时20:22:14首次BRAKE:RELEASE发生超时、WriteFile error5及端口短暂不存在，重连boot未变。不能将后续成功描述为首次附加/USB故障已经完全修复。


## 3.0.1已烧录（执行器隔离，只读验证通过）

用户明确“死区”是靠近收回端提前停车、剩余段无法回卷。源码已改为停止余量1%（最少32计数），近目标启动容差8计数；原始物理端点/失联/编码器/超时保护保留。
舵机目标按1°/20ms非阻塞推进，回卷须在最后一步后再等待500ms；停止脉冲取消过渡。首次启用实际位置未知，不能保证首次动作缓慢。
用户随后确认“已隔离，USB已接好，可以烧录”，故已在COM4写入296128字节，Hash of data verified，MAC 8c:aa:b5:15:e2:c4。板载现为3.0.1，boot=15e2c4-d57f700a。
25次只读STATUS检查通过：I2C0x06有效、错误0、丢帧0，电机active/armed/holding/releasing/D7/D8及JOB.preparing均0、舵机脉冲关闭、灯关闭。新RAM端点未登记。
未发送启动电机、舵机或灯的指令；退出仅发送SAFE。错误5是否因缓动改善仍未验证。旧交接包未覆盖。
验证：PlatformIO构建成功，策略静态检查包含缓动期间禁止提前启动、停止脉冲取消缓动、延迟不突跳和计时回绕；13项GUI测试及12项SDK测试通过。
已烧录镜像位于`releases/surgerybox-v3-3.0.1-candidate/firmware.bin`；该目录仍保留candidate名称，因为尚未完成带电动作验收。
SHA256：E6A8890383A408209FAF8F958B83CB16BD28643220C5211C21821C6D6F7D827A。
证据同目录upload.log、readonly-wire.log、readonly-check.json。

## 后续发现的未解决故障（2026-11-09）

用户在全功能测试端实际操作后报告每次舵机指令需要重连。日志test_logs/hardware_20261109_195338_911876.txt
显示19:56～19:58多次BRAKE:RELEASE/WEAK/LOCK后出现Windows GetOverlappedResult/WriteFile的PermissionError(13, error 5)，
客户端据此将串口标记fatal并关闭，必须人工重连。多次重连的boot均为15e2c4-41011c69，没有MCU重启证据。
不是舵机协议设计要求重连；也不能仅凭错误断定电源不足、MCU复位或某器件损坏。
下方隔离接口测试通过记录仍有效，但**不能据此宣称实际舵机动作后的通信稳定性已通过**。
已提出完全断开舵机三根线进行空载对照，用户选择“暂不改线，先保留现场”。因此本轮不再发动作、开串口或重烧；
根因仍待验证，不能通过自动重连重放舵机/电机指令来掩盖故障。

日期：2026-11-09。设备：WEMOS D1 R1，COM4，ESP8266EX MAC 8c:aa:b5:15:e2:c4。
当前板载为`firmware/v3`的统一硬件固件3.0.0 / API v1 / protocol=7，不再是单项调试程序。
写入295856字节，esptool报告Hash of data verified。
镜像SHA256：`D0856D105EC0085335E4EBA81E0FA1E0111216899E04E32D658E5BC409759A3F`。

## 通过的检查

| 层次 | 检查及结果 |
|---|---|
| 固件构建 | PlatformIO espressif8266 4.2.1、board=d1，编译和写入校验通过 |
| 编译期策略 | 跨零、两个编码器坐标方向、内缩限位、失反馈、反向、无进展、租期、1秒释放、异常释放位移等静态断言通过 |
| Python客户端 | 12项回归通过：请求相关性、主动事件隔离、分段串口重组、重启失效、心跳独立、超时不重试、故障不伪报成功、急停与关闭 |
| 实机完整接口 | HELLO/INFO/STATUS、三档刹车指令、5°微调及超步拒绝、灯ON/OFF、编码器查询/归零/主动上报、缺行程拒绝回卷和释放、SAFE通过 |
| 连续查询 | 连续100次完整STATUS通过，dropped_frames=0，执行器输出保持关闭 |
| 原始协议保护 | 旧boot修改拒绝、重复危险修改ID拒绝、超长输入恢复、旧boot仍可SAFE通过 |
| 实机主机看门狗 | 停止PING约1.25秒后，舵机脉冲与灯自动关闭，motor.reason=host_watchdog，电机保持停机 |

实机验收时用户再次明确确认电机驱动VM/VCC及舵机正极断开，其他串口窗口已关闭。
舵机接口检查验证的是脉冲指令/状态，未让该轮测试的断电舵机实际运动。
灯本体高电平点亮、舵机50°/120°/180°、编码器正反向及电机方向的机械单项由此前现场测试确认。

## 最终读取

- `I2CENC`：地址0x06，valid=1、relative_valid=1，原始值529，诊断相对计数0。
- `BUS`：MODE/SDA/SCL均高，addr=6，clears=2。
- `MOTORPROBE`：bounds=0、armed/active/holding/releasing/D7/D8均0，reason=safe_off。
- `JOB`：preparing=0，kind=idle。
- `BRAKE`：enabled=0、angle=180（仅内部指令值）。
- `LIGHT`：OFF、D3=0。
- `SYSTEM`：dropped_frames=0，free_heap=42920；COM4已释放。

启动阶段曾遇到总线低电平未释放，累计errors=88；增加规范总线恢复后已读取正常，后续100次状态查询及完整验收期间该计数保持88、未新增。
不能把累计非零计数写成“零错误”，也不能忽略valid而仅凭旧样本显示位置。
连续指令时发现的回执问题已通过有界非阻塞发送队列、紧急通知无回执及客户端跨超时分段重组处理；最终验收通过。

## 尚需上位机联调验收

本轮没有登记虚假行程，也没有运行带负载的完整自动回卷，因此：

- 仍须人工标定本次上电的两端；不能沿用历史标定或把相对0当机械原点。
- 实际“舵机释放→自动回卷→方向1释放1秒”完整机械流程、停止惯性余量需现场验证。
- 未提供毫米/米系数，SDK只有计数/角度/圈数。
- 现有USB/主板5V供电由用户现场使用；实际驱动芯片及电机额定电流尚未实查，不把功能试验当成供电额定确认。

这些限制已在接口合同中列明；上位机可以先开发查询、显示、灯和刹车功能，回卷UI必须处理行程未登记及故障回执。

交接包`verification/`保留upload.log、acceptance.log、query-stress.log、protocol-guards.json、unit-tests.log和final-state.json。
工作区原始记录位于`hardware_backups/v3_hardware_api_20261109/`。
