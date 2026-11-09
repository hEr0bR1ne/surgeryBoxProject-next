"""SurgeryBox V3 USB API v1. Python 3.10+, pip install pyserial.

Only this object may own the COM port. No GUI dependency and no auto-reconnect.
Responses and asynchronous telemetry are separated by request id + boot session.
"""
from __future__ import annotations
import argparse
import json
import queue
import secrets
import threading
import time


class HardwareError(RuntimeError):
    pass


def parse_payload(line: str) -> dict:
    kind, _, payload = line.partition(':')
    result = {'type': kind}
    for part in payload.split(','):
        key, sep, value = part.partition('=')
        if not sep:
            continue
        try:
            parsed = int(value)
        except ValueError:
            try:
                parsed = float(value)
            except ValueError:
                parsed = value
        result[key] = parsed
    return result


class SurgeryBox:
    """Thread-safe serialized calls; reader and heartbeat run independently.

    Construction only identifies firmware. It never zeros, marks endpoints,
    enables the servo, lights the lamp or starts a motor. close() sends SAFE.
    """
    def __init__(self, port='COM4', *, timeout=2.0, serial_factory=None):
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self.timeout = timeout
        self.boot = None
        self.identity = None
        self.fatal = None
        self.uncertain = False
        self._token = None
        self._next_id = secrets.randbelow(1000000000)+1
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._pending = None
        self._stop = threading.Event()
        self.events = queue.Queue(maxsize=128)
        self.serial = serial_factory(port=None, baudrate=115200, timeout=.05, write_timeout=.3)
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.port = port
        self.serial.open()
        self._reader = threading.Thread(target=self._read_loop, name='surgerybox-rx', daemon=True)
        self._heartbeat = threading.Thread(target=self._heartbeat_loop, name='surgerybox-heartbeat', daemon=True)
        self._reader.start()
        self._heartbeat.start()
        try:
            hello = self.request('HELLO')
            self.identity = next(parse_payload(s) for s in hello if s.startswith('HELLO:'))
            if self.identity.get('product') != 'SurgeryBoxV3' or self.identity.get('api') != 1 or self.identity.get('protocol') != 8:
                raise HardwareError('Incompatible firmware: use firmware/v3, not an old tuner or main program')
            self.boot = str(self.identity['boot'])
        except Exception:
            self.close()
            raise

    def _write(self, line):
        with self._write_lock:
            payload = (line+'\n').encode('ascii')
            if self.serial.write(payload) != len(payload):
                raise HardwareError('Short serial write; operation was not retried')

    def _read_loop(self):
        buffer = bytearray()
        try:
            while not self._stop.is_set():
                raw = self.serial.readline()
                if not raw:
                    continue
                # pyserial.readline may return a partial frame at its timeout.
                # Keep bytes until LF instead of dropping an incomplete prefix.
                buffer.extend(raw)
                if len(buffer)>16384:
                    raise HardwareError('Serial frame exceeded 16384 bytes')
                while b'\n' in buffer:
                    line, _, buffer = buffer.partition(b'\n')
                    self._accept_line(line.decode('utf-8', errors='replace').strip())
        except Exception as exc:
            if not self._stop.is_set():
                self.fatal = HardwareError(f'Serial disconnected: {exc}')

    def _accept_line(self, line):
        parts = line.split(' ', 2)
        if len(parts) != 3 or not (parts[0] == '!' or parts[0].startswith('@')):
            return  # ESP8266 boot ROM bytes or unrelated diagnostic firmware.
        marker, boot, payload = parts
        if self.boot and boot != self.boot:
            self._token = None
            self.fatal = HardwareError('MCU restarted; power-on home changed, reconnect explicitly')
            return
        if marker == '!':
            event = {**parse_payload(payload), 'boot': boot, 'raw': payload}
            try:
                self.events.put_nowait(event)
            except queue.Full:
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    pass
                self.events.put_nowait(event)
            return
        try:
            response_id = int(marker[1:])
        except ValueError:
            return
        pending = self._pending
        if pending and response_id == pending[0]:
            pending[1].put((boot, payload))

    def _heartbeat_loop(self):
        while not self._stop.wait(.075):
            if not self.boot or self.fatal:
                continue
            try:
                self._write(f'~{self.boot} PING')
                token = self._token
                if token is not None:
                    self._write(f'~{self.boot} KEEP:{token}')
            except Exception as exc:
                self.fatal = HardwareError(f'Heartbeat failed: {exc}')

    def request(self, command: str, *, timeout=None) -> list[str]:
        """One tagged exchange. No automatic retry, especially for motion."""
        timeout = self.timeout if timeout is None else timeout
        if self.fatal:
            raise self.fatal
        safe_or_query = command.endswith('?') or command in ('HELLO','STOP','SAFE','LIGHT:OFF','BRAKE:OFF')
        if self.uncertain and not safe_or_query:
            raise HardwareError('Previous command completion unknown; STOP or SAFE and query state first')
        if '\n' in command or '\r' in command or not command.isascii():
            raise ValueError('Command must be one ASCII line')
        if not self._request_lock.acquire(timeout=timeout):
            raise HardwareError('Another request is pending')
        try:
            self._next_id = self._next_id % 2147483647 + 1
            response_id = self._next_id
            replies = queue.Queue()
            self._pending = (response_id, replies)
            try:
                self._write(f'@{response_id} {self.boot or "-"} {command}')
            except Exception:
                self.uncertain = True
                raise
            deadline = time.monotonic()+timeout
            lines = []
            while time.monotonic() < deadline:
                if self.fatal:
                    raise self.fatal
                try:
                    _, payload = replies.get(timeout=min(.05, max(.001, deadline-time.monotonic())))
                except queue.Empty:
                    continue
                if payload == 'END:OK':
                    if command in ('STOP','SAFE'):
                        self.uncertain = False
                    return lines
                if payload == 'END:ERROR':
                    raise HardwareError('; '.join(lines) or 'MCU rejected command')
                lines.append(payload)
            self.uncertain = True
            raise HardwareError(f'No complete reply to {command}; not retried. Query state or STOP before continuing')
        finally:
            self._pending = None
            self._request_lock.release()

    def _records(self, command):
        return {record['type']: record for record in map(parse_payload, self.request(command))}

    def status(self):
        return self._records('STATUS?')

    def info(self):
        return self._records('INFO?')

    def position(self):
        value = self._records('ENC?')['I2CENC']
        valid = value.get('valid') == value.get('relative_valid') == 1
        ticks = value['relative_ticks'] if valid else None
        return {**value, 'relative_ticks': ticks, 'relative_turns': ticks/16384 if valid else None,
                'relative_degrees': ticks*360/16384 if valid else None}

    def zero(self):
        return self._records('ZERO')

    def set_light(self, on: bool):
        if not isinstance(on, bool):
            raise TypeError('on must be bool')
        return self._records('LIGHT:ON' if on else 'LIGHT:OFF')

    def set_brake(self, mode: str):
        if mode not in ('release', 'weak', 'lock', 'off'):
            raise ValueError('Brake mode: release, weak, lock, off')
        return self._records('BRAKE:'+mode.upper())

    def set_brake_angle(self, angle: int):
        if isinstance(angle, bool) or not isinstance(angle, int) or not 50 <= angle <= 180:
            raise ValueError('Angle must be integer 50..180; firmware also limits each step to 5 degrees')
        return self._records('BRAKE:ANGLE:'+str(angle))

    def mark_endpoint(self, endpoint: str, *, motor_power_isolated: bool):
        raise ValueError('Manual endpoints removed: firmware 3.1 captures the power-on position as home')

    def clear_endpoints(self):
        raise ValueError('Power-on home cannot be cleared or moved by the host; restart to capture a new home')

    def stream(self, enabled: bool):
        return self._records('STREAM:ON' if enabled else 'STREAM:OFF')

    def _start(self, kind):
        if self._token is not None:
            raise HardwareError('A motor job is still owned by this client; wait or STOP it first')
        token = secrets.randbelow(2147483646)+1
        self._token = token
        try:
            self.request(f'MOTOR:{kind}:{token}')
        except Exception:
            self._token = None  # Do not extend an unconfirmed command's lease.
            raise
        return token

    def wind(self):
        """Rewind to this boot's home, without a deadzone or extension limit, then release 1s."""
        return self._start('WIND')

    def release(self):
        """Release the friction wheel for 1 second; encoder motion is not required."""
        return self._start('RELEASE')

    def finish(self):
        """Normally end an owned rewind early, including the 1-second release."""
        if self._token is None:
            raise HardwareError('No owned motor job')
        return self._records('MOTOR:FINISH:'+str(self._token))

    def wait_motor(self, *, timeout=130.0):
        token = self._token
        if token is None:
            raise HardwareError('No owned motor job')
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            data = self._records('MOTOR?')
            motor, job = data['MOTORPROBE'], data['JOB']
            if not job['preparing'] and not motor['active'] and motor['id']==token:
                self._token = None
                if motor['reason'] != 'release_complete':
                    raise HardwareError('Motor stopped without successful completion: '+str(motor['reason']))
                return motor
            time.sleep(.1)
        self.stop()
        raise HardwareError('Motor wait timed out; STOP sent')

    def stop(self):
        self._token = None
        self._write('MS')  # Immediate stop does not wait for the request lock.
        return self._records('STOP')

    def safe_off(self):
        self._token = None
        self._write('SAFE')
        return self._records('SAFE')

    def next_event(self, timeout=0.0):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        if self._stop.is_set():
            return
        self._token = None
        try:
            self._write('SAFE')
            if self.boot and not self.fatal:
                self.request('SAFE', timeout=.6)
        except Exception:
            pass
        self._stop.set()
        self._heartbeat.join(timeout=.5)
        try:
            self.serial.cancel_read()
        except Exception:
            pass
        self._reader.join(timeout=.5)
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM4')
    parser.add_argument('command', nargs='?', default='status', choices=('status','info','position','light-on','light-off','brake-release','brake-weak','brake-lock','brake-off','zero','stop','safe','wind','release'))
    parser.add_argument('--hold-seconds', type=float, default=2, help='Keep light/servo command active before SAFE on exit')
    args = parser.parse_args()
    with SurgeryBox(args.port) as box:
        cmd = args.command
        if cmd in ('wind','release'):
            token = box.wind() if cmd=='wind' else box.release()
            print('accepted token=',token,flush=True)
            result = box.wait_motor()
        elif cmd.startswith('light-'):
            result=box.set_light(cmd=='light-on'); print(json.dumps(result,ensure_ascii=False),flush=True)
            time.sleep(max(0,args.hold_seconds))
        elif cmd.startswith('brake-'):
            result=box.set_brake(cmd[6:]); print(json.dumps(result,ensure_ascii=False),flush=True)
            time.sleep(max(0,args.hold_seconds))
        else:
            result = {'safe': box.safe_off}.get(cmd, getattr(box,cmd,None))()
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
