"""USB serial hardware connector for the surgery box MCU."""

from __future__ import annotations

import re
import time
from typing import List

from PySide6.QtCore import QThread, Signal
from app.hardware.serial_probe import probe_serial_connection

try:
    import serial
    from serial.tools import list_ports
except Exception as exc:  # pragma: no cover - surfaced in UI at runtime.
    serial = None
    list_ports = None
    SERIAL_IMPORT_ERROR = exc
else:
    SERIAL_IMPORT_ERROR = None


_EVENT_LINES = {"Pain", "Pain2", "HighDamp", "LowDamp", "Keep", "Start", "Stop", "Winding"}
_PREFIX_RE = re.compile(r"^(ACK:|SEQ:|POS:|SPEED:|DIST:|PULL:|ENC:|PINS:|ERROR:|REWIND_)", re.IGNORECASE)


def is_protocol_line(text: str) -> bool:
    """Return True for clean MCU protocol lines and ignore debug logs."""
    line = text.strip()
    if not line:
        return False
    if line in _EVENT_LINES:
        return True
    return bool(_PREFIX_RE.match(line))


def list_serial_ports() -> List[str]:
    """List available serial port device names, for example COM6 on Windows."""
    if list_ports is None:
        return []
    return [port.device for port in list_ports.comports()]


class SerialHardwareListener(QThread):
    """Read line-based MCU telemetry from a USB serial port."""

    message_received = Signal(str)
    connection_changed = Signal(bool, str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.stop_flag = False
        self.ready = False
        self.last_error = ""
        self._serial = None

    def run(self):
        if serial is None:
            self.last_error = f"pyserial unavailable: {SERIAL_IMPORT_ERROR}"
            self.connection_changed.emit(False, self.last_error)
            return

        try:
            self._serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0.2,
                write_timeout=0.5,
            )
            # Some CH340/ESP8266 boards are held in reset or bootloader mode
            # when pyserial leaves DTR/RTS asserted. Release both lines so the
            # firmware runs normally after the COM port is opened.
            try:
                self._serial.dtr = False
                self._serial.rts = False
            except Exception:
                pass
            # Many ESP8266 boards reset when the port opens. Give firmware a
            # short moment to boot before Start is sent by the training screen.
            time.sleep(1.2)
            self.ready = True
            self.connection_changed.emit(True, f"{self.port} @ {self.baudrate}")

            while not self.stop_flag:
                try:
                    raw = self._serial.readline()
                except Exception as exc:
                    if self.stop_flag:
                        break
                    self.last_error = str(exc)
                    self.connection_changed.emit(False, self.last_error)
                    break
                if not raw:
                    continue
                text = raw.decode("utf-8", errors="replace").strip()
                if is_protocol_line(text):
                    self.message_received.emit(text)
        except Exception as exc:
            self.last_error = str(exc)
            self.connection_changed.emit(False, self.last_error)
        finally:
            self.ready = False
            try:
                if self._serial and self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None
            if not self.stop_flag:
                self.connection_changed.emit(False, "Serial disconnected")

    def stop(self):
        self.stop_flag = True
        try:
            if self._serial:
                self._serial.cancel_read()
        except Exception:
            pass

    def send_message(self, msg: str) -> bool:
        try:
            if not self.ready or not self._serial or not self._serial.is_open:
                return False
            payload = (msg.strip() + "\n").encode("utf-8")
            self._serial.write(payload)
            self._serial.flush()
            return True
        except Exception as exc:
            self.last_error = str(exc)
            self.connection_changed.emit(False, self.last_error)
            return False


class SerialConnectionTestThread(QThread):
    """Background serial connection probe used by the UI."""

    connection_result = Signal(bool, str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate

    def run(self):
        if serial is None:
            self.connection_result.emit(False, f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
            return
        try:
            with serial.Serial(self.port, self.baudrate, timeout=0.4, write_timeout=0.5) as ser:
                try:
                    ser.dtr = False
                    ser.rts = False
                except Exception:
                    pass
                time.sleep(1.0)
                if probe_serial_connection(ser):
                    self.connection_result.emit(True, f"Serial connected on {self.port}: ACK: HELLO_PC")
                else:
                    self.connection_result.emit(False, f"Serial port {self.port} opened, but MCU handshake timed out")
        except Exception as exc:
            self.connection_result.emit(False, f"Serial connection failed on {self.port}: {exc}")
