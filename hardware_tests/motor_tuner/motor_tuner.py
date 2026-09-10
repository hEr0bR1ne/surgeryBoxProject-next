"""Manual motor tester for the guarded SurgeryBox main firmware. PySide6 only."""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QIODevice, QTimer, Qt
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QGroupBox, QPlainTextEdit,
    QCheckBox, QFileDialog, QProgressBar)


def parse_state(line):
    if not line.startswith('TRAVEL:home='):
        return None
    try:
        s = dict(x.split('=', 1) for x in line[7:].split(','))
        for key in ('home', 'pos', 'low', 'high', 'stop', 'active', 'pwm'):
            s[key] = int(s[key])
        if (s['home'] not in (0, 1) or s['active'] not in (0, 1)
                or (s['low'], s['high'], s['stop']) != (1745, 33146, 1945)
                or not 300 <= s['pwm'] <= 700
                or s['direction'] not in ('F', 'R', 'unknown')
                or s.get('control') != 'dir_pwm_v1' or s.get('matrix') != '1'):
            return None
        s['reason']  # Require a complete status, not a command echo.
        return s
    except (ValueError, KeyError):
        return None


class MotorTuner(QWidget):
    def __init__(self):
        super().__init__()
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
        self.setWindowTitle('SurgeryBox · 电机手动测试')
        self.resize(880, 820)
        self.serial = QSerialPort(self)
        self.serial.readyRead.connect(self.read_serial)
        self.serial.errorOccurred.connect(self.serial_error)
        self.buffer = bytearray()
        self.handshake = False
        self.state = None
        self.last_rx = 0
        self.opened_at = 0
        self.pending = None
        self.run_record = None
        self.history = []
        self.events = []
        self.last_logged_status = None
        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(lambda: self.stop('设定时间到达'))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(200)
        layout = QVBoxLayout(self)
        title = QLabel('电机手动测试')
        title.setStyleSheet('font-size:26px;font-weight:700;color:#15364b')
        layout.addWidget(title)
        layout.addWidget(QLabel('D1 R1  ·  AIN1 → D7  /  AIN2 → D8  ·  编码器 A → D5 / B → D6'))
        row = QHBoxLayout()
        self.ports = QComboBox(); self.ports.setEditable(True)
        self.ports.addItems([p.portName() for p in QSerialPortInfo.availablePorts()])
        self.ports.setCurrentText('COM4')
        row.addWidget(self.ports, 1)
        self.connect_button = QPushButton('连接主板')
        self.connect_button.clicked.connect(self.toggle_connection)
        row.addWidget(self.connect_button)
        self.export_button = QPushButton('导出测试记录')
        self.export_button.clicked.connect(self.export)
        row.addWidget(self.export_button)
        layout.addLayout(row)
        self.connection_label = QLabel('未连接。需烧录新版输入组合保护主程序；常转程序和旧版固件不支持本工具。')
        self.connection_label.setWordWrap(True)
        layout.addWidget(self.connection_label)
        status = QGroupBox('实时状态')
        box = QVBoxLayout(status)
        self.position = QLabel('位置 —')
        self.position.setStyleSheet('font-size:30px;font-weight:600')
        box.addWidget(self.position)
        self.bar = QProgressBar(); self.bar.setRange(0, 34891)
        self.bar.setTextVisible(False); box.addWidget(self.bar)
        self.details = QLabel('等待板子返回状态')
        self.details.setWordWrap(True); box.addWidget(self.details)
        box.addWidget(QLabel('物理控制区间 1,745～33,146；方向试转只允许在 14,000～20,000。'))
        layout.addWidget(status)
        self.home_check = QCheckBox('我已手动放回原始机械零点（不是当前位置任意清零）')
        layout.addWidget(self.home_check)
        self.home_button = QPushButton('登记原始零点')
        self.home_button.clicked.connect(self.home)
        self.home_check.stateChanged.connect(self.update_controls)
        layout.addWidget(self.home_button)
        controls = QGroupBox('单次试转 · 改数值不会自动运行')
        box = QVBoxLayout(controls)
        row = QHBoxLayout()
        row.addWidget(QLabel('输入组合'))
        self.direction = QComboBox()
        for combo in (1, 3, 5, 7, 0, 8, 4, 2, 6):
            levels = ('低', 'PWM', '高')
            suffix = '（全驱动，最多200ms）' if combo in (2, 6) else ''
            self.direction.addItem(f'{combo}: AIN1={levels[combo//3]} / AIN2={levels[combo%3]} {suffix}', str(combo))
        row.addWidget(self.direction, 1)
        row.addWidget(QLabel('运行时间'))
        self.duration = QSpinBox(); self.duration.setRange(100, 2000)
        self.duration.setSingleStep(100); self.duration.setValue(200)
        self.duration.setSuffix(' ms'); row.addWidget(self.duration)
        box.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel('PWM 输出'))
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(300, 700)
        self.pwm = QSpinBox(); self.pwm.setRange(300, 700); self.pwm.setValue(512)
        self.slider.setValue(512)
        self.slider.valueChanged.connect(self.pwm.setValue)
        self.pwm.valueChanged.connect(self.slider.setValue)
        self.percent = QLabel('50.0%')
        self.pwm.valueChanged.connect(lambda v: self.percent.setText(f'{100*v/1023:.1f}%'))
        row.addWidget(self.slider, 1); row.addWidget(self.pwm); row.addWidget(self.percent)
        box.addLayout(row)
        note = QLabel('选择组合逐项测试；高/低组合为全驱动，PWM滑块对它无效。\n'
                      '普通组合最多2秒；高/低组合最多200ms；任一方向位移150计数提前停。')
        note.setWordWrap(True); box.addWidget(note)
        row = QHBoxLayout()
        self.run_button = QPushButton('点动一次')
        self.run_button.setStyleSheet('background:#176e8a;color:white;padding:12px;font-size:18px')
        self.run_button.clicked.connect(self.run)
        row.addWidget(self.run_button, 2)
        self.stop_button = QPushButton('停止电机')
        self.stop_button.setStyleSheet('background:#b32c40;color:white;padding:12px;font-size:18px')
        self.stop_button.clicked.connect(lambda: self.stop('用户点击停止'))
        row.addWidget(self.stop_button, 1); box.addLayout(row)
        self.run_hint = QLabel()
        self.run_hint.setWordWrap(True)
        self.run_hint.setStyleSheet('font-weight:600;padding:6px;color:#805315')
        box.addWidget(self.run_hint)
        layout.addWidget(controls)
        self.result = QLabel('本次位移：—')
        self.result.setWordWrap(True); layout.addWidget(self.result)
        self.observation = QComboBox()
        self.observation.addItems(['尚未记录观察', '明显收线', '离合器已脱离', '意外放线 / 线变松',
                                   '电机转但没带动线', '仅抖动 / 有声音', '完全无动作'])
        row = QHBoxLayout(); row.addWidget(QLabel('最近一次观察')); row.addWidget(self.observation, 1)
        save_note = QPushButton('保存观察到最近一次测试')
        save_note.clicked.connect(self.save_observation); row.addWidget(save_note)
        layout.addLayout(row)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200); self.log.setMaximumHeight(135)
        layout.addWidget(self.log)
        footer = QLabel('全部外设由外部 24V 供电，主板由 USB 供电。断开 24V 后的移动不会被记录。\n'
                        '关闭窗口会发送停止；掉线时无法确认现场状态，固件仍有 2 秒上限。')
        footer.setWordWrap(True); layout.addWidget(footer)
        self.setStyleSheet("QWidget{font-family:'Microsoft YaHei';font-size:13px;}"
                          'QGroupBox{margin-top:8px;padding-top:16px;} QPushButton{min-height:25px;}')
        self.update_controls()

    def fresh(self):
        return bool(self.handshake and self.state and time.monotonic() - self.last_rx < 1.5)

    def update_controls(self, *_):
        idle = self.fresh() and not self.state['active'] and not self.pending and not self.run_record
        self.run_button.setEnabled(bool(idle and self.state['home'] and 14000 <= self.state['pos'] <= 20000))
        if not self.fresh():
            hint = ('无法运行：未连接主板，请先点击“连接主板”。' if not self.serial.isOpen() else
                    '无法运行：正在等待有效状态，请查看顶部连接提示。')
        elif self.state['active']:
            hint = '电机正在运行；请等待停止，或点击“停止电机”。'
        elif self.pending:
            hint = '正在确认所选参数，请稍候。'
        elif self.run_record:
            hint = '正在等待本次试转结束状态；必要时点击“停止电机”。'
        elif not self.state['home']:
            hint = '无法运行：物理零点未确认。先回原机械零点，再勾选并登记零点。'
        elif self.state['pos'] < 14000:
            hint = f"无法运行：当前位置 {self.state['pos']:,}，请手动拉到 14,000～20,000 并停稳。"
        elif self.state['pos'] > 20000:
            hint = f"无法运行：当前位置 {self.state['pos']:,}，请手动退回 14,000～20,000 并停稳。"
        else:
            hint = '可以运行：保持手不拉动，选好参数后点击“运行一次”。'
        self.run_hint.setText(hint)
        self.run_button.setToolTip(hint)
        self.home_button.setEnabled(bool(idle and self.home_check.isChecked()))
        for widget in (self.direction, self.duration, self.pwm, self.slider):
            widget.setEnabled(not self.pending and not self.run_record)
        self.stop_button.setEnabled(self.serial.isOpen())

    def log_message(self, message):
        stamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.log.appendPlainText(f'[{stamp}] {message}')

    def send(self, command):
        if not self.serial.isOpen(): return False
        data = (command + '\n').encode('ascii')
        ok = self.serial.write(data) == len(data)
        if command != 'TRAVEL?': self.log_message('→ ' + command)
        return ok

    def toggle_connection(self):
        if self.serial.isOpen(): self.disconnect(); return
        self.serial.setPortName(self.ports.currentText().strip())
        self.serial.setBaudRate(115200)
        self.serial.setFlowControl(QSerialPort.NoFlowControl)
        if not self.serial.open(QIODevice.ReadWrite):
            self.connection_label.setText('连接失败：' + self.serial.errorString()); return
        self.serial.setDataTerminalReady(False); self.serial.setRequestToSend(False)
        self.handshake = False; self.state = None; self.buffer.clear()
        self.last_logged_status = None
        self.opened_at = time.monotonic(); self.last_rx = self.opened_at
        self.connect_button.setText('断开'); self.ports.setEnabled(False)
        self.connection_label.setText('正在识别主程序；不会自动运行或重新归零')
        self.send('HELLO_PC'); self.send('TRAVEL?')

    def disconnect(self, message='已断开；停止指令已尝试发送'):
        self.stop_timer.stop()
        if self.serial.isOpen():
            self.send('MS'); self.serial.waitForBytesWritten(100); self.serial.close()
        if self.run_record:
            self.run_record['result'] = 'connection_lost_or_closed; final position unknown'
            self.history.append(self.run_record)
        self.run_record = None; self.pending = None
        self.handshake = False; self.state = None; self.buffer.clear()
        self.connect_button.setText('连接主板'); self.ports.setEnabled(True)
        self.connection_label.setText(message); self.details.setText('已断开，现场状态未知')
        self.position.setText('位置 —（已断开）')
        self.update_controls()

    def serial_error(self, error):
        if error in (QSerialPort.ResourceError, QSerialPort.DeviceNotFoundError) and self.serial.isOpen():
            self.disconnect('串口断开：' + self.serial.errorString())

    def home(self):
        if self.fresh() and not self.state['active'] and not self.pending and not self.run_record and self.home_check.isChecked():
            self.send('TRAVEL:HOME'); self.home_check.setChecked(False)

    def run(self):
        if not (self.fresh() and self.state['home'] and not self.state['active']
                and not self.pending and not self.run_record and 14000 <= self.state['pos'] <= 20000): return
        self.pending = dict(direction=self.direction.currentData(), pwm=self.pwm.value(),
                            duration_ms=min(self.duration.value(), 200) if self.direction.currentData() in ('2', '6') else self.duration.value(), queued=time.monotonic(),
                            start_ticks=self.state['pos'])
        if not self.send(f"MOTOR:PWM:{self.pending['pwm']}"):
            self.pending = None
        self.update_controls()

    def stop(self, source='取消或异常处理'):
        self.pending = None; self.stop_timer.stop()
        self.log_message('停止来源：' + source)
        if self.run_record:
            self.run_record['stop_requested_by'] = source
        self.send('MS'); self.send('TRAVEL?'); self.update_controls()

    def tick(self):
        if not self.serial.isOpen(): return
        now = time.monotonic()
        if self.pending and now - self.pending['queued'] > 1:
            self.stop(); self.connection_label.setText('参数确认超时，未启动试转')
        if (self.handshake and now - self.last_rx > 1.5) or (not self.handshake and now - self.opened_at > 5):
            self.disconnect('状态超时，已尝试停止。请检查连接或主程序版本。'); return
        if not self.handshake: self.send('HELLO_PC')
        self.send('TRAVEL?'); self.update_controls()

    def read_serial(self):
        self.buffer.extend(bytes(self.serial.readAll()))
        if len(self.buffer) > 16384:
            self.disconnect('串口数据异常，已尝试停止'); return
        while b'\n' in self.buffer:
            raw, _, rest = self.buffer.partition(b'\n'); self.buffer = bytearray(rest)
            self.handle_line(raw.decode('utf-8', errors='replace').strip())

    def handle_line(self, line):
        if line.startswith('PINS:') and self.run_record and self.state and self.state['active']:
            try:
                pins = dict(item.split('=', 1) for item in line[5:].split(','))
                d7, d8 = int(pins['D7']), int(pins['D8'])
                if d7 not in (0, 1) or d8 not in (0, 1): raise ValueError('invalid pin level')
                sample = dict(time=datetime.now().isoformat(timespec='milliseconds'), d7=d7, d8=d8)
                samples = self.run_record.setdefault('input_pin_samples', [])
                if not samples:
                    self.log_message(f'引脚瞬时读回：D7={d7}、D8={d8}；PWM脚瞬时0/1不代表占空比或轴转向。')
                samples.append(sample)
            except (ValueError, KeyError):
                self.log_message('无法解析方向脚回执：' + line)
            return
        if line == 'ACK: HELLO_PC': self.handshake = True
        if line.startswith(('MOTOR_CONTINUOUS:', 'MOTOR_DIR_PWM:')) or (
                line.startswith('TRAVEL:home=') and ('control=dir_pwm_v1' not in line or 'matrix=1' not in line)):
            self.disconnect('固件不兼容：请先烧录新版输入组合保护主程序；常转固件需断24V停止。')
            return
        s = parse_state(line)
        if s and self.handshake:
            self.state = s; self.last_rx = time.monotonic()
            status_key = (s['active'], s['reason'], s['home'], s['pwm'])
            if status_key != self.last_logged_status:
                self.log_message('← ' + line)
                self.last_logged_status = status_key
            self.position.setText(f"位置 {s['pos']:,} 计数")
            self.bar.setValue(max(0, min(34891, s['pos'])))
            self.details.setText(f"零点：{'已确认' if s['home'] else '需回原零点确认'}   "
                f"电机：{'运行中' if s['active'] else '已停止'}   PWM：{s['pwm']}   "
                f"回卷方向：{s['direction']}\n停止/状态原因：{s['reason']}")
            self.connection_label.setText('已连接；拉到中段、停稳后点击运行一次')
            if self.pending and s['reason'] == 'pwm_set_probe_required' and s['pwm'] == self.pending['pwm']:
                request = self.pending; self.pending = None
                if s['home'] and not s['active'] and 14000 <= s['pos'] <= 20000 and abs(s['pos'] - request['start_ticks']) <= 2:
                    self.run_record = dict(direction=request['direction'], combination=int(request['direction']), pwm=request['pwm'],
                        ain1=('LOW','PWM','HIGH')[int(request['direction'])//3],
                        ain2=('LOW','PWM','HIGH')[int(request['direction'])%3],
                        requested_ms=request['duration_ms'], start_ticks=s['pos'],
                        created_at=datetime.now().isoformat(timespec='seconds'), seen_active=False,
                        sent_monotonic=time.monotonic())
                    self.log_message(f"本次设置：组合 {request['direction']}，PWM {request['pwm']}/1023，"
                                     f"请求 {request['duration_ms']} ms，起点 {s['pos']}；固件执行时长和行程保护")
                    if self.send(f"MOTOR:MATRIX:{request['direction']}:{request['duration_ms']}"):
                        self.stop_timer.start(request['duration_ms'])
                    else:
                        self.run_record['result'] = 'send_failed'; self.history.append(self.run_record)
                        self.run_record = None; self.stop()
                else: self.connection_label.setText('位置变化或状态不满足条件，未启动')
            if self.run_record:
                if s['active']:
                    self.run_record['seen_active'] = True
                    self.send('PINS?')
                elif self.run_record['seen_active'] or s['reason'] not in ('pwm_set_probe_required', 'probing'):
                    self.stop_timer.stop()
                    r = self.run_record; r['end_ticks'] = s['pos']
                    r['delta_ticks'] = s['pos'] - r['start_ticks']; r['reason'] = s['reason']
                    r['observed_completion_ms'] = round((time.monotonic() - r.pop('sent_monotonic')) * 1000)
                    self.history.append(r); self.run_record = None
                    self.result.setText(f"本次位移：{r['delta_ticks']:+,} 计数   结束：{s['reason']}")
                    self.log_message(f"测试结束：观察到停止用时 {r['observed_completion_ms']} ms，"
                        f"位移 {r['delta_ticks']:+}，原因 {r['reason']}；该用时包含串口延迟")
                    self.observation.setCurrentIndex(0)
            self.events.append(dict(time=datetime.now().isoformat(timespec='milliseconds'), **s))
            self.events = self.events[-10000:]
        elif line.startswith('ERROR:'):
            self.log_message('← ' + line)
            self.stop()
        elif line and line not in ('TRAVEL?', 'ACK: HELLO_PC') and not line.startswith('[Serial CMD] Received: TRAVEL?'):
            self.log_message('← ' + line)
        self.update_controls()

    def save_observation(self):
        if self.history:
            self.history[-1]['observation'] = self.observation.currentText()
            self.log.appendPlainText('已保存最近一次的现场观察')

    def export(self):
        filename, _ = QFileDialog.getSaveFileName(self, '导出测试记录',
            str(Path(__file__).parent / 'motor_test_results.json'), 'JSON (*.json)')
        if filename:
            try:
                Path(filename).write_text(json.dumps(dict(schema_version=2, board='WEMOS D1 R1',
                    tests=self.history, status_samples=self.events), ensure_ascii=False, indent=2), encoding='utf-8')
                self.log.appendPlainText('已导出：' + filename)
            except OSError as exc: self.log.appendPlainText('导出失败：' + str(exc))

    def closeEvent(self, event):
        self.timer.stop(); self.disconnect(); event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MotorTuner(); window.show()
    sys.exit(app.exec())
