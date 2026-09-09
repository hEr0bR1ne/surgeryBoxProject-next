"""Shared physical-light integration for both remove-needle training screens."""
import os

from PySide6.QtCore import QTimer
from app.hardware.blood_light import BloodLightController


class BloodLightTrainingMixin:
    def _uses_physical_blood(self):
        return os.getenv("SURGERYBOX_BLOOD_LIGHT", "1").lower() not in ("0", "false", "no", "off")

    def _set_blood_light(self, on):
        if not self._uses_physical_blood() or getattr(self, "_cleanup_done", False):
            return
        if not hasattr(self, "_blood_light"):
            self._blood_light = BloodLightController(
                self._send_hardware_message, self._hardware_ready, self._blood_light_error
            )
            self._blood_light_timer = QTimer(self)
            self._blood_light_timer.timeout.connect(self._blood_light.poll)
            self._blood_light_timer.start(250)
        if on:
            # Establish the existing serial/UDP transport before Phase 4, but
            # do not issue Start or start the motor to illuminate the lamp.
            self._start_hardware_listener()
        self._blood_light.set(on)

    def _blood_light_error(self, message):
        print(f"[BloodLight] {message}")
        self.last_event_msg = message
        # This can occur in Phase 3.5, before the Phase 4 overlay is displayed.
        if not getattr(self, "_cleanup_done", False):
            self.text_display.set_text(message)

    def _receive_blood_light(self, message):
        controller = getattr(self, "_blood_light", None)
        return controller.receive(message) if controller else message.strip().upper().startswith("LIGHT:")

    def _close_blood_light(self):
        timer = getattr(self, "_blood_light_timer", None)
        if timer:
            timer.stop()
        controller = getattr(self, "_blood_light", None)
        if controller:
            controller.close()
