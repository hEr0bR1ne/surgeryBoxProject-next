"""Bounded, device-specific serial handshake without UI dependencies."""

import time


def probe_serial_connection(ser, timeout=2.0, clock=time.monotonic):
    """Require the MCU's exact reply; an open port alone is not a connection.

    The caller must configure a finite read timeout on ``ser``. Discard stale
    input before sending the probe so an earlier acknowledgement cannot pass.
    """
    ser.reset_input_buffer()
    ser.write(b"HELLO_PC\n")
    ser.flush()
    deadline = clock() + timeout
    while clock() < deadline:
        raw = ser.readline()
        if raw.decode("utf-8", errors="replace").strip() == "ACK: HELLO_PC":
            return True
    return False
