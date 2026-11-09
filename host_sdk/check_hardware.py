"""Read-only live checks for protocol 8. No actuator start commands."""
import argparse
import json
import time
from surgerybox_v3 import SurgeryBox


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM4')
    parser.add_argument('--actuator-power-isolated',action='store_true',required=True)
    args=parser.parse_args()
    with SurgeryBox(args.port) as box:
        print('IDENTITY '+json.dumps(box.identity,ensure_ascii=False),flush=True)
        last=None
        for _ in range(25):
            last=box.status()
            m,b,l=last['MOTORPROBE'],last['BRAKE'],last['LIGHT']
            assert m['home_valid']==m['home_captured']==1,last
            assert m['home_source']=='power_on' and m['deadzone_ticks']==0 and m['extension_limit']==0,last
            assert m['active']==m['holding']==m['releasing']==m['D7']==m['D8']==0,last
            assert not last['JOB']['preparing'] and not b['enabled'] and not l['D3'],last
            assert last['I2CENC']['valid']==last['I2CENC']['relative_valid']==1,last
            assert last['SYSTEM']['dropped_frames']==0,last
            time.sleep(.1)
        print('LAST '+json.dumps(last,ensure_ascii=False),flush=True)
        print('INFO '+json.dumps(box.info(),ensure_ascii=False),flush=True)
    print('PASS: 25 read-only snapshots, boot home valid, outputs off. No actuator start commands.',flush=True)


if __name__=='__main__':main()
