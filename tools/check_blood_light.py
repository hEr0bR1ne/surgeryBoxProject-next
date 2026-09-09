"""Check the blood-light command path on a connected MCU; never move the motor."""
import argparse
import time

import serial


def exchange(port, command, matches):
    port.reset_input_buffer()
    port.write((command + "\n").encode("ascii"))
    port.flush()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        line = port.readline().decode("utf-8", errors="replace").strip()
        if matches(line):
            print(f"{command} -> {line}", flush=True)
            return line
    raise RuntimeError(f"No expected response to {command}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--hold-seconds", type=float, default=0,
                        help="Keep the light on for 0 to 5 seconds for visual inspection")
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 5:
        parser.error("--hold-seconds must be between 0 and 5")
    # Set modem lines before opening, avoiding pyserial's default assertion.
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    with connection as port:
        time.sleep(2)
        try:
            exchange(port, "HELLO_PC", lambda line: line == "ACK: HELLO_PC")
            exchange(port, "LIGHT:OFF", lambda line: line == "LIGHT:OFF")
            exchange(port, "LIGHT?", lambda line: line == "LIGHT:OFF")
            exchange(port, "PINS?", lambda line: line.startswith("PINS:") and "D3=0" in line.split(","))
            exchange(port, "PINS?", lambda line: line.startswith("PINS:")
                     and "D7=0" in line.split(",") and "D8=0" in line.split(","))
            exchange(port, "LIGHT:ON", lambda line: line == "LIGHT:ON")
            exchange(port, "LIGHT?", lambda line: line == "LIGHT:ON")
            exchange(port, "PINS?", lambda line: line.startswith("PINS:") and "D3=1" in line.split(","))
            time.sleep(args.hold_seconds)
        finally:
            exchange(port, "LIGHT:OFF", lambda line: line == "LIGHT:OFF")
        exchange(port, "PINS?", lambda line: line.startswith("PINS:") and "D3=0" in line.split(","))
        print("PASS: handshake, commanded light states and D3 readback; final state OFF.")
        print("This does not verify MOS output voltage or visible light.")


if __name__ == "__main__":
    main()
