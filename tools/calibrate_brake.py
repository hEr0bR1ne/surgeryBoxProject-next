"""Query brake state, or request one bounded calibration step. No motor drive."""
import argparse
import time

import serial
from check_blood_light import exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--angle", type=int, help="Optional requested angle, 0-125 degrees")
    args = parser.parse_args()
    if args.angle is not None and not 0 <= args.angle <= 125:
        parser.error("angle must be between 0 and 125")
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    with connection as port:
        time.sleep(1)
        exchange(port, "HELLO_PC", lambda line: line == "ACK: HELLO_PC")
        response = exchange(port, "BRAKE?", lambda line: line.startswith("BRAKE:ANGLE:"))
        current = int(response.rsplit(":", 1)[1])
        exchange(port, "PINS?", lambda line: line.startswith("PINS:")
                 and "D7=0" in line.split(",") and "D8=0" in line.split(","))
        if args.angle is not None:
            if abs(args.angle - current) > 5:
                raise SystemExit("Refusing a step larger than 5 degrees")
            command = f"BRAKE:ANGLE:{args.angle}"
            reply = exchange(port, command, lambda line: line == command or line.startswith("ERROR:"))
            if reply.startswith("ERROR:"):
                raise SystemExit(reply)
            exchange(port, "BRAKE?", lambda line: line == command)
        print("Reported angles are commanded positions, not measured angle or brake force.")


if __name__ == "__main__":
    main()
