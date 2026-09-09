"""Read isolated encoder firmware without actuator commands."""
import argparse
from datetime import datetime
from pathlib import Path
import time
import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM4')
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--zero', action='store_true')
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error('seconds must be within (0, 3600]')
    port = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    port.dtr = False
    port.rts = False
    port.port = args.port
    folder = Path(__file__).resolve().parent / 'encoder_logs'
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.txt')
    with port, path.open('w', encoding='utf-8') as log:
        def receive():
            line = port.readline().decode('utf-8', errors='replace').strip()
            if line:
                print(line, flush=True)
                log.write(datetime.now().isoformat(timespec='milliseconds') + ' ' + line + '\n')
                log.flush()
            return line

        time.sleep(1)
        deadline = time.monotonic() + 5
        verified = False
        while time.monotonic() < deadline:
            port.write(b'HELLO_PC\n')
            if receive() == 'ACK: ENCODER_ONLY':
                verified = True
                break
        if not verified:
            raise SystemExit('Encoder-only firmware not detected; no test commands sent.')
        if args.zero:
            port.write(b'ZERO\n')
        port.write(b'STREAM:ON\n')
        samples = 0
        try:
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                if receive().startswith('ENC:'):
                    samples += 1
        finally:
            port.write(b'STREAM:OFF\n')
        print(f'Log: {path}')
        if not samples:
            raise SystemExit('No encoder samples received.')


if __name__ == '__main__':
    main()
