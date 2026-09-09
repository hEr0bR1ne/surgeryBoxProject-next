"""Read main-firmware encoder snapshots without changing hardware state."""
import time
from datetime import datetime
from pathlib import Path
import serial
from check_blood_light import exchange


def main():
    folder = Path(__file__).resolve().parent / 'encoder_logs'
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now().strftime('main_%Y%m%d_%H%M%S') + '.txt')
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = 'COM4'
    samples = []
    with connection as port, path.open('w', encoding='utf-8') as log:
        exchange(port, 'HELLO_PC', lambda line: line == 'ACK: HELLO_PC')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            line = exchange(port, 'ENC?', lambda line: line.startswith('ENC:'))
            log.write(datetime.now().isoformat(timespec='milliseconds') + ' ' + line + '\n')
            log.flush()
            samples.append(dict(part.split('=', 1) for part in line[4:].split(',')))
            time.sleep(0.4)
    if samples:
        ticks = [int(s['ticks']) for s in samples]
        print('SUMMARY samples={}, ticks_first={}, ticks_last={}, min={}, max={}, edgeA_delta={}, edgeB_delta={}'.format(
            len(samples), ticks[0], ticks[-1], min(ticks), max(ticks),
            int(samples[-1]['edgeA']) - int(samples[0]['edgeA']),
            int(samples[-1]['edgeB']) - int(samples[0]['edgeB'])))
    print('LOG:', path)


if __name__ == '__main__':
    main()
