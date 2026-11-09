"""Graphical test console for SurgeryBox V3 API v1 / protocol 8, power-on home."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host_sdk'))
from surgerybox_v3 import SurgeryBox, HardwareError
from PySide6.QtCore import QObject, QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtSerialPort import QSerialPortInfo
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QGroupBox, QCheckBox, QSpinBox, QPlainTextEdit,
    QTabWidget, QScrollArea, QProgressBar, QFileDialog)


class Backend(QObject):
    connected = Signal(object)
    disconnected = Signal(str)
    state = Signal(object)
    done = Signal(str, object)
    failed = Signal(str)
    wire = Signal(str)

    def __init__(self):
        super().__init__()
        self.tasks=queue.Queue(); self.client=None; self.generation=0; self.token=None
        self.shutdown=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True,name='hardware-test-worker')
        self.thread.start()

    def submit(self,name,*args):
        self.tasks.put((self.generation,name,args))

    def emergency(self,all_outputs=True):
        self.generation+=1; self.token=None
        target=self.client
        if target is None:return
        def stop():
            try:
                result=target.safe_off() if all_outputs else target.stop()
                self.done.emit('safe' if all_outputs else 'stop',result)
            except Exception as exc:self.failed.emit(str(exc))
        threading.Thread(target=stop,daemon=True,name='hardware-test-stop').start()

    def disconnect(self):
        self.emergency(); self.submit('disconnect')

    def run(self):
        last_poll=0
        try:
            while not self.shutdown.is_set():
                try:epoch,name,args=self.tasks.get(timeout=.03)
                except queue.Empty:name=None
                if name and epoch==self.generation:
                    try:
                        if name=='connect':
                            if self.client:self.client.close()
                            backend=self
                            class LoggedClient(SurgeryBox):
                                def _write(self,line):
                                    backend.wire.emit('TX '+line);return super()._write(line)
                                def _accept_line(self,line):
                                    backend.wire.emit('RX '+line);return super()._accept_line(line)
                            self.client=LoggedClient(*args)
                            self.connected.emit(self.client.identity)
                        elif name=='disconnect':
                            if self.client:self.client.close()
                            self.client=None; self.token=None
                            self.disconnected.emit('已断开；已发送SAFE')
                            continue
                        elif self.client:
                            methods={'light':self.client.set_light,'brake':self.client.set_brake,
                                'angle':self.client.set_brake_angle,'zero':self.client.zero,
                                'stream':self.client.stream,
                                'info':self.client.info,'bus':lambda:self.client.request('BUS?'),
                                'wind':self.client.wind,'release':self.client.release,'finish':self.client.finish}
                            if name=='refresh':result=self.client.status()
                            else:result=methods[name](*args)
                            if epoch!=self.generation:
                                self.client.safe_off()
                            else:
                                if name in ('wind','release'):self.token=result
                                self.done.emit(name,result)
                        last_poll=0
                    except Exception as exc:
                        self.failed.emit(str(exc))
                        if name=='connect':
                            if self.client:self.client.close()
                            self.client=None;self.disconnected.emit('连接失败')
                        else:self.done.emit(name,{'error':str(exc)})
                if self.client and time.monotonic()-last_poll>=.25:
                    try:
                        data=self.client.status();data['CLIENT']={'uncertain':self.client.uncertain}; self.state.emit(data); last_poll=time.monotonic()
                        m,j=data['MOTORPROBE'],data['JOB']
                        if self.token and m['id']==self.token and not m['active'] and not j['preparing']:
                            try:result=self.client.wait_motor(timeout=.6);self.done.emit('motor_complete',result)
                            except Exception as exc:self.failed.emit(str(exc));self.done.emit('motor_complete',{'error':str(exc)})
                            self.token=None
                        # SDK consumes events independently. Drain them so old telemetry does not accumulate.
                        while self.client.next_event() is not None:pass
                    except Exception as exc:
                        self.failed.emit(str(exc))
                        if self.client.fatal:
                            self.client.close();self.client=None;self.token=None
                            self.disconnected.emit('串口断开或主板重启，请重新连接')
                        last_poll=time.monotonic()
        finally:
            if self.client:self.client.close()

    def close(self):
        self.emergency();self.shutdown.set();self.thread.join(timeout=3)


REASONS={'boot_disarmed':'上电未使能','safe_off':'全部输出关闭','stopped':'电机已停止',
    'holding':'方向2回卷中','release_wait':'停机后等待换向','releasing_1s':'方向1释放1秒中',
    'release_complete':'释放完成','no_progress':'无位移进展，已停机','wrong_way':'方向异常，已停机',
    'hold_keepalive_lost':'电机心跳丢失，已停机','host_watchdog':'主机离线，输出关闭',
    'encoder_fault_home_invalid':'编码器跟踪失效，本次上电零点失效',
    'prepare_encoder_or_home_fault':'编码器或上电零点失效',
    'hold_time_limit':'连续回卷达到120秒上限，已停机'}


class TestConsole(QWidget):
    def __init__(self,port='COM4',backend=None):
        super().__init__()
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
        if font.exists():QFontDatabase.addApplicationFont(str(font))
        self.setStyleSheet("QWidget{font-family:'Microsoft YaHei';font-size:13px;} QPushButton{padding:7px;} QGroupBox{margin-top:8px;padding-top:12px;}")
        self.setWindowTitle('SurgeryBox V3 · 全功能硬件测试端');self.resize(1000,880)
        self.backend=backend or Backend();self.online=False;self.pending=False;self.latest={}
        self.last_state=0;self.owned_token=None;self.identity={};self.history=[];self.closing=False;self.emergency_wait=False
        folder=Path(__file__).resolve().parents[1]/'test_logs';folder.mkdir(exist_ok=True)
        self.log_path=folder/('hardware_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.txt')
        self.log_file=self.log_path.open('w',encoding='utf-8')
        root=QVBoxLayout(self);row=QHBoxLayout()
        self.port=QComboBox();self.port.setEditable(True)
        self.port.addItems(sorted(set([x.portName() for x in QSerialPortInfo.availablePorts()]+[port])))
        self.port.setCurrentText(port);row.addWidget(QLabel('串口'));row.addWidget(self.port)
        self.connect_button=QPushButton('连接');self.connect_button.clicked.connect(self.connect_port);row.addWidget(self.connect_button)
        self.refresh=QPushButton('刷新状态');self.refresh.clicked.connect(lambda:self.act('refresh'));row.addWidget(self.refresh)
        self.info_button=QPushButton('设备信息');self.info_button.clicked.connect(lambda:self.act('info'));row.addWidget(self.info_button)
        self.bus_button=QPushButton('I²C诊断');self.bus_button.clicked.connect(lambda:self.act('bus'));row.addWidget(self.bus_button)
        self.link=QLabel('未连接 · 需要固件3.1 / protocol=8');self.link.setWordWrap(True);row.addWidget(self.link,1);root.addLayout(row)
        tabs=QTabWidget();root.addWidget(tabs,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();layout=QVBoxLayout(page);scroll.setWidget(page);tabs.addTab(scroll,'功能测试')
        self.position=QLabel('相对位置：—');self.position.setStyleSheet('font-size:29px;font-weight:600;');layout.addWidget(self.position)
        self.encoder_info=QLabel('编码器：等待有效数据');layout.addWidget(self.encoder_info)
        row=QHBoxLayout();self.zero=QPushButton('当前位置显示归零');self.zero.clicked.connect(lambda:self.act('zero'));row.addWidget(self.zero)
        self.stream=QCheckBox('开启10Hz位置上报');self.stream.toggled.connect(lambda v:self.act('stream',v));row.addWidget(self.stream)
        row.addWidget(QLabel('每圈16384计数；显示归零不改变上电零点'));layout.addLayout(row)
        row=QHBoxLayout();brake=QGroupBox('舵机刹车');b=QVBoxLayout(brake)
        self.brake_status=QLabel('指令角度：—');b.addWidget(self.brake_status)
        buttons=QHBoxLayout();self.brake_buttons=[]
        for label,mode in [('释放180°','release'),('弱阻尼120°','weak'),('锁紧50°','lock'),('停止脉冲','off')]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,m=mode:self.act('brake',m));buttons.addWidget(button);self.brake_buttons.append(button)
        b.addLayout(buttons);micro=QHBoxLayout();self.angle=QSpinBox();self.angle.setRange(50,180);self.angle.setValue(180);micro.addWidget(self.angle)
        self.apply_angle=QPushButton('设置角度（单次≤5°）');self.apply_angle.clicked.connect(lambda:self.act('angle',self.angle.value()));micro.addWidget(self.apply_angle);b.addLayout(micro);row.addWidget(brake)
        lamp=QGroupBox('D3血迹灯');l=QVBoxLayout(lamp);self.lamp_status=QLabel('D3：—');l.addWidget(self.lamp_status)
        self.light_on=QPushButton('开灯 / D3高');self.light_off=QPushButton('关灯 / D3低')
        self.light_on.clicked.connect(lambda:self.act('light',True));self.light_off.clicked.connect(lambda:self.act('light',False));l.addWidget(self.light_on);l.addWidget(self.light_off);row.addWidget(lamp);layout.addLayout(row)
        group=QGroupBox('上电自动零点');g=QVBoxLayout(group)
        note=QLabel('主板上电后的第一个有效编码器位置自动记为收回零点。无需登记两端；拉出距离不限，回卷到零点即关闭电机，再释放摩擦轮1秒。显示归零不会移动收回零点。');note.setWordWrap(True);g.addWidget(note)
        self.travel=QLabel('上电零点：等待读取');g.addWidget(self.travel);layout.addWidget(group)
        group=QGroupBox('电机自动回卷与摩擦轮释放');m=QVBoxLayout(group)
        self.powered=QCheckBox('确认：执行器供电已恢复，机构可运动');self.powered.toggled.connect(self.power_mode);m.addWidget(self.powered)
        note=QLabel('回卷：刹车缓动释放180°并等待稳定→方向2返回上电零点→停止→方向1释放1秒→停止。无提前停车死区；连续回卷上限120秒，保留500ms无进展、250ms心跳和编码器失效停机。');note.setWordWrap(True);m.addWidget(note)
        motors=QHBoxLayout();self.wind=QPushButton('开始自动回卷');self.release=QPushButton('只释放摩擦轮1秒');self.finish=QPushButton('正常结束回卷并释放')
        self.wind.clicked.connect(lambda:self.act('wind'));self.release.clicked.connect(lambda:self.act('release'));self.finish.clicked.connect(lambda:self.act('finish'))
        for button in (self.wind,self.release,self.finish):button.setMinimumHeight(45);motors.addWidget(button)
        m.addLayout(motors);self.motor_status=QLabel('电机：等待连接');self.motor_status.setWordWrap(True);m.addWidget(self.motor_status);layout.addWidget(group);layout.addStretch()
        self.raw=QPlainTextEdit();self.raw.setReadOnly(True);tabs.addTab(self.raw,'原始状态')
        self.logs=QPlainTextEdit();self.logs.setReadOnly(True);self.logs.setMaximumBlockCount(600);tabs.addTab(self.logs,'通信日志')
        self.message=QLabel('动作由按钮触发，连接只读取状态。');self.message.setWordWrap(True);root.addWidget(self.message)
        bottom=QHBoxLayout();self.stop_button=QPushButton('急停电机（不反向）');self.safe_button=QPushButton('全部安全关闭（空格 / Esc）')
        self.stop_button.clicked.connect(lambda:self.emergency(False));self.safe_button.clicked.connect(lambda:self.emergency(True))
        for button in (self.stop_button,self.safe_button):button.setMinimumHeight(50);button.setStyleSheet('background:#b42318;color:white;font-size:18px;');bottom.addWidget(button)
        self.export=QPushButton('导出测试记录');self.export.clicked.connect(self.export_log);bottom.addWidget(self.export);root.addLayout(bottom)
        for key in ('Space','Esc'):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda:self.emergency(True))
        self.backend.connected.connect(self.on_connected);self.backend.disconnected.connect(self.on_disconnected)
        self.backend.state.connect(self.on_state);self.backend.done.connect(self.on_done);self.backend.failed.connect(self.on_error);self.backend.wire.connect(self.log)
        self.timer=QTimer(self);self.timer.timeout.connect(self.controls);self.timer.start(150);self.controls()

    def log(self,text):
        if self.log_file.closed:return
        line=datetime.now().isoformat(timespec='milliseconds')+' '+text
        self.log_file.write(line+'\n');self.log_file.flush()
        if not text.startswith('TX ~'):self.logs.appendPlainText(line)

    def connect_port(self):
        if self.online:self.backend.disconnect()
        else:self.pending=True;self.backend.submit('connect',self.port.currentText());self.link.setText('正在连接…');self.controls()

    def on_connected(self,identity):
        self.online=True;self.pending=False;self.identity=identity;self.latest={};self.last_state=0
        self.powered.setChecked(False);self.stream.blockSignals(True);self.stream.setChecked(False);self.stream.blockSignals(False)
        self.connect_button.setText('断开');self.log('IDENTITY '+json.dumps(identity));self.controls()

    def on_disconnected(self,message):
        self.online=False;self.pending=False;self.emergency_wait=False;self.owned_token=None;self.latest={};self.last_state=0
        self.powered.setChecked(False);self.connect_button.setText('连接');self.link.setText(message);self.controls()
        self.position.setText('相对位置：未连接');self.encoder_info.setText('编码器：无有效连接')

    def on_state(self,data):
        if self.closing:return
        self.latest=data;self.last_state=time.monotonic();self.raw.setPlainText(json.dumps(data,ensure_ascii=False,indent=2))
        e=data.get('I2CENC',{});valid=e.get('valid')==e.get('relative_valid')==1
        ticks=e.get('relative_ticks',0)
        self.position.setText(f'相对位置：{ticks:+d} 计数   {ticks/16384:+.4f} 圈' if valid else '相对位置：无效 / 等待恢复')
        self.encoder_info.setText(f'单圈角度 {e.get("angle_deg","—")}°   地址 {e.get("addr","—")}   累计错误 {e.get("errors","—")}   样本年龄 {e.get("age_ms","—")} ms')
        b=data.get('BRAKE',{});self.brake_status.setText(f'脉冲 {"开启" if b.get("enabled") else "关闭"}   指令 {b.get("angle","—")}° → 目标 {b.get("target",b.get("angle","—"))}°   {"缓动中" if b.get("moving") else ""}（非实测）')
        if not self.angle.hasFocus():self.angle.setValue(int(b.get('angle',180)))
        self.lamp_status.setText('D3引脚：'+str(data.get('LIGHT',{}).get('state','—'))+'（实体灯需观察）')
        m=data.get('MOTORPROBE',{});j=data.get('JOB',{})
        self.travel.setText(f'上电零点 {m.get("home","—")}   当前位置 {m.get("pos","—")}   零点{"有效" if m.get("home_valid") else "无效"} · 无拉出上限 / 无提前停车死区')
        reason=m.get('reason','—');self.motor_status.setText(('刹车释放准备中' if j.get('preparing') else REASONS.get(reason,reason))+f'   token={j.get("token",0)}')
        self.link.setText('已连接 · '+str(self.identity.get('boot','')));self.controls()

    def fresh(self):return self.online and bool(self.latest) and time.monotonic()-self.last_state<.9
    def motor_busy(self):return bool(self.latest.get('MOTORPROBE',{}).get('active') or self.latest.get('JOB',{}).get('preparing'))

    def controls(self):
        fresh=self.fresh();trusted=fresh and not self.latest.get('CLIENT',{}).get('uncertain');idle=trusted and not self.pending and not self.motor_busy()
        e=self.latest.get('I2CENC',{});m=self.latest.get('MOTORPROBE',{});b=self.latest.get('BRAKE',{})
        enc=fresh and e.get('valid')==e.get('relative_valid')==1 and e.get('age_ms',999)<=30
        for button in self.brake_buttons:button.setEnabled(idle)
        self.brake_buttons[-1].setEnabled(fresh and not self.pending)
        self.angle.setEnabled(idle);self.apply_angle.setEnabled(idle)
        self.light_on.setEnabled(trusted and not self.pending);self.light_off.setEnabled(fresh and not self.pending)
        self.zero.setEnabled(idle and e.get('valid')==1);self.stream.setEnabled(fresh and not self.pending)
        ready=enc and m.get('home_valid')==1
        self.wind.setEnabled(bool(idle and ready and self.powered.isChecked()));self.release.setEnabled(self.wind.isEnabled())
        self.finish.setEnabled(bool(fresh and not self.pending and self.owned_token and self.motor_busy() and not m.get('releasing')))
        self.refresh.setEnabled(self.online and not self.pending);self.info_button.setEnabled(self.refresh.isEnabled());self.bus_button.setEnabled(self.refresh.isEnabled());self.port.setEnabled(not self.online and not self.pending)
        self.connect_button.setEnabled(not self.pending or self.online);self.stop_button.setEnabled(self.online);self.safe_button.setEnabled(self.online)
        if self.online and not fresh:
            self.position.setText('相对位置：数据过期');self.link.setText('等待实时数据，动作按钮已禁用')

    def power_mode(self,checked):
        if not checked and self.motor_busy():self.emergency(True)
        self.controls()

    def act(self,name,*args):
        if not self.fresh() or self.pending:return
        if name in ('wind','release') and not self.wind.isEnabled():return
        self.pending=True;self.message.setText('执行中：'+name);self.log('ACTION '+name+' '+repr(args));self.backend.submit(name,*args);self.controls()

    def on_done(self,name,result):
        if name in ('safe','stop'):self.emergency_wait=False
        self.pending=self.emergency_wait
        if name in ('wind','release') and isinstance(result,int):self.owned_token=result
        if name in ('safe','stop','motor_complete'):self.owned_token=None
        self.history.append({'time':datetime.now().isoformat(),'action':name,'result':result})
        labels={'light':'灯指令已确认','brake':'舵机指令已确认','angle':'角度指令已确认',
            'zero':'显示相对零已设置','stream':'位置上报设置已确认','wind':'回卷任务已接受，等待执行结果','release':'释放任务已接受，等待执行结果',
            'finish':'已请求正常结束并释放','motor_complete':'电机流程完成','safe':'已确认：电机关闭、灯灭、舵机无脉冲','stop':'电机停止已确认',
            'refresh':'状态已刷新','info':'设备信息已写入日志和测试记录','bus':'I²C诊断结果：'+str(result)}
        self.message.setText('操作失败：'+str(result['error']) if isinstance(result,dict) and 'error' in result else labels.get(name,name+'已完成'))
        self.log('RESULT '+name+' '+json.dumps(result,ensure_ascii=False));self.controls()

    def on_error(self,message):
        self.message.setText('错误：'+message);self.log('ERROR '+message)

    def emergency(self,all_outputs=True):
        if self.online:
            self.emergency_wait=True;self.pending=True;self.owned_token=None;self.backend.emergency(all_outputs)
            self.message.setText('已发安全关闭' if all_outputs else '已发电机急停（不反向）');self.controls()

    def export_log(self):
        if self.motor_busy():self.emergency(True)
        filename,_=QFileDialog.getSaveFileName(self,'导出测试记录',str(self.log_path.with_suffix('.json')),'JSON (*.json)')
        if filename:Path(filename).write_text(json.dumps({'identity':self.identity,'latest':self.latest,'history':self.history,'wire_log':str(self.log_path)},ensure_ascii=False,indent=2),encoding='utf-8')

    def event(self,event):
        if event.type()==QEvent.WindowDeactivate and hasattr(self,'latest') and (self.motor_busy() or self.pending or self.owned_token):self.emergency(True)
        return super().event(event)

    def closeEvent(self,event):
        self.closing=True;self.timer.stop();self.backend.close();self.log_file.close();event.accept()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',default='COM4');parser.add_argument('--connect',action='store_true');args=parser.parse_args()
    app=QApplication(sys.argv);window=TestConsole(args.port);window.show()
    if args.connect:QTimer.singleShot(300,window.connect_port)
    sys.exit(app.exec())
