import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
try:
    from PySide6.QtCore import QCoreApplication, QObject
    from app.ui.blood_light_training import BloodLightTrainingMixin
except ImportError:
    QCoreApplication = None
else:
    class Screen(BloodLightTrainingMixin, QObject):
        def __init__(self):
            super().__init__()
            self.connected = False
            self.sent = []
            self.text_display = Mock()
            self._start_hardware_listener = Mock()

        def _hardware_ready(self):
            return self.connected

        def _send_hardware_message(self, command):
            self.sent.append(command)
            return True


@unittest.skipIf(QCoreApplication is None, "PySide6 not installed")
class BloodLightQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_ready_after_stage_entry_and_cleanup(self):
        with patch.dict(os.environ, {"SURGERYBOX_BLOOD_LIGHT": "1"}):
            screen = Screen()
            try:
                screen._set_blood_light(True)
                screen._start_hardware_listener.assert_called_once()
                self.assertEqual(screen.sent, [])
                screen.connected = True
                screen._blood_light_timer.timeout.emit()
                self.assertEqual(screen.sent, ["LIGHT:ON"])
                self.assertTrue(screen._receive_blood_light("LIGHT:ON"))
                self.assertFalse(screen._blood_light.pending)
                screen._close_blood_light()
                screen._blood_light_timer.timeout.emit()
                self.assertEqual(screen.sent, ["LIGHT:ON", "LIGHT:OFF"])
                self.assertFalse(screen._blood_light_timer.isActive())
            finally:
                screen._close_blood_light()

    def test_virtual_mode_does_not_open_a_transport(self):
        with patch.dict(os.environ, {"SURGERYBOX_BLOOD_LIGHT": "0"}):
            screen = Screen()
            screen._set_blood_light(True)
            screen._close_blood_light()
            screen._start_hardware_listener.assert_not_called()
            self.assertEqual(screen.sent, [])


if __name__ == "__main__":
    unittest.main()
