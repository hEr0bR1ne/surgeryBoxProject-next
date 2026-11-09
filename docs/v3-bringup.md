# 当前第三代统一接口交付（2026-11-09）

当前板载已升级为firmware/v3，3.0.0 / API v1 / protocol=7；不再是下方protocol=6及更早单项固件。
接口文档：v3-hardware-api.md；验收/镜像哈希：v3-hardware-validation.md；客户端：host_sdk/surgerybox_v3.py。
四路接口与隔离验收完成，12项SDK回归、100次状态查询、旧会话/重复修改/看门狗检查通过。
最终D7/D8低、D3低、舵机脉冲关闭，端点未登记；I2C地址0x06，valid/relative_valid=1。
启动总线恢复后累计errors保持88无新增，BUS两线高、clears=2；最终串口释放。
用户在本轮检查中再次确认电机/舵机正极隔离，未恢复供电或执行有效电机驱动。
新增自动回卷及完整1秒释放的带负载机械验证留给上位机联调，不等于本轮隔离接口测试。

---
下方为第三代逐项调试历史：

# 第三代手术盒联调记录

更新：2026-11-09。本文是第三代当前现场信息；第二代交接文件中的供电、编码器标定和固件烧录状态不能直接视为第三代现状。

## 2026-11-09 D3灯已现场确认点亮，当前protocol=6

最终结果：用户修正线路后再次拉高D3，明确回复“亮了”。D3/GPIO5 HIGH→实体血迹灯亮已现场验证。
随后LIGHT:OFF及LIGHT?均回LIGHT:state=OFF,D3=0,gpio=5，串口释放；
关灯日志hardware_backups/motor_light_20261109_v6/light-off-after-confirmation.log（LOW回读已确认，实体灭灯未另行询问）。
不再等待灯模块型号/照片或电压；根因按用户排查为线路问题，未证实是3.3V门限或器件损坏。
舵机、I2C相对编码器、电机方向及灯都有用户现场验证，可开始整机接口整合；
主程序仍电机禁用且未整合新I2C接线，不能直接恢复旧主程序作为新整机固件；
新增自动回卷结束1秒释放的完整机械效果、停车惯性及上位机完整流程仍须在接口联调时验证。
以下“未亮/等待测量/留HIGH”为排查历史，以本段最终状态为准。

后续：用户实测灯模块VCC-GND=5V、IN-GND=3.3V，并自行排查确认线路问题后要求再次拉高。
已在COM4重发LIGHT:ON及LIGHT?，均回LIGHT:state=ON,D3=1,gpio=5；仅查询和灯指令，未烧录或发送电机动作。
记录hardware_backups/motor_light_20261109_v6/light-on-after-wiring-fix.log。
当前D3留HIGH、COM4释放，等待用户确认实体灯是否亮；此前“需照片/测量”的排查步骤已被本次用户线路排查取代。

用户要求最后调试D3血迹灯，灯通过后再写整机接口。再次确认隔离驱动板VM/VCC和舵机正极，
保留灯模块/编码器接线后插USB；COM4已烧录protocol=6，288000字节，Hash of data verified。
新增LIGHT:ON/OFF/LIGHT?，WEMOS D1 R1 D3=GPIO5，高触发；上电默认LOW，其他电机/释放保护保持。
GUI增加开关灯及D3状态，连接和正常断开时关灯，不依赖编码器/行程；23项既有GUI回归通过。
upload.log、idle-check.log、light-on.log见hardware_backups/motor_light_20261109_v6/。
实机无输出检查通过，电机D7/D8均LOW，active/armed/releasing/holding=0，I2C errors=0。
随后在未登记电机端点的停机状态执行LIGHT:OFF，回D3=0；LIGHT:ON及LIGHT?均回D3=1、state=ON。
**用户现场明确反馈“没有亮”。不能把GPIO回读当成实体灯通过，整机单项调试尚未全部完成。**
目前D3保持HIGH、串口已释放，电机及舵机供电仍按用户确认隔离；未恢复执行器供电或发有效驱动。
已请用户用万用表在灯模块处测VCC-GND和IN-GND，预期约5V与3.3V，等待实测值定位供电/信号链路。
此时不要打开GUI连接（会自动关灯），也不要盲目换GPIO或将软件HIGH等同于5V。

## 2026-11-09 方向1释放1000ms已实现并烧录（当前protocol=5）

用户明确指定方向1点按运行1秒，并说明逆向不会接触线卷；该时长是用户要求，不是传感器实测标定值。
正常松开回卷按钮（按钮内松手）通过FINISH:<id>结束方向2；正常到收回端内缩边界也结束回卷。
固件随后两输出LOW等50ms，再方向1/100%运行1000ms，最后两输出LOW。重复FINISH同ID不重启计时。
释放不要求编码器有进展，避免原500ms无位移保护提前中断；但编码器故障、250ms心跳丢失、
线位移达到128计数或越出原始物理端点范围会取消释放。MS随时直接停止，故障/失联/急停不自动反向。
GUI新增“点按：方向1释放1秒，然后停止”按钮；原方向1长按仅保留手动调试。
按钮内正常释放和移出/失焦明确区分，后者直接MS；当前运行中方向2按钮保持可接收松手事件。
独立释放也需当前有效端点与编码器，通过RELEASE:ARM/RELEASE与独立ID握手；连接/复位不自动释放。
原15秒回卷/500ms无进展/方向与行程保护不变，主程序电机禁用配置未改。

用户确认关闭窗口、隔离驱动板VM/VCC及舵机正极、USB接好后，COM4烧录287792字节，Hash of data verified。
MAC仍8c:aa:b5:15:e2:c4；日志hardware_backups/motor_release_20261109_v5/upload.log与idle-check.log。
镜像SHA256=A429BF0895408A87D03327E26B75CE7DD9C5177BC2E32EAB3453A2B9F864DCE6。
实机CAPS确认protocol=5、pwm=1023、release_ms=1000、release_wait_ms=50、release_delta=128；
缺端点时RELEASE/HOLD/PROBE均拒绝，FINISH拒绝、旧KEEP不启动；最终active/armed/releasing/holding/D7/D8均0。
I2C0x06读取有效、relative_valid=1、errors=0；COM4释放，未执行有效驱动或恢复电机供电。
23项无硬件GUI回归通过，新增编译期1秒无位移、50ms换向间隔、心跳/编码器故障和异常位移检查；
界面中文布局已核验，内容可滚动且红色急停固定可见。实际机械1秒释放效果待用户恢复供电后验证。
旧RAM端点已因重烧复位失效，须在驱动板断电时重新登记，回中段再接电、切②测试。
新版GUI已打开未连接（PID11048，标题“SurgeryBox · 回卷后自动释放1秒”），串口空闲。
交付hardware_tests/motor_release_toolkit_v5_20261109.zip，包含新版窗口/启动器/说明和motor-i2c-release-v5.bin；
包内SHA256、当前GUI源码及已烧录镜像一致性均已验证。旧v4包不包含1秒释放，不混用。

## 2026-11-09 用户确认100%测试成功，发现放线前需方向1

用户现场确认：方向2可回卷；不按方向1则线无法拉出，观察为摩擦轮锁住线圈。
据此记录方向2=回卷，方向1=使机构允许拉出。用户随后明确确认：方向1只需短按一次，松开后即可拉出，
无需持续驱动。后续正常回卷完成流程应为方向2回卷→停止→方向1短暂释放→停止输出。
随后用户已明确指定1000ms并按上方最新段实现；本段为该指定前的现象记录。
故障/急停/反馈丢失不应自动触发反向动作，须与正常回卷完成区分；释放可能无明显编码器位移，
不能仅凭无位移判定释放失败并延长驱动。当前停止仍只将D7/D8置LOW，没有自动执行方向1。
日志tools/encoder_logs/motor_gui_20261109_133056.txt确认protocol=4/PWM1023、signB=+1、signA=0；
末状态pos=-5348，端点6634/-19269、控制-16679~4044，active/armed/holding/D7/D8均0。
机械回卷方向由用户观察确认；signB只是编码器符号。最新空日志不能用作设备状态。
本段记录时未改固件或发送动作；当前实现与烧录状态见上方protocol=5段。

## 2026-11-09 100%长按版protocol=4已烧录（当前）

用户试用25%长按后仍反馈不转，明确要求最大运行指令；确认VM接主板5V，电机本体此前直连5V能转。
这是用户报告，实际电机额定电压/电流及驱动芯片仍未实查；100%不升压，也不能绕过驱动欠压保护。
若实际为A4950，官方VBB仍要求8~40V；此次调整不代表现有5V供电已符合其规格。
日志tools/encoder_logs/motor_gui_20261109_132200.txt证明HOLD_STARTED被接收，
约500ms后no_progress停机；该次端点8159/-6812、控制-5315~6662，中段约1725，不能据此判定驱动损坏。

已将独立测试固件duty改为1023/1023：方向1 D7持续HIGH、D8 LOW；方向2相反，停止仍00。
保留长按15秒上限、500ms无进展、250ms心跳租期、30ms编码器新鲜度，以及全部原行程/方向保护。
GUI明确标识100%和HIGH/LOW，严格核对protocol=4/CAPS pwm1023，拒绝旧25%版本；不自动启动或自动续转。
18项界面回归通过，编译期保护检查通过，主程序MOTOR_OUTPUT_ENABLED=false未改。

用户再次确认“已隔离，USB已接好”；COM4上传286048字节，MAC 8c:aa:b5:15:e2:c4，Hash验证成功。
日志hardware_backups/motor_full_20261109_v4/upload.log与idle-check.log；
镜像SHA256=EA12845CF1B12EBF6D26CB8CB579E14A5A0423A66FCF3092A7C9841467C31F09。
实机CAPS pwm=1023、protocol=4；缺行程时ARM/PROBE/HOLD拒绝，失效KEEP不能启动；
最终bounds/armed/active/holding/D7/D8均0，I2C0x06有效、relative_valid=1、errors=0、mode_pin=1。
当前驱动板及舵机正极仍按用户确认隔离，未执行有效驱动或恢复供电；COM4已释放。
用户下一步在电机断电下重登两端，回中段后恢复电机供电、切②做100%长按测试。
旧RAM参考不恢复；若再次断USB须重新登记。实际100%带负载运动与停车惯性尚未验证。
GUI已重开（PID10752，标题“SurgeryBox · 电机100%长按测试”），未连接，COM4空闲。
hardware_tests/motor_full_toolkit_v4_20261109.zip已核验包内SHA256与当前GUI、已烧录镜像一致；
内含motor-i2c-full-v4.bin。此前motor_hold_toolkit包是25%版，不能用于本次固件。

## 2026-11-09 长按运行版protocol=3已烧录（历史25%）

用户试用短点动后反馈“只有声音没有转动”，要求改成按住持续、松开停止。
日志tools/encoder_logs/motor_gui_20261109_130503.txt显示多次PROBE均no_progress，位置24911不变；
旧版在30ms无进展时退出，不是仅75ms总时长。该次用户登记端点a=33159、b=18473（反向坐标），
控制19941~31691；随后为重烧断USB，这些RAM参考失效，不导入新固件。

长按模式继续使用D7 PWM/D8 LOW或反向的官方两输入控制，PWM256/1023、500Hz不变。
按住最长15秒、500ms无进展停，取消原短点动在长按时的75ms/128计数截止；两端仍内缩10%。
未知方向从40%～60%中间起动，32计数后学习其编码器符号；已知方向可在区间内起动，朝边界须有128计数余量。
反向超过已达峰值8计数、30ms编码器过期、I2C失败/连续性丢失均停；反馈故障清除端点。
每次按压使用独立ID的HOLD:ARM/HOLD:A或B，KEEP仅维持当前活动运行，250ms过期停机，旧ID不能复活。
MS无条件停机。15秒上限不随心跳续期，不自动换向、重试或回卷；保留旧PROBE仅作原CLI兼容。

窗口tools/motor_probe_monitor.py改为鼠标长按，松开、移出按钮、失去窗口焦点、关闭/断连或红色停止均发MS。
按钮运行期间保持可释放，停止后必须重新物理按下；空格/Esc只能停止。CAPS?核对保护参数，v2窗口不兼容。
18项无硬件GUI回归通过，编译期增加边界、心跳、长按超时/无进展、峰值反向及ID解析检查。
UART遥测在命令间服务采样，运行中交替查询位置和状态；这些软件检查不能代替实测停车惯性。

用户再次回复“已隔离，USB已接好”，确认驱动板VM/VCC及舵机正极隔离。
COM4上传286048字节，MAC 8c:aa:b5:15:e2:c4，Hash of data verified，SUCCESS；
记录hardware_backups/motor_hold_20261109_v3/upload.log，镜像SHA256为
AF7958116B7D0AA54C698BF3A8EDDDEF3F437DC4B151AB8A405EC52430F976A2。
idle-check.log确认protocol=3、CAPS匹配、无端点时ARM/PROBE/HOLD拒绝、失效KEEP不启动；
最终armed/active/holding/D7/D8均0，bounds=0；ENC地址0x06，valid/relative_valid=1、errors=0、mode_pin=1。
未给执行器恢复供电，未执行有效电机输出；COM4释放。下一步用户在驱动板断电时重新登记两端并回中段，
通过已有接头恢复电机供电、确认静止后切②长按测试。若再次断USB须重登端点。
驱动型号/电源规格适配及实际长按运动、停车惯性尚待现场核实。
新版GUI已重开（PID22324，窗口标题“SurgeryBox · 第三代电机长按调试”），未连接、COM4空闲。
交付hardware_tests/motor_hold_toolkit_v3_20261109.zip，内含新版GUI/启动器/说明/motor-i2c-hold-v3.bin；
包内SHA256及与已烧录镜像/当前GUI源码的一致性已核验。旧motor_probe_toolkit包是短点动版，勿混用。

## 2026-11-09 电机测试固件v2已烧录，调试窗口可用

用户回复“已隔离，USB已接好”，确认驱动板VM/VCC供电正极与舵机正极断开。
COM4烧录hardware_tests/motor_i2c_probe：MAC 8c:aa:b5:15:e2:c4，283360字节，Hash of data verified，SUCCESS。
日志 hardware_backups/motor_probe_gui_20261109_v3/upload.log；镜像SHA256与已交付包一致。
无输出检查 idle-check.log：HELLO_PC→ACK: MOTOR_I2C_PROBE，状态protocol=2，bounds/armed/active/D7/D8均0。
缺少端点时ARM、PROBE:A和PROBE:B全部拒绝，没有进入有效点动；最终MS及状态复核输出保持低。
ENC?：地址0x06，valid=1、relative_valid=1、mode_pin=1、errors=0，raw14=284、relative_ticks=0。
串口已关闭释放；GUI PID15100仍打开但未连接，下一步用户选择COM4连接、在电机断电下重登两端。
旧0~18949等RAM参考不恢复，不自动设置机械原点，没有执行有效电机输出或恢复外设供电。

以下为同日准备阶段记录，所述“尚未烧录”已由上方实际烧录结果取代。

用户反馈电机实际可以动作，要求烧录测试固件并提供调试程序；继续遵循官方方向控制，不做旧输入组合试验。
已准备 MOTOR_I2C_PROBE protocol=2，保留D4高、D5/D6的14位I2C读取、独立行程跟踪和原固定短点动保护。
没有提高PWM、时长或位移上限：PWM256/1023、500Hz、75ms/128计数、30ms无进展、两端内缩10%、仅中间40%～60%起动。
新增端点是否已登记、编码器有效性和固定保护参数回报；未运行期间反馈过期也清除行程。
串口循环每处理一条命令即回到反馈/保护循环，避免连续查询长时间占用采样。

新增 tools/motor_probe_monitor.py，双击 tools/StartMotorProbe.cmd：连接COM4后只停机、查询；
手动断电登记两端，回到中段，恢复供电后切到点动模式；单击一次只发送一次脉冲，不自动重试。
界面显示相对计数/圈数、两端和控制边界、停机原因、断驱动时净位移，支持MS红色停止/空格/Esc。
迟到使能回执、重复点击、切换模式、复位、掉线均不能续发原点动；连接时不自动ZERO/BOUND。
10项无硬件GUI回归通过，motor_i2c_probe及encoder_i2c均编译通过，中文界面预览已检查。
调试窗口拒绝旧协议；不要打开历史hardware_tests/motor_tuner的组合测试工具。
本机GUI已打开但未连接（PID15100，窗口标题“SurgeryBox · 第三代电机调试”）；COM4未占用。
交付包hardware_tests/motor_probe_toolkit_v3_20261109.zip已校验内部SHA256，包含GUI/启动器/说明/固件。
固件283360字节，SHA256=2663046C5204904BB3B3525FAF910F0E1CED12318E1ADB132FFAE7732D3CD09D。

**此段记录时尚未烧录、未打开COM4或发送电机命令。** 之前最后确认的设备是11月5日MOTOR_I2C_PROBE旧版，
当时驱动板已恢复5V供电；不能假定旧RAM行程和现场状态延续至今。已请用户在断USB后隔离驱动板VM/VCC正极、
舵机正极，再接USB；等待当前物理隔离确认后即可执行已经授权的烧录、写入校验和无输出串口检查。
主程序MOTOR_OUTPUT_ENABLED=false未变；实际驱动芯片及供电规格仍未核实，不能把用户报告能动解释为A4950在5V符合规格。

## 2026-11-05 电机排查最新状态

用户要求继续测试电机，保留原接线与主板USB/5V供电，电机仍连接卷线机构；明确不要旧的八种输入组合试验，只按官方指引。
实际驱动芯片型号及电机额定电压尚未核实，既有商品/历史记录标称A4950。A4950官方VBB工作范围8~40V，5V不满足规格。

新增hardware_tests/motor_i2c_probe，复用14位I2C读取，保留D4高及D5/D6；主程序电机禁用开关未改。
固件只支持官方单输入PWM+另一输入LOW的两种方向接法，停止为00，不含矩阵/常转/自动回卷命令。
两端参考必须在本次上电后人工登记，诊断ZERO不改变独立跟踪计数；重启、I2C失败/超时会清参考。
向内收10%，仅从中间40~60%发起单次点动；固定25%占空比、最长75ms、净位移128计数、无进展30ms截止。
参考未完成或未ARM时拒绝输出；ARM仅一次且5秒过期。policy_checks.cpp的编译期回归覆盖保护数值条件。

COM4已烧录MOTOR_I2C_PROBE，283168字节，Hash of data verified，SUCCESS。
上传日志hardware_backups/motor_i2c_probe_20261105_v3/upload.log。
实机验证未登记两端时ARM及PROBE:A/B均拒绝、D7/D8低、I2C有效，日志idle-check.log。
这些拒绝测试没有使能电机。

用户在电机断电下确认两个允许端点：A收回端=0，B拉出端=18949，内缩控制区间1894~17055。
记录tools/encoder_logs/motor_reference_20261105_152425.json、motor_reference_20261105_152517.json。
用户随后手动移到8034（约42%），快照稳定，errors=0，armed=0、active=0、D7/D8=0。
用户明确确认已恢复驱动板原5V供电，电机静止，舵机继续断电；USB未断，参考仍有效。

已执行且仅执行一次PROBE:A：D7 PWM256/1023、500Hz，D8 LOW，属于A4950官方PWM真值表接法。
固件因no_progress自动结束，位置8034→8034，净变化0；随后MS与状态查询确认armed=0、active=0、D7/D8低。
日志tools/encoder_logs/motor_probe_20261105_153215.json。没有执行PROBE:B或旧组合遍历。
短脉冲/无进展退出不能证明电机故障；须核实实际芯片和VM供电，不在5V不符合A4950规格时继续提高PWM或延长时间。

当前板上MOTOR_I2C_PROBE，非主程序或原编码器固件；两端参考在RAM中，复位后须重建。
COM4已释放，电机驱动板按用户报告仍有5V供电但输出已关闭；后续刷机前须先隔离驱动电源。
原相对位置窗口PID3448已关闭，日志末尾收到ACK: STREAM:OFF，不再占COM4。

## 2026-11-05 相对位置读取（电机测试前）

用户明确取消实际距离/毫米换算要求，只需相对位置，不再要求尺量或建立距离系数。
今天用户再次确认执行器供电仍隔离、D4→M/Z及D5/D6接线未变、USB已接好。
原计划200mm标定未完成，用户反馈起点靠近全部行程位置；200mm试验标记incomplete，未计算或写入任何距离系数。
随后50mm计划也随用户要求取消，不再以标定流程阻塞相对位置读取。

板上继续保持ENCODER_I2C_14BIT固件，未重烧。
新增tools/encoder_relative_monitor.py及tools/StartEncoderRelative.cmd，使用PySide6 QtSerialPort，
每圈16384计数直接显示相对计数、相对角度和圈数，跨圈继续累计；没有毫米字段。
连接先识别固件，再通过ZERO设置诊断相对零，绝不建立机械原点或改变电机限位。
采样中断、复位或relative_valid=0会隐藏失效位置，要求用户重新点击归零；不会自动恢复旧位置。

曾打开“SurgeryBox · 编码器相对位置”窗口，PID 3448，电机测试前已关闭并收到停流回执。
日志tools/encoder_logs/relative_20261105_150631.txt确认握手、ZERO回执、STREAM:ON通过；
raw14=4286，单圈角度94.1748°，relative_ticks=0，valid=1，relative_valid=1，errors=0，mode_pin=1。
当前相对零是用户要求下的诊断起点，不是物理行程原点。主程序I2C整合仍未完成，电机/舵机保持隔离。
后续若需要别的工具打开COM4，先关闭此实时窗口；窗口关闭尝试STREAM:OFF并释放串口。

## 用户报告的接线与观察

- 主板仅由本机电脑USB供电，不再使用外部24V。
- 电机驱动板、舵机正极、血迹灯模块电源均从主板5V取电；驱动板VM/VCC具体接点仍待核实。
- 血迹灯模块已处理好，高电平触发，信号接D3（配置板型WEMOS D1 R1的GPIO5）。
- 编码器更换为MT6701模块：VDD接3.3V，M接GND。M与芯片MODE的对应及板上跳线尚未实测核实。
- 用户观察到：插USB后电机短暂转动，随后停止。不能据此判定原因或认定当前板载固件。

## 本机检查

- 枚举到USB-SERIAL CH340，COM4，VID:PID=1A86:7523；COM10/COM11为蓝牙串口。
- 源码include/config.h仍为MOTOR_OUTPUT_ENABLED=false；不能以源码推定实物固件。
- 本轮尚未打开COM4、烧录或发送执行器指令。

## COM4只读核验（2026-11-03）

用户已确认断电隔离驱动板、舵机正极并插回USB，随后读取串口。
握手ACK: HELLO_PC。TRAVEL?返回：home=0,pos=0,direction=unknown,active=0,
motor_enabled=1,rewind_enabled=0,armed=0,bench=0,matrix=1,reason=boot_unreferenced。
板载固件与本地motor_enabled=false源码不同，且返回额外保护字段，不能将本地源码视为板载固件来源。
PINS?返回D7=0,D8=0,D3=0；ENC?返回raw=0,ticks=0,A=0,B=1,edgeA=0,edgeB=2,seq=0。
BRAKE?为ANGLE:0（指令值），LIGHT?为OFF（指令值），均不是实际动作或光学验证。
串口已关闭；未烧录、未发送执行器动作命令。
待用户准备手动正反转后采样，不能将静止快照当作编码器工作通过。

## 舵机调试固件烧录完成（2026-11-03）

用户暂停编码器采样，要求先调松刹车，已打开ServoTuner GUI（PID 6556），随后明确要求烧录配套固件。
沿用刚才用户确认的驱动板、舵机正极隔离状态，仅USB供主板。

- flash_id检测：ESP8266EX，MAC 8c:aa:b5:15:e2:c4，Flash 4MB。MAC与旧第二代记录不同，以本次实测为准。
- 覆盖前read_flash读取0到0x400000，共4194304字节，保存hardware_backups/before_servo_tuner_20261103_v3/flash-4mb.bin。
- 原Flash SHA256：572F75E6E271DA44BF898A351AC53F7AFD33493F9F2A5B9DDC54233D88A74697。
- hardware_tests/servo_tuner环境d1_servo_tuner编译通过，COM4以115200上传275856字节，Hash of data verified，SUCCESS。
- 实际写入镜像另存同备份目录servo-tuner-written.bin；SHA256SUMS.txt及上传/回读日志保留。
- HELLO_TUNER返回TUNER:1及STATE:0,90,90；STATUS、OFF也返回STATE:0,90,90。
- 未发送SET或恢复外设供电。状态中0代表控制脉冲关闭；90是内部指令角，不是轴实际角度。
- 校验后COM4已关闭释放，GUI仍打开、未连接，用户可选择COM4后连接。

当前板上是独立舵机调试程序，不再运行编码器、血迹灯或主程序的电机保护。
电机须继续隔离供电；舵机正极恢复连接须在USB拔掉、整机断电时进行。
该固件首次SET会先输出内部90°指令再渐变至目标，并非从实际轴位置开始；用户应先核实刹车机构可允许该位置。
调好后导出释放/弱阻尼/锁紧角度JSON，再讨论恢复原Flash或整合第三代主程序。

## 第三代舵机标定已整合源码（2026-11-03）

用户提交hardware_tests/servo_tuner/servo_calibration.json（导出时间17:58:58）：
release=180°、weak=120°、lock=50°，WEMOS D1 R1，GPIO16。
已同步hardware_tests/servo_calibration.json、src/servo_brake.cpp、tools/calibrate_brake.py与docs/brake-calibration.md。
微调范围改为50~180°，由释放/锁紧角的最小最大值判断，保留单次最多5°及训练/回卷期间拒绝的限制。
主程序env:d1本机编译通过；未烧录、未打开串口、未发送动作。板上仍为独立ServoTuner固件。
用户导出的数值是指令角度，不是力或轴角的传感器测量；旧0°/55°/125°仅保留作历史。

## 编码器独立固件与首轮采样（2026-11-03）

用户确认已将舵机释放180°并停止脉冲，断电隔离舵机正极与电机驱动板正极后插回USB。
COM4烧录hardware_tests/encoder_only，273648字节，Hash of data verified，SUCCESS。
上传日志在hardware_backups/encoder_bringup_20261103_v3/upload.log。
当前板上已切换为ENCODER_ONLY，不再是ServoTuner；HELLO_PC返回ACK: ENCODER_ONLY。
未发送舵机/电机指令，未重设物理原点，未修改MT6701配置。

- 静止5秒：26个快照均raw=0,ticks=0,A=1,B=0,edgeA=0,edgeB=0。
  日志tools/encoder_logs/20261103_180641_063930.txt。
- 用户回复开始后采样30秒：首帧raw=0,ticks=0,A=1,B=0,edgeA=4,edgeB=2；
  随后B边沿增至3，ticks=1；A边沿增至5，ticks=2；余下采样保持ticks=2。
  日志tools/encoder_logs/20261103_180745_456795.txt。
- 采样内A/B各新增1边沿，显示两相有反馈，但没有捕获反向计数；运动幅度与磁铁跟随情况待用户说明。
  不能据此推定故障、每圈分辨率或正反向已验证。采样前已有边沿，不能把采样窗口等同于用户全部运动。

采样已停止、COM4已关闭。接下来确认实际转动幅度，再决定是否按整圈测计数或核查磁铁安装。

## 延长采样确认正反转（2026-11-03）

用户说明首轮实际正反转了数圈，怀疑采集启动较慢；随后改为先启动90秒采集，
确认收到ACK: ENCODER_ONLY和ACK: STREAM:ON后，才提示用户正转3圈、停2秒、反转3圈并停住。
用户回复已完成。

日志tools/encoder_logs/20261103_181038_600948.txt，共451帧，摘要在同名.summary.json。
计数：2→-11→2，负向13步、正向13步，回到起始计数；edgeA增加14、edgeB增加12。
动作发生18:11:25~18:11:47，采样覆盖18:10:39~18:12:09；此前与停住后计数均稳定。
本次慢速测试确认A/B都有反馈、方向能够反转、回转后计数回到起点；不等于高速或精度验证。

转约3圈只有约13计数，推测当前AB输出接近1PPR（四倍频约4计数/圈），仍须核实芯片实际配置。
原厂Rev1.8订货型号表列STD默认AB=1PPR；不能把最高1024PPR当作模块当前配置。
本次没有修改MT6701参数、没有写EEPROM、没有修改距离系数或物理行程限位。
采集结束、COM4已释放，执行器仍保持用户确认的供电隔离。

## 切换14位I2C，D4分线驱动M/Z（2026-11-03）

用户要求保留VDD原3.3V线，仅用一转二把D4接M及Z；已确认断电改线完成，执行器供电继续隔离。
已实查本机board=d1的pins_arduino.h：D4=GPIO4（不是D1 mini上的GPIO2）。
连接为VDD→3.3V、G→GND、A/SDA→D5/GPIO14、B/SCL→D6/GPIO12、M+Z→D4/GPIO4。
M/Z原接地/其他连接已要求拆除；D4仅驱动模式输入，不给编码器VDD供电。

新增hardware_tests/encoder_i2c独立固件：启动将D4设HIGH，显式Wire.begin(D5,D6)、100kHz，
0x03先于0x04单字节读取14位角度，每10ms采样；不写配置或EEPROM。
D7/D8/D3设LOW，不输出舵机脉冲；复位/烧录期仍须保持执行器供电隔离。
诊断相对计数处理跨圈；通信失败或采样间隔超过100ms会锁存relative_valid=0，须明确ZERO才重新建立诊断相对零。
任何诊断相对零均不是机械原点，不恢复物理行程参考。

- d1_encoder_i2c编译通过；COM4上传277616字节，Hash of data verified，SUCCESS。
  上传记录hardware_backups/encoder_i2c_20261103_v3/upload.log。
- HELLO_PC回ACK: ENCODER_I2C_14BIT；地址0x06，D4读回mode_pin=1。
- 首轮5秒51帧全部有效，raw14=4620、angle=101.5137°静止稳定，errors=0。
  日志tools/encoder_logs/i2c_20261103_194912_489261.txt。
- 先启动采集再提示用户小幅转动、正转一圈并反转；用户报告完成。
  日志tools/encoder_logs/i2c_20261103_194956_399184.txt，1030帧全部valid=1、relative_valid=1、errors=0。
  正向累计16238、反向累计16607计数；relative_ticks范围-371~16194，最后-369，未精确回到起点。
  原始角度跨零两次且连续位移正确衔接；末30帧raw14均4251。
  这确认了本次慢速高分辨率读数与跨圈逻辑，不是距离精度或整圈计数精密标定。
- 采集结束首次STREAM:OFF回执未收到，但角度流仍连续且错误数0；随后补发换行及重试收到ACK: STREAM:OFF，
  再核验握手与STATUS通过，COM4释放。尚未判定首次回执丢失原因。
  已给tools/check_encoder_i2c.py加幂等串口命令重试与失败保留采样摘要，未改芯片参数。
- 修正后2秒复核21帧全部有效，raw14=4226、angle=92.8564°保持稳定，errors=0；
  停流回执通过，stream_stop_confirmed=true，COM4关闭。
  日志tools/encoder_logs/i2c_20261103_195429_413774.txt。

当前板上是ENCODER_I2C_14BIT（D4持续高），非原A/B测试程序、ServoTuner或主程序。
主程序仍使用A/B解码，尚未整合D4模式控制与I2C读取；不能直接恢复旧主程序并当作兼容当前接线。
距离换算系数、机械原点和新行程限位尚未标定，电机仍不得按旧行程计数运行。

## 当前待完成

已收到隔离确认并完成上述只读核验；后续任何供电恢复须重新确认现场条件。
串口打开/下载可能引起复位，不能忽略已报告的上电短暂动作。

先做握手、只读状态和MT6701手动计数，再逐项测试灯、舵机、电机。新编码器的距离系数与行程尚未标定。
独立编码器固件不初始化执行器引脚，不能用其保证驱动板停机。

供电适配尚未完成：若驱动板实际为A4950，其负载电源VBB额定工作范围为8~40V，VM仅5V不满足规格。
模块型号仍须核实，不能仅凭排针认定A4950；电机短暂动作也不能证明5V供电满足要求。
电机、舵机从主板USB/5V路径取电是否可行，还需按实际负载电压、电流及主板供电路径核实。

参考：https://www.allegromicro.com/-/media/files/datasheets/a4950-datasheet.pdf （第3页）
