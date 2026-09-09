import json,time,serial
from pathlib import Path
from datetime import datetime
from check_blood_light import exchange
p=serial.Serial(port=None,baudrate=115200,timeout=.15,write_timeout=1)
p.dtr=False;p.rts=False;p.port='COM4'
folder=Path(__file__).resolve().parent/'encoder_logs';folder.mkdir(exist_ok=True)
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
result=folder/('range_'+stamp+'.json')
with p, (folder/('range_'+stamp+'.txt')).open('w',encoding='utf-8') as log:
 exchange(p,'HELLO_PC',lambda s:s=='ACK: HELLO_PC')
 exchange(p,'ZERO',lambda s:s=='ACK: ZERO')
 print('ZERO SET; CAPTURING 120 SECONDS',flush=True)
 peak=0;minimum=0;last=0;count=0;start=time.monotonic();report=start
 while time.monotonic()-start<120:
  p.write(b'ENC?\n');deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   line=p.readline().decode('utf-8',errors='replace').strip()
   if line.startswith('ENC:'):break
  else:raise RuntimeError('ENC timeout; calibration incomplete')
  fields=dict(x.split('=',1) for x in line[4:].split(','));last=int(fields['ticks']);peak=max(peak,last);minimum=min(minimum,last);count+=1
  log.write(str(round(time.monotonic()-start,3))+' '+line+'\n');log.flush()
  state=dict(schema_version=1,created_at=stamp,zero='user_selected_position',max_ticks=peak,min_ticks=minimum,last_ticks=last,samples=count,complete=False,distance_per_tick_m_unverified=0.0000507)
  result.write_text(json.dumps(state,indent=2),encoding='utf-8')
  if time.monotonic()-report>=5:print(f'elapsed={time.monotonic()-start:.0f}s ticks={last} peak={peak} min={minimum}',flush=True);report=time.monotonic()
  time.sleep(.05)
 state['complete']=True;result.write_text(json.dumps(state,indent=2),encoding='utf-8');print('RESULT '+str(result)+' '+json.dumps(state),flush=True)
