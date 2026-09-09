"""Read the isolated servo firmware's state without enabling PWM output."""
import argparse
import time
import serial
from check_blood_light import exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    with connection as port:
        time.sleep(1)
        exchange(port, "HELLO_PC", lambda line: line == "ACK: SERVO_ONLY")
        exchange(port, "SERVO?", lambda line: line.startswith("SERVO:ENABLED:"))


if __name__ == "__main__":
    main()
