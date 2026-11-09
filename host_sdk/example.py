"""Minimal upper-computer integration. Read-only unless explicitly requested."""
from surgerybox_v3 import SurgeryBox

with SurgeryBox('COM4') as box:
    print(box.identity)
    print(box.status())
    print(box.position())  # counts/degrees/turns; no fabricated millimetres

    # UI actions (do not uncomment all of these as an automatic startup sequence):
    # box.set_light(True)
    # box.set_brake('release')  # 180 degrees
    # box.set_brake('weak')     # 120 degrees
    # box.set_brake('lock')     # 50 degrees
    # box.set_brake('off')      # stops motor and disables servo pulses
    # box.zero()               # display zero only, leaves power-on home intact

    # Power-on position is captured by the MCU; no endpoint marking is needed.
    # token = box.wind()       # brake release -> rewind -> friction release 1s
    # box.wait_motor()         # raises on a fault; never fakes successful completion
    # box.finish()             # normal early finish, includes 1-second release
    # box.stop()               # emergency motor stop, never automatically reverses

    # In a real application keep this context alive throughout hardware use.
    # Poll box.next_event() from a UI timer, or consume it in a worker thread.
    # box.stream(True) enables 10 Hz relative encoder events.
    # Exiting this context sends SAFE: motor off, lamp off, servo pulses off.
