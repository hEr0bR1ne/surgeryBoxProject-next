import queue
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from surgerybox_v3 import SurgeryBox, HardwareError


class SerialEmulator:
    """Protocol peer for client correlation, watchdog and retry regression tests."""
    def __init__(self, **kwargs):
        self.rx=queue.Queue(); self.writes=[]; self.port=None
        self.boot='abc-session'; self.light=0; self.drop=None; self.token=0
        self.motor_reason='release_complete'; self.closed=False
        self.fragment=False
        self.protocol=8
    def open(self): pass
    def close(self): self.closed=True
    def cancel_read(self): self.rx.put(b'')
    def readline(self):
        try:return self.rx.get(timeout=.02)
        except queue.Empty:return b''
    def emit(self, marker, payload, boot=None):
        frame=f'{marker} {boot or self.boot} {payload}\n'.encode()
        if self.fragment:
            cut=len(frame)//2; self.rx.put(frame[:cut]); self.rx.put(frame[cut:])
        else:self.rx.put(frame)
    def write(self,data):
        line=data.decode().strip(); self.writes.append(line)
        if not line.startswith('@'):return len(data)
        marker,session,cmd=line.split(' ',2)
        if cmd==self.drop:return len(data)
        if cmd=='HELLO':self.emit(marker,f'HELLO:product=SurgeryBoxV3,api=1,protocol={self.protocol},boot={self.boot}')
        elif cmd=='ENC?':
            self.emit('@999999999','I2CENC:relative_ticks=999999')
            self.emit('!','I2CENC:valid=1,relative_valid=1,relative_ticks=16384')
            self.emit(marker,'I2CENC:valid=1,relative_valid=1,relative_ticks=-8192')
        elif cmd.startswith('MOTOR:WIND:') or cmd.startswith('MOTOR:RELEASE:'):
            self.token=int(cmd.rsplit(':',1)[1]); self.emit(marker,'ACCEPTED:token='+str(self.token))
        elif cmd=='MOTOR?':
            self.emit(marker,f'MOTORPROBE:active=0,id={self.token},reason={self.motor_reason}')
            self.emit(marker,'JOB:preparing=0')
        elif cmd=='LIGHT:ON':self.light=1;self.emit(marker,'LIGHT:state=ON,D3=1,gpio=5')
        elif cmd=='LIGHT:OFF':self.light=0;self.emit(marker,'LIGHT:state=OFF,D3=0,gpio=5')
        elif cmd.startswith('BAD'):
            self.emit(marker,'ERROR: rejected');self.emit(marker,'END:ERROR');return len(data)
        self.emit(marker,'END:OK')
        return len(data)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.peer=SerialEmulator()
        self.box=SurgeryBox('FAKE',serial_factory=lambda **kw:self.peer,timeout=.45)
    def tearDown(self):self.box.close()

    def commands(self):
        return [line.split(' ',2)[2] for line in self.peer.writes if line.startswith('@')]

    def test_connect_has_no_mutation_or_automatic_zero(self):
        self.assertEqual(self.commands(),['HELLO'])

    def test_ids_and_async_events_cannot_corrupt_query_result(self):
        p=self.box.position()
        self.assertEqual(p['relative_ticks'],-8192)
        self.assertEqual(p['relative_turns'],-.5)
        self.assertEqual(self.box.next_event(.1)['relative_ticks'],16384)

    def test_partial_serial_reads_are_reassembled_until_newline(self):
        self.peer.fragment=True
        self.assertEqual(self.box.position()['relative_ticks'],-8192)
        self.assertEqual(self.box.next_event(.1)['relative_ticks'],16384)

    def test_reboot_invalidates_client_without_reconnect_or_motion(self):
        self.box._accept_line('! different-boot READY:outputs=off')
        with self.assertRaisesRegex(HardwareError,'restarted'):self.box.set_light(True)
        self.assertNotIn('LIGHT:ON',self.commands())

    def test_heartbeat_keeps_running_during_a_slow_query(self):
        self.peer.drop='HANG?'
        with self.assertRaises(HardwareError):self.box.request('HANG?',timeout=.3)
        self.assertGreaterEqual(sum(' PING' in s for s in self.peer.writes),2)

    def test_timeout_does_not_retry_motion_or_allow_next_mutation(self):
        self.peer.drop='LOST'
        with self.assertRaises(HardwareError):self.box.request('LOST',timeout=.12)
        with self.assertRaisesRegex(HardwareError,'unknown'):self.box.set_light(True)
        self.assertEqual(self.commands().count('LOST'),1)
        self.box.stop()
        self.box.set_light(True)
        self.assertEqual(self.peer.light,1)

    def test_rejection_is_error_not_success_and_has_no_retry(self):
        with self.assertRaisesRegex(HardwareError,'rejected'):self.box.request('BAD:COMMAND')
        self.assertEqual(self.commands().count('BAD:COMMAND'),1)
        self.assertFalse(self.box.uncertain)

    def test_motor_failure_never_reports_success(self):
        self.peer.motor_reason='no_progress'
        self.box.wind()
        with self.assertRaisesRegex(HardwareError,'no_progress'):self.box.wait_motor(timeout=1)

    def test_motor_success_requires_release_complete(self):
        token=self.box.wind()
        self.assertEqual(self.box.wait_motor(timeout=1)['id'],token)
        self.assertIsNone(self.box._token)

    def test_emergency_stop_is_written_before_tagged_reply(self):
        self.box.stop()
        self.assertIn('MS',self.peer.writes)
        self.assertLess(self.peer.writes.index('MS'),len(self.peer.writes)-1)

    def test_manual_endpoints_cannot_replace_power_on_home(self):
        with self.assertRaises(ValueError):self.box.mark_endpoint('retract',motor_power_isolated=True)
        with self.assertRaises(ValueError):self.box.clear_endpoints()
        self.assertFalse(any(s.startswith('BOUND:') for s in self.commands()))
        self.assertNotIn('BOUNDS:CLEAR',self.commands())

    def test_old_endpoint_protocol_is_rejected_without_motion(self):
        old=SerialEmulator();old.protocol=7
        with self.assertRaisesRegex(HardwareError,'Incompatible'):
            SurgeryBox('OLD',serial_factory=lambda **kw:old)
        self.assertTrue(old.closed)
        self.assertFalse(any('MOTOR:WIND:' in s for s in old.writes))

    def test_close_sends_safe_and_stops_threads(self):
        self.box.close()
        self.assertIn('SAFE',self.peer.writes)
        self.assertTrue(self.peer.closed)
        self.assertFalse(self.box._reader.is_alive())
        self.assertFalse(self.box._heartbeat.is_alive())


if __name__=='__main__':unittest.main()
