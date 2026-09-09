import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
from app.hardware.serial_probe import probe_serial_connection


class FakeSerial:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.operations = []

    def reset_input_buffer(self):
        self.operations.append("reset")

    def write(self, payload):
        self.operations.append(payload)

    def flush(self):
        self.operations.append("flush")

    def readline(self):
        return self.responses.pop(0) if self.responses else b""


class SerialProbeTests(unittest.TestCase):
    def probe(self, responses):
        port = FakeSerial(responses)
        ticks = iter(i * 0.1 for i in range(100))
        result = probe_serial_connection(port, timeout=1, clock=lambda: next(ticks))
        self.assertEqual(port.operations, ["reset", b"HELLO_PC\n", "flush"])
        return result

    def test_accepts_exact_reply_after_boot_noise(self):
        self.assertTrue(self.probe([b"[BOOT] Ready\n", b"POS:1\n", b"ACK: HELLO_PC\r\n"]))

    def test_silent_open_port_is_failure(self):
        self.assertFalse(self.probe([]))

    def test_unrelated_ack_and_telemetry_are_failure(self):
        self.assertFalse(self.probe([b"ACK: Start\n", b"POS:1\n", b"HELLO_PC\n"]))

    def test_debug_echo_and_binary_noise_are_failure(self):
        self.assertFalse(self.probe([b"[DEBUG] ACK: HELLO_PC\n", b"\xff\xfeACK: HELLO_PC\n"]))

    def test_read_failure_propagates_to_connection_thread(self):
        port = FakeSerial()
        def disconnected():
            raise OSError("Device disconnected")
        port.readline = disconnected
        with self.assertRaises(OSError):
            probe_serial_connection(port)


if __name__ == "__main__":
    unittest.main()
