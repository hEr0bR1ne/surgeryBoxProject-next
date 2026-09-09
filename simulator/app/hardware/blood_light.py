"""Command/acknowledgement lifecycle for the physical blood indicator."""
import time


class BloodLightController:
    def __init__(self, send, ready, report_error, clock=time.monotonic):
        self.send = send
        self.ready = ready
        self.report_error = report_error
        self.clock = clock
        self.desired = False
        self.confirmed = None
        self.pending = False
        self.closed = False
        self.last_send = float("-inf")
        self.deadline = 0

    def set(self, on):
        if self.closed:
            return
        self.desired = bool(on)
        self.confirmed = None
        self.pending = True
        self.last_send = float("-inf")
        self.deadline = self.clock() + 10
        self.poll()

    def poll(self):
        if self.closed or not self.pending:
            return
        now = self.clock()
        if now >= self.deadline:
            self.pending = False
            self.report_error("Blood light did not confirm " + ("ON" if self.desired else "OFF"))
            return
        if now - self.last_send >= 1 and self.ready():
            self.last_send = now
            try:
                self.send("LIGHT:ON" if self.desired else "LIGHT:OFF")
            except Exception:
                # The bounded retry window also covers transient write errors.
                pass

    def receive(self, message):
        line = message.strip().upper()
        if line not in ("LIGHT:ON", "LIGHT:OFF"):
            return False
        if not self.closed:
            self.confirmed = line == "LIGHT:ON"
            if self.confirmed == self.desired:
                self.pending = False
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.pending = False
        self.desired = False
        # Send before the owning screen closes its transport. No motor commands.
        try:
            if not self.ready() or not self.send("LIGHT:OFF"):
                self.report_error("Blood light OFF could not be sent; check the physical lamp")
        except Exception as exc:
            self.report_error(f"Blood light OFF failed: {exc}")
