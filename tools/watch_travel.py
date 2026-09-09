import serial,time
p=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1)
p.dtr=False;p.rts=False;p.port='COM4'
with p:
 end=time.monotonic()+45
 stable_since=None
 last_position=None
 while time.monotonic()<end:
  p.write(b'TRAVEL?\n');deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   line=p.readline().decode(errors='replace').strip()
   if line.startswith('TRAVEL:home='):
    print(line,flush=True)
    state=dict(part.split('=',1) for part in line[7:].split(','))
    position=int(state['pos'])
    if state['home']=='1' and state['active']=='0' and 14000<=position<=20000:
     if last_position != position:stable_since=time.monotonic()
     elif stable_since is not None and time.monotonic()-stable_since>=3:
      print('STABLE MIDDLE: '+str(position),flush=True)
      end=0
    else:stable_since=None
    last_position=position
    break
  else:raise RuntimeError('No travel status')
  time.sleep(1)
