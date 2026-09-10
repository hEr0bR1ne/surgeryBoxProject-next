import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import unittest
from PySide6.QtWidgets import QApplication
from motor_tuner import MotorTuner, parse_state

app = QApplication.instance() or QApplication([])


def state(pos=17000, home=1, active=0, pwm=512, reason='home_confirmed'):
    return (f'TRAVEL:home={home},pos={pos},low=1745,high=33146,stop=1945,'
            f'direction=unknown,active={active},pwm={pwm},control=dir_pwm_v1,matrix=1,reason={reason}')


class Tests(unittest.TestCase):
    def setUp(self):
        self.w = MotorTuner(); self.w.timer.stop()
        self.sent = []
        self.w.send = lambda command: self.sent.append(command) or True
        self.w.handle_line('ACK: HELLO_PC')
        self.w.handle_line(state())

    def tearDown(self):
        self.w.stop_timer.stop(); self.w.close()

    def test_parser_rejects_echo_and_wrong_limits(self):
        self.assertIsNone(parse_state('TRAVEL:HOME'))
        self.assertIsNone(parse_state(state().replace('high=33146', 'high=99999')))
        self.assertIsNone(parse_state('TRAVEL:home=1'))

    def test_selection_does_not_run(self):
        self.w.pwm.setValue(600); self.w.duration.setValue(500)
        self.w.direction.setCurrentIndex(1)
        self.assertEqual(self.sent, [])

    def test_handoff_firmware_reports_motor_disabled(self):
        self.w.handle_line(state().replace('matrix=1', 'matrix=0,motor_enabled=0'))
        self.assertFalse(self.w.run_button.isEnabled())
        self.assertIn('电机已在固件中禁用', self.w.connection_label.text())

    def test_reverse_duration_sent_to_firmware_and_zero_motion_completes(self):
        self.w.direction.setCurrentIndex(1)
        self.w.duration.setValue(100)
        self.w.run()
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.assertEqual(self.sent[-1], 'MOTOR:MATRIX:3:100')
        self.w.handle_line(state(active=1, reason='probing'))
        self.w.handle_line(state(reason='matrix_complete'))
        self.assertEqual(self.w.history[-1]['delta_ticks'], 0)
        self.assertIsNone(self.w.run_record)

    def test_old_firmware_and_continuous_firmware_are_rejected(self):
        self.assertIsNone(parse_state(state().replace('control=dir_pwm_v1,', '')))
        self.w.handle_line('MOTOR_DIR_PWM: DIR_GPIO13=0 PWM_GPIO0=512/1023 freq=500Hz')
        self.assertFalse(self.w.run_button.isEnabled())
        self.assertIn('固件不兼容', self.w.connection_label.text())

    def test_stop_ack_before_active_status_finishes_record(self):
        self.w.run()
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.w.stop()
        self.w.handle_line(state(reason='stopped'))
        self.assertIsNone(self.w.run_record)

    def test_disabled_reason_matches_state(self):
        self.w.handle_line(state(home=0))
        self.assertIn('零点未确认', self.w.run_hint.text())
        self.assertFalse(self.w.run_button.isEnabled())
        self.w.handle_line(state(pos=500))
        self.assertIn('手动拉到', self.w.run_hint.text())
        self.w.handle_line(state(pos=25000))
        self.assertIn('手动退回', self.w.run_hint.text())
        self.w.handle_line(state())
        self.assertIn('可以运行', self.w.run_hint.text())
        self.assertTrue(self.w.run_button.isEnabled())

    def test_refuse_unreferenced_or_outside_or_stale(self):
        for s in (state(home=0), state(pos=20001), state(active=1)):
            self.w.handle_line(s); self.w.run()
        self.w.handle_line(state()); self.w.last_rx = time.monotonic() - 5; self.w.run()
        self.assertEqual(self.sent, [])

    def test_pwm_ack_then_single_probe(self):
        self.w.run()
        self.assertEqual(self.sent, ['MOTOR:PWM:512'])
        self.w.handle_line(state(reason='pwm_set_probe_required', pwm=300))
        self.assertEqual(len(self.sent), 1)
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.assertEqual(self.sent[-1], 'MOTOR:MATRIX:1:200')
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.assertEqual(self.sent.count('MOTOR:MATRIX:1:200'), 1)
        self.w.handle_line(state(active=1, reason='probing'))
        self.w.handle_line(state(pos=16850, reason='probe_complete'))
        self.assertEqual(self.w.history[-1]['delta_ticks'], -150)
        self.assertIn('observed_completion_ms', self.w.history[-1])
        self.assertIn('probe_complete', self.w.log.toPlainText())
        self.assertFalse(self.w.stop_timer.isActive())

    def test_all_nine_combinations_and_full_drive_time_cap(self):
        self.assertEqual({self.w.direction.itemData(i) for i in range(9)}, set('012345678'))
        for combo in ('2', '6'):
            self.w.direction.setCurrentIndex(self.w.direction.findData(combo))
            self.w.duration.setValue(2000)
            self.w.run()
            self.w.handle_line(state(reason='pwm_set_probe_required'))
            self.assertEqual(self.sent[-1], f'MOTOR:MATRIX:{combo}:200')
            self.w.handle_line(state(active=1, reason='probing'))
            self.w.handle_line(state(reason='matrix_complete'))
            self.assertEqual(self.w.history[-1]['combination'], int(combo))

    def test_stop_source_visible(self):
        self.w.stop('设定时间到达')
        self.assertIn('停止来源：设定时间到达', self.w.log.toPlainText())

    def test_reverse_pin_readback_records_stop_race_without_false_diagnosis(self):
        self.w.direction.setCurrentIndex(1)
        self.w.run()
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.w.handle_line(state(active=1, reason='probing'))
        self.assertEqual(self.sent[-1], 'PINS?')
        self.w.handle_line('PINS:D7=1,D8=0')
        self.assertEqual(self.w.run_record['input_pin_samples'][-1]['d7'], 1)
        self.w.handle_line('PINS:D7=0,D8=1')
        self.assertNotIn('MS', self.sent)
        self.assertEqual(self.w.run_record['input_pin_samples'][-1]['d8'], 1)

    def test_stop_cancels_late_ack(self):
        self.w.run(); self.w.stop()
        self.w.handle_line(state(reason='pwm_set_probe_required'))
        self.assertFalse(any(s.startswith('MOTOR:MATRIX:') for s in self.sent))

    def test_moving_while_applying_rejects_probe(self):
        self.w.run()
        self.w.handle_line(state(pos=17100, reason='pwm_set_probe_required'))
        self.assertFalse(any(s.startswith('MOTOR:MATRIX:') for s in self.sent))

    def test_home_requires_explicit_check(self):
        self.w.home(); self.assertEqual(self.sent, [])
        self.w.home_check.setChecked(True); self.w.home()
        self.assertEqual(self.sent, ['TRAVEL:HOME'])
        self.assertFalse(self.w.home_check.isChecked())


if __name__ == '__main__':
    unittest.main()
