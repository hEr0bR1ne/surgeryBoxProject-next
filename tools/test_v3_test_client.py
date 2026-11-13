import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
import time
import unittest
from PySide6.QtCore import QObject, QEvent, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from v3_test_client import TestConsole

app=QApplication.instance() or QApplication([])

class FakeBackend(QObject):
    connected=Signal(object);disconnected=Signal(str);state=Signal(object)
    done=Signal(str,object);failed=Signal(str);wire=Signal(str)
    def __init__(self):super().__init__();self.calls=[]
    def submit(self,*args):self.calls.append(args)
    def emergency(self,all_outputs=True):self.calls.append(('emergency',all_outputs))
    def disconnect(self):self.calls.append(('disconnect',))
    def close(self):self.calls.append(('close',))

def state():
    return {'I2CENC':{'valid':1,'relative_valid':1,'relative_ticks':123,'age_ms':5,'angle_deg':10,'addr':'0x06','errors':0},
        'BRAKE':{'enabled':0,'angle':180},'LIGHT':{'state':'OFF','D3':0},
        'MOTORPROBE':{'home':0,'home_valid':1,'pos':-5000,'active':0,'releasing':0,'reason':'safe_off'},
        'JOB':{'preparing':0,'kind':'idle','token':0}}

class GuiTests(unittest.TestCase):
    def setUp(self):
        self.backend=FakeBackend();self.w=TestConsole(backend=self.backend);self.w.timer.stop()
        self.w.on_connected({'boot':'test-session'});self.data=state();self.w.on_state(self.data)
    def tearDown(self):self.w.close()
    def test_connect_and_state_never_trigger_actions(self):self.assertEqual(self.backend.calls,[])
    def test_rewind_position_is_separate_from_display_zero(self):
        data = state()
        data['MOTORPROBE'].update(pos=-13763, home=0)
        data['I2CENC']['relative_ticks'] = 11092
        self.w.on_state(data)
        self.assertIn('-13763', self.w.position.text())
        self.assertIn('+11092', self.w.display_position.text())
    def test_set_home_button_sends_explicit_command_only_when_supported(self):
        self.w.zero.click()
        self.assertEqual(self.backend.calls, [])
        data = state()
        data['MOTORPROBE']['home_settable'] = 1
        self.w.on_state(data)
        self.w.zero.click()
        self.assertEqual(self.backend.calls, [('set_home',)])
    def test_ramping_status_distinguishes_command_from_target(self):
        data=state();data['BRAKE'].update(enabled=1,angle=160,target=120,moving=1,settled=0)
        self.w.on_state(data)
        self.assertIn('160° → 目标 120°',self.w.brake_status.text())
        self.assertIn('缓动中',self.w.brake_status.text());self.assertEqual(self.backend.calls,[])
    def test_motor_needs_power_confirmation_and_valid_home(self):
        self.assertFalse(self.w.wind.isEnabled());self.w.powered.setChecked(True);self.assertTrue(self.w.wind.isEnabled())
        data=state();data['MOTORPROBE']['home_valid']=0;self.w.on_state(data);self.w.act('wind')
        self.assertFalse(self.w.wind.isEnabled());self.assertEqual(self.backend.calls,[])
    def test_far_pull_never_disables_rewind(self):
        self.w.powered.setChecked(True);data=state();data['MOTORPROBE']['pos']=-1000000
        self.w.on_state(data);self.w.act('wind');self.assertEqual(self.backend.calls,[('wind',)])
    def test_no_manual_endpoint_widgets_or_minimum_pull_gate(self):
        self.assertFalse(hasattr(self.w,'mark_a'));self.w.powered.setChecked(True)
        data=state();data['MOTORPROBE']['pos']=-1;self.w.on_state(data)
        self.assertTrue(self.w.wind.isEnabled());self.assertIn('无提前停车死区',self.w.travel.text())
    def test_stale_state_blocks_all_motion(self):
        self.w.powered.setChecked(True);self.w.last_state=time.monotonic()-2;self.w.controls();self.w.act('wind')
        self.assertFalse(self.w.wind.isEnabled());self.assertEqual(self.backend.calls,[])
    def test_emergency_remains_available_during_pending_command(self):
        self.w.powered.setChecked(True);self.w.act('wind');self.assertTrue(self.w.safe_button.isEnabled())
        self.w.emergency(True);self.assertEqual(self.backend.calls[-1],('emergency',True));self.assertTrue(self.w.pending)
        self.assertFalse(self.w.wind.isEnabled())
    def test_repeat_click_does_not_queue_more_actions(self):
        self.w.powered.setChecked(True);self.w.act('wind');self.w.act('wind');self.assertEqual(self.backend.calls,[('wind',)])
    def test_late_action_result_does_not_unlock_emergency_pending(self):
        self.w.emergency(True);self.w.on_done('refresh',{})
        self.assertTrue(self.w.pending)
        self.w.on_done('safe',{});self.assertFalse(self.w.pending)
    def test_uncertain_command_blocks_new_motion_until_stop(self):
        data=state();data['CLIENT']={'uncertain':True};self.w.on_state(data);self.w.powered.setChecked(True)
        self.assertFalse(self.w.wind.isEnabled());self.assertFalse(self.w.light_on.isEnabled());self.assertTrue(self.w.safe_button.isEnabled())
    def test_disconnect_discards_power_confirmation_and_live_position(self):
        self.w.powered.setChecked(True);self.w.on_disconnected('断开');self.assertFalse(self.w.powered.isChecked())
        self.assertFalse(self.w.wind.isEnabled());self.assertIn('未连接',self.w.position.text())
    def test_window_deactivation_cancels_pending_motor_start(self):
        self.w.powered.setChecked(True);self.w.act('wind')
        app.sendEvent(self.w,QEvent(QEvent.WindowDeactivate))
        self.assertIn(('emergency',True),self.backend.calls)
    def test_space_on_focused_wind_button_is_emergency_not_start(self):
        self.w.powered.setChecked(True);self.w.show();self.w.activateWindow();self.w.wind.setFocus();app.processEvents()
        QTest.keyClick(self.w.wind,Qt.Key_Space);app.processEvents()
        self.assertIn(('emergency',True),self.backend.calls);self.assertNotIn(('wind',),self.backend.calls)

if __name__=='__main__':unittest.main()
