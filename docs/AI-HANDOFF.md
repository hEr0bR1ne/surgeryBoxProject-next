# SurgeryBox V3 3.1.0交接

当前主板已烧录**3.1.0 / API v1 / protocol=8**。硬件接口、独立测试端和Python SDK已就绪，下一步由上位机开发者接入训练界面。
本次发布包：`releases/surgerybox-v3-3.1.0-20261109.zip`；镜像与证据：`releases/surgerybox-v3-3.1.0/`。
不要烧录根目录旧`src/`入口，也不要使用旧protocol=7 SDK或单项电机测试程序接入新版。

## 接手顺序

1. 读[硬件接口](v3-hardware-api.md)：接线、SDK、报文、任务生命周期与零点规则。
2. 双击`tools/StartHardwareTest.cmd`，或安装`host_sdk/requirements-gui.txt`后运行`python tools/v3_test_client.py --port COM4`。
3. 从`host_sdk/example.py`接入上位机，只让一个SurgeryBox对象长期持有USB串口；UI按键触发动作，连接仅查询。
4. 状态以实时查询为准。上位机关闭/失焦按产品需求调用safe_off()；断线后不自动重放动作。

## 已确定行为

- 上电后第一个有效编码器读数自动作为收回零点，不自动运动找机械端点。希望卷回哪里，就在那个位置上电。
- 不再标定收回端/拉出端；无拉出距离上限、无最小行程、无提前停车死区。显示归零与电脑端重连不改上电零点。
- 方向2（D7低/D8高）计数增加，回到/跨过上电零点即关闭，再停50ms，方向1（D7高/D8低）释放摩擦轮1秒后停止。
- 舵机释放180°、弱阻尼120°、锁紧50°，指令速度75°/秒；完成缓动再等500ms才启动回卷。
- 灯D3高有效；编码器MT6701 I2C地址0x06，每圈16384计数，累计跨圈，无毫米换算。
- 故障、STOP、SAFE不自动反向。无进展/错误方向/失联/编码器异常停机，连续回卷硬上限120秒。
- 编码器失去连续性后home失效，不能用ZERO或重连掩盖；重新上电才捕获新零点。

## 已验证与剩余问题

已完成290464字节写入校验，镜像SHA256：`96112899e6bcc152d2ef908ca1a5b5bc54636bd88b687284ec51b12d625c8af9`。
构建/策略静态检查、13项SDK测试、13项GUI测试、25次隔离状态只读实机查询均通过。
用户在3.1.0测试端完成多次缓动刹车、灯开关和回卷；token1715103486返回release_complete，encoder errors=0、dropped_frames=0。用户随后确认效果满意并要求发布交接。

保留两项实际观察：

- 20:42:36第一次BRAKE:WEAK后仍有一次Windows COM4 error5；重新连接后多次舵机/灯/回卷成功，boot未变。根因未确定，不能保证首次附加舵机绝不断连。
- 回卷完成时记录pos=86、home=0，约1.89°编码器角位移，随后末次查询pos=85。软件无预留死区，采样与惯性仍可能造成少量超零；没有毫米标定。

证据见[验证记录](v3-hardware-validation.md)和`releases/surgerybox-v3-3.1.0/operator-test.log`。日志只记录历史，不代表当前执行器输出或供电状态。

## 上位机需要做的事

使用SDK的position()/status()接位置显示，set_brake()/set_light()接训练动作，wind()/release()/finish()/stop()/safe_off()接回卷与停车。
只把同token、preparing=0、active=0、reason=release_complete当作正常完成；不能把ACCEPTED当完成。
不要恢复旧两端标定界面、百分比余量、UDP训练事件或伪造毫米。显示ZERO可以用于训练相对位置，回卷仍回上电零点。
完整场景流程、训练剧情、旧simulator UI与新SDK接合尚未在本次交付中完成。

历史版本的工作记录在`archive/AI-HANDOFF-before-v3-release-20261109.md`，不应照着旧状态恢复固件或供电。
