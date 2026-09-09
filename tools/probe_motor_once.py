"""One bounded, user-authorized direction probe; never starts a full rewind."""
import argparse,json,time,serial
from pathlib import Path
from datetime import datetime
from check_blood_light import exchange

def fields(line):
    return dict(part.split('=',1) for part in line[len('TRAVEL:'):].split(','))

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--direction',choices=['F','R'],required=True)
parser.add_argument('--expected-pwm',type=int,choices=range(300,701),default=300)
args=parser.parse_args()
command=f'MOTOR:PROBE:{args.direction}'
p=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
p.dtr=False;p.rts=False;p.port='COM4'
folder=Path(__file__).resolve().parent/'encoder_logs';folder.mkdir(exist_ok=True)
path=folder/('probe_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
records=[]
with p:
    exchange(p,'HELLO_PC',lambda s:s=='ACK: HELLO_PC')
    snapshots=[]
    for _ in range(3):
        state=fields(exchange(p,'TRAVEL?',lambda s:s.startswith('TRAVEL:home=')))
        assert state['home']=='1' and state['active']=='0',state
        assert state.get('pwm')==str(args.expected_pwm),'Unexpected PWM; probe not sent'
        assert 14000<=int(state['pos'])<=20000,state
        snapshots.append(int(state['pos']))
        time.sleep(.5)
    assert max(snapshots)-min(snapshots)<=2,'Position still moving; probe not sent'
    start=time.monotonic()
    try:
        p.write((command+'\n').encode('ascii'));p.flush()
        while time.monotonic()-start<5:
            line=p.readline().decode(errors='replace').strip()
            if line:
                print(line,flush=True)
                records.append({'elapsed_s':round(time.monotonic()-start,4),'line':line})
            if time.monotonic()-start>.3:
                p.write(b'TRAVEL?\n')
                time.sleep(.1)
    finally:
        exchange(p,'MS',lambda s:s=='ACK: MotorStop')
    final=fields(exchange(p,'TRAVEL?',lambda s:s.startswith('TRAVEL:home=')))
    pins=exchange(p,'PINS?',lambda s:s.startswith('PINS:'))
    assert final['active']=='0' and 'D7=0' in pins.split(',') and 'D8=0' in pins.split(',')
    path.write_text(json.dumps({'command':command,'initial_ticks':snapshots[-1],'final':final,'records':records},indent=2),encoding='utf-8')
    print('LOG:',path)
