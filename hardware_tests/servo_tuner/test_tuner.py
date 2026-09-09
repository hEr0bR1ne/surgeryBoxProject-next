import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from servo_tuner import ServoTuner, parse_state


class TunerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ServoTuner()
        self.window.timer.stop()
        self.window.send = Mock(return_value=True)

    def tearDown(self):
        self.window.close()

    def test_protocol_rejects_invalid_or_wrong_firmware(self):
        for line in ("STATE:1,181,90", "STATE:2,90,90", "STATE:x,90,90", "BRAKE:ANGLE:90"):
            self.assertIsNone(parse_state(line))
        self.window.handle_line("ACK: SERVO_ONLY")
        self.window.send_angle()
        self.window.send.assert_not_called()

    def test_slider_does_not_move_until_send(self):
        self.window.handle_line("TUNER:1")
        self.window.slider.setValue(130)
        self.window.send.assert_not_called()
        self.window.send_angle()
        self.window.send.assert_called_once_with("SET:130")

    def test_step_uses_returned_target_and_clamps(self):
        self.window.handle_line("TUNER:1")
        self.window.handle_line("STATE:1,100,175")
        self.window.step(10)
        self.window.send.assert_called_once_with("SET:180")

    def test_records_require_settled_enabled_state(self):
        self.window.handle_line("TUNER:1")
        self.window.handle_line("STATE:1,95,120")
        self.window.record("weak")
        self.assertEqual(self.window.records, {})
        self.window.handle_line("STATE:1,120,120")
        self.window.record("weak")
        self.assertEqual(self.window.records, {"weak": 120})
        self.window.handle_line("STATE:0,120,120")
        self.window.record("lock")
        self.assertNotIn("lock", self.window.records)

    def test_disconnect_clears_stale_angle(self):
        self.window.handle_line("TUNER:1")
        self.window.handle_line("STATE:1,100,100")
        self.window.disconnect()
        self.assertFalse(self.window.verified)
        self.assertIsNone(self.window.state)
        self.assertFalse(self.window.send_button.isEnabled())

    def test_new_command_cannot_record_previous_angle(self):
        self.window.handle_line("TUNER:1")
        self.window.handle_line("STATE:1,90,90")
        self.window.angle.setValue(120)
        self.window.send_angle()
        self.window.record("weak")
        self.assertEqual(self.window.records, {})
        self.window.handle_line("STATE:1,120,120")
        self.window.record("weak")
        self.assertEqual(self.window.records, {"weak": 120})

    def test_export_uses_recorded_angles(self):
        import json
        import tempfile
        from pathlib import Path
        self.window.records = {"release": 70, "weak": 95, "lock": 110}
        with tempfile.TemporaryDirectory() as folder:
            destination = str(Path(folder) / "angles.json")
            with patch("servo_tuner.QFileDialog.getSaveFileName", return_value=(destination, "JSON")):
                self.window.export_records()
            result = json.loads(Path(destination).read_text(encoding="utf-8"))
        self.assertEqual(result["angles_deg"], self.window.records)
        self.assertEqual(result["gpio"], 16)
        self.assertEqual(result["measurement"], "commanded_not_measured")


if __name__ == "__main__":
    unittest.main()
