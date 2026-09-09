import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
from app.hardware.blood_light import BloodLightController


class BloodLightTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.connected = False
        self.sent = []
        self.errors = []
        self.controller = BloodLightController(
            lambda cmd: self.sent.append(cmd) or True,
            lambda: self.connected, self.errors.append, lambda: self.now)

    def test_waits_for_transport_then_retries_until_matching_reply(self):
        self.controller.set(True)
        self.assertEqual(self.sent, [])
        self.connected = True
        self.controller.poll()
        self.controller.receive("ACK: Start")
        self.controller.receive("LIGHT:OFF")
        self.now = 1
        self.controller.poll()
        self.assertEqual(self.sent, ["LIGHT:ON", "LIGHT:ON"])
        self.controller.receive("LIGHT:ON")
        self.now = 2
        self.controller.poll()
        self.assertEqual(len(self.sent), 2)

    def test_success_turns_off_and_ignores_late_on_reply(self):
        self.connected = True
        self.controller.set(True)
        self.controller.set(False)
        self.controller.receive("LIGHT:ON")
        self.assertTrue(self.controller.pending)
        self.controller.receive("LIGHT:OFF")
        self.assertFalse(self.controller.pending)
        self.assertEqual(self.sent, ["LIGHT:ON", "LIGHT:OFF"])

    def test_cleanup_before_connection_cancels_pending_on(self):
        self.controller.set(True)
        self.controller.close()
        self.connected = True
        self.controller.poll()
        self.controller.set(True)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.errors), 1)

    def test_cleanup_sends_off_once_and_never_reopens(self):
        self.connected = True
        self.controller.set(True)
        self.controller.close()
        self.controller.close()
        self.controller.set(True)
        self.assertEqual(self.sent, ["LIGHT:ON", "LIGHT:OFF"])

    def test_connection_timeout_reports_failure(self):
        self.controller.set(True)
        self.now = 10
        self.controller.poll()
        self.controller.poll()
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(self.controller.pending)


if __name__ == "__main__":
    unittest.main()
