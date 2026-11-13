# SurgeryBox V3：当前开发入口

当前已烧录固件为3.1.6 / API v1 / protocol=8，基于3.1.0。入口`firmware/v3`，SDK是`host_sdk/surgerybox_v3.py`，测试端是`tools/v3_test_client.py`。
先读`docs/AI-HANDOFF.md`和`docs/v3-hardware-api.md`。仓库根目录的`src/`、`include/`、`platformio.ini`是历史第二代入口，不适用于当前接线；不得误烧录。

## 当前用户要求

- MCU上电第一个有效编码器样本作为收回零点；不需人工两端标定，不设拉出上限、最小行程或提前停车死区。
- 当前绕线方向下拉出计数增加，回卷计数递减。D8驱动回卷，到达当前回卷零点后停50ms，再由D7释放1秒。3.1.6带载实测已确认这一顺序。禁止旧输入排列组合试验。
- 测试端「设为回卷零点」用HOME:SET将当前位置设为回卷目标，并同步清零显示计数。只在电机空闲且编码器跟踪有效时接受，重启后重新取上电位置。SDK的ZERO只清显示计数。跟踪失效时停机并使home失效。
- 舵机目标180°/90°/30°，指令缓动75°/秒，完成后500ms才能启动回卷。角度为指令值。
- 保留编码器失效、250ms运动租期、1000ms主机看门狗、500ms无净进展、错向与120秒连续回卷停止。故障/急停不自动反向。
- 编码器仅相对计数、角度与圈数；未标定毫米，不导入第二代旧距离系数或端点。

## 操作与验证

- 发布/文档任务不需要开串口或发动作。现场状态随用户操作改变，不从旧日志推断当前输出/供电。
- 烧录或复位前确认驱动VM/VCC与舵机正极隔离：D8/GPIO0是启动脚，复位期间可能误动。只允许一个程序占串口，不自动重连重放动作。
- 当前用户明确同意以上上电零点和无死区行为，历史记录中的双端标定/内缩余量要求已被替代。
- 固件检查：`platformio run -d firmware/v3`（包括policy_checks.cpp静态检查）。
- SDK检查：`python -m unittest discover -s host_sdk/tests -p test_client.py`。
- GUI检查：`python -m unittest discover -s tools -p test_v3_test_client.py`，需要PySide6。
- 只读实机检查：`python host_sdk/check_hardware.py --port COM4 --actuator-power-isolated`，必须已实际隔离供电。

完整回卷/释放有用户实测成功日志，仍保留首次舵机启用后的Windows串口error5问题；不能把后续成功说成此问题已根治。实际惯性仍可能超零。
历史记录在`docs/archive/`及`docs/v3-bringup.md`，其中旧型号、供电、协议和固件状态不覆盖当前说明。
