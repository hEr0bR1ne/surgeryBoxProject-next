"""Manual D1 R1 servo calibration window. Requires PySide6 only."""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QIODevice
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QSlider, QGroupBox, QPlainTextEdit, QFileDialog,
)


def parse_state(line):
    if not line.startswith("STATE:"):
        return None
    try:
        enabled, output, target = map(int, line[6:].split(","))
        if enabled not in (0, 1) or not (0 <= output <= 180 and 0 <= target <= 180):
            return None
        return bool(enabled), output, target
    except ValueError:
        return None


class ServoTuner(QWidget):
    def __init__(self):
        super().__init__()
        # Also provide CJK glyphs when rendering via Qt's offscreen plugin.
        if "Microsoft YaHei" not in QFontDatabase.families():
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
        self.setWindowTitle("SurgeryBox · 舵机角度调试")
        self.resize(760, 720)
        self.serial = QSerialPort(self)
        self.serial.readyRead.connect(self.read_serial)
        self.serial.errorOccurred.connect(self.serial_error)
        self.buffer = bytearray()
        self.verified = False
        self.state = None
        self.last_rx = 0
        self.connected_at = 0
        self.records = {}
        self.pending_target = None
        self.controls = []
        self.record_buttons = []

        layout = QVBoxLayout(self)
        title = QLabel("舵机角度调试")
        title.setStyleSheet("font-size:26px; font-weight:700; color:#16334d")
        layout.addWidget(title)
        layout.addWidget(QLabel("WEMOS D1 R1  ·  信号 D2 / GPIO16  ·  串口 115200"))
        row = QHBoxLayout()
        self.ports = QComboBox()
        self.ports.setEditable(True)
        row.addWidget(self.ports, 1)
        refresh = QPushButton("刷新串口")
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self.toggle_connection)
        row.addWidget(self.connect_button)
        layout.addLayout(row)
        self.connection_label = QLabel("未连接；请先烧录配套 ServoTuner 固件")
        self.connection_label.setWordWrap(True)
        layout.addWidget(self.connection_label)

        status_box = QGroupBox("板子返回的状态")
        status_layout = QVBoxLayout(status_box)
        self.angle_label = QLabel("输出角度 —    目标角度 —")
        self.angle_label.setStyleSheet("font-size:24px; font-weight:600; padding:8px")
        self.output_label = QLabel("输出状态：未知")
        status_layout.addWidget(self.angle_label)
        status_layout.addWidget(self.output_label)
        note = QLabel("这是板子已设置的角度，不是轴位置或刹车力度的传感器测量值。")
        note.setWordWrap(True)
        status_layout.addWidget(note)
        layout.addWidget(status_box)

        angle_box = QGroupBox("选择角度，再点击发送")
        angle_layout = QVBoxLayout(angle_box)
        selection = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 180)
        self.slider.setValue(90)
        self.angle = QSpinBox()
        self.angle.setRange(0, 180)
        self.angle.setSuffix(" °")
        self.angle.setValue(90)
        self.slider.valueChanged.connect(self.angle.setValue)
        self.angle.valueChanged.connect(self.slider.setValue)
        selection.addWidget(self.slider, 1)
        selection.addWidget(self.angle)
        angle_layout.addLayout(selection)
        angle_layout.addWidget(QLabel("拖动滑块或输入数字只选值，不会立即转动。"))
        steps = QHBoxLayout()
        for delta in (-10, -5, -1, 1, 5, 10):
            button = QPushButton(f"{delta:+d}°")
            button.clicked.connect(lambda checked=False, d=delta: self.step(d))
            steps.addWidget(button)
            self.controls.append(button)
        angle_layout.addLayout(steps)
        angle_layout.addWidget(QLabel("步进按钮会立即发送，以板子最近返回的目标角度为基准。"))
        actions = QHBoxLayout()
        self.send_button = QPushButton("发送所选角度 / 启用输出")
        self.send_button.clicked.connect(self.send_angle)
        self.send_button.setStyleSheet("background:#176e8a;color:white;padding:10px")
        actions.addWidget(self.send_button, 2)
        self.stop_button = QPushButton("停止控制脉冲")
        self.stop_button.setStyleSheet("background:#a32a37;color:white;padding:10px")
        self.stop_button.clicked.connect(lambda: self.send("OFF"))
        actions.addWidget(self.stop_button, 1)
        self.controls.extend([self.send_button, self.stop_button])
        angle_layout.addLayout(actions)
        warning = QLabel("先确认机械行程再扩大范围。停止脉冲不等于断电，也不保证刹车保持或释放。")
        warning.setWordWrap(True)
        angle_layout.addWidget(warning)
        layout.addWidget(angle_box)

        record_box = QGroupBox("记录合适的刹车角度")
        record_layout = QVBoxLayout(record_box)
        record_row = QHBoxLayout()
        for key, label in (("release", "释放"), ("weak", "弱阻尼"), ("lock", "锁定")):
            button = QPushButton(f"记录为{label}")
            button.clicked.connect(lambda checked=False, k=key: self.record(k))
            self.record_buttons.append(button)
            record_row.addWidget(button)
        record_layout.addLayout(record_row)
        self.record_label = QLabel("释放：—    弱阻尼：—    锁定：—")
        record_layout.addWidget(self.record_label)
        export = QPushButton("导出角度记录 JSON（发给我整合）")
        export.clicked.connect(self.export_records)
        record_layout.addWidget(export)
        layout.addWidget(record_box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(150)
        self.log.setMaximumHeight(100)
        layout.addWidget(self.log)
        self.setStyleSheet("QWidget{font-family:'Microsoft YaHei';font-size:13px;}"
                          "QGroupBox{margin-top:10px;padding-top:16px;} QPushButton{min-height:26px;}")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.refresh_ports()
        self.update_controls()

    def refresh_ports(self):
        previous = self.ports.currentText()
        self.ports.clear()
        names = [p.portName() for p in QSerialPortInfo.availablePorts()]
        self.ports.addItems(names)
        self.ports.setCurrentText(previous or ("COM4" if "COM4" in names else next(iter(names), "COM4")))

    def update_controls(self):
        for control in self.controls:
            control.setEnabled(self.verified)
        settled = bool(self.verified and self.state and self.state[0]
                       and self.pending_target is None
                       and self.state[1] == self.state[2] and time.monotonic() - self.last_rx < 3)
        for button in self.record_buttons:
            button.setEnabled(settled)

    def toggle_connection(self):
        if self.serial.isOpen():
            self.disconnect()
            return
        self.serial.setPortName(self.ports.currentText().strip())
        self.serial.setBaudRate(115200)
        self.serial.setFlowControl(QSerialPort.NoFlowControl)
        if not self.serial.open(QIODevice.ReadWrite):
            self.connection_label.setText("连接失败：" + self.serial.errorString())
            return
        self.serial.setDataTerminalReady(False)
        self.serial.setRequestToSend(False)
        self.buffer.clear()
        self.state = None
        self.verified = False
        self.connected_at = time.monotonic()
        self.last_rx = self.connected_at
        self.connect_button.setText("断开")
        self.ports.setEnabled(False)
        self.connection_label.setText("正在识别调试固件；不会自动启用舵机")
        self.send("HELLO_TUNER")

    def disconnect(self, reason="已断开；停止指令已尝试发送，固件也有3秒通信超时停脉冲"):
        if self.serial.isOpen():
            if self.verified:
                self.send("OFF")
                self.serial.waitForBytesWritten(200)
            self.serial.close()
        self.verified = False
        self.state = None
        self.pending_target = None
        self.buffer.clear()
        self.angle_label.setText("输出角度 —    目标角度 —")
        self.output_label.setText("输出状态：未连接，无法读取")
        self.connect_button.setText("连接")
        self.ports.setEnabled(True)
        self.connection_label.setText(reason)
        self.update_controls()

    def serial_error(self, error):
        if error in (QSerialPort.ResourceError, QSerialPort.DeviceNotFoundError):
            self.disconnect("设备已断开：" + self.serial.errorString())

    def send(self, command):
        if not self.serial.isOpen():
            return False
        payload = (command + "\n").encode("ascii")
        written = self.serial.write(payload)
        if command != "PING":
            self.log.appendPlainText("→ " + command)
        return written == len(payload)

    def send_angle(self):
        if self.verified:
            if self.send(f"SET:{self.angle.value()}"):
                self.pending_target = self.angle.value()
                self.update_controls()

    def step(self, delta):
        if not self.verified or self.state is None:
            return
        self.angle.setValue(max(0, min(180, self.state[2] + delta)))
        self.send_angle()

    def tick(self):
        if not self.serial.isOpen():
            return
        now = time.monotonic()
        if not self.verified:
            if now - self.connected_at > 5:
                self.disconnect("未识别到配套固件：请先烧录 ServoTuner，自动往返固件不支持此工具")
            else:
                self.send("HELLO_TUNER")
        elif now - self.last_rx > 3:
            self.disconnect("板子状态超时，已停止发送角度；请检查连接")
        else:
            self.send("PING")
        self.update_controls()

    def read_serial(self):
        self.buffer.extend(bytes(self.serial.readAll()))
        if len(self.buffer) > 8192:
            self.buffer.clear()
            return
        while b"\n" in self.buffer:
            raw, _, remaining = self.buffer.partition(b"\n")
            self.buffer = bytearray(remaining)
            self.handle_line(raw.decode("utf-8", errors="replace").strip())

    def handle_line(self, line):
        if line == "TUNER:1":
            self.verified = True
            self.last_rx = time.monotonic()
            self.connection_label.setText("已连接配套固件；选择角度后点击发送")
        state = parse_state(line)
        if state is not None and self.verified:
            self.state = state
            self.last_rx = time.monotonic()
            enabled, output, target = state
            if not enabled or output == target == self.pending_target:
                self.pending_target = None
            self.angle_label.setText(f"输出角度 {output}°    目标角度 {target}°")
            self.output_label.setText("输出状态：" + ("保持中" if output == target else "移动中") if enabled
                                      else "输出状态：已停止脉冲（角度为最后指令记录）")
        elif line:
            self.log.appendPlainText("← " + line)
        self.update_controls()

    def record(self, key):
        if not (self.verified and self.state and self.state[0] and self.pending_target is None
                and self.state[1] == self.state[2]
                and time.monotonic() - self.last_rx < 3):
            self.log.appendPlainText("请等板子输出到达目标角度，再记录。")
            return
        self.records[key] = self.state[1]
        self.record_label.setText("    ".join(
            f"{label}：{self.records.get(k, '—')}°" for k, label in
            (("release", "释放"), ("weak", "弱阻尼"), ("lock", "锁定"))))

    def export_records(self):
        if not self.records:
            self.log.appendPlainText("请先记录至少一个角度。")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "导出角度记录", "servo_calibration.json", "JSON (*.json)")
        if not filename:
            return
        payload = {"schema_version": 1, "board": "WEMOS D1 R1", "gpio": 16,
                   "angles_deg": self.records, "measurement": "commanded_not_measured",
                   "created_at": datetime.now().isoformat(timespec="seconds")}
        try:
            Path(filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.log.appendPlainText("已导出：" + filename)
        except OSError as exc:
            self.log.appendPlainText("导出失败：" + str(exc))

    def closeEvent(self, event):
        self.timer.stop()
        self.disconnect()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ServoTuner()
    window.show()
    sys.exit(app.exec())
