"""Perform one visible servo calibration step, then disable control pulses."""
import argparse
import time
import serial
from check_blood_light import exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--angle", type=int, required=True)
    args = parser.parse_args()
    if not 60 <= args.angle <= 150:
        parser.error("angle must be 60-150")
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    with connection as port:
        time.sleep(1)
        exchange(port, "HELLO_PC", lambda line: line == "ACK: SERVO_ONLY")
        state = exchange(port, "SERVO?", lambda line: line.startswith("SERVO:ENABLED:"))
        enabled = state.startswith("SERVO:ENABLED:1,")
        current = int(state.rsplit(":", 1)[1]) if enabled else 90
        if abs(args.angle - current) > 5:
            raise SystemExit("Requested step exceeds 5 degrees; no motion sent")
        try:
            if not enabled:
                exchange(port, "SERVO:ENABLE", lambda line: line == "SERVO:ENABLED:1,ANGLE:90")
                time.sleep(1)
            expected = f"SERVO:ENABLED:1,ANGLE:{args.angle}"
            reply = exchange(port, f"SERVO:ANGLE:{args.angle}",
                             lambda line: line == expected or line.startswith("ERROR:"))
            if reply.startswith("ERROR:"):
                raise RuntimeError(reply)
            time.sleep(3)
        finally:
            exchange(port, "SERVO:OFF", lambda line: line.startswith("SERVO:ENABLED:0,"))
        exchange(port, "SERVO?", lambda line: line.startswith("SERVO:ENABLED:0,"))
        print("Control pulses disabled. Reported angle is not physical position feedback.")


if __name__ == "__main__":
    main()
