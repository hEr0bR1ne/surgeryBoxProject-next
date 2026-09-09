"""Execute production phase/render methods without opening cameras or serial ports.

Extract the methods from the actual class AST to avoid importing optional
MediaPipe and Windows/Qt device initialization on the CI runner.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock


def screen_class(filename):
    path = Path(__file__).resolve().parents[1] / "simulator" / "app" / filename
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RemoveNeedleTraining")
    selected = {"_start_phase_3_wipe_blood", "_phase_3_wipe_blood_success", "_phase_3_wipe_blood_update"}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in selected]
    namespace = {
        "time": time, "QTimer": SimpleNamespace(singleShot=lambda *args: None),
        "cv2": SimpleNamespace(FONT_HERSHEY_SIMPLEX=0,
                               getTextSize=lambda *args: ((10, 10), 0), putText=lambda *args: None)
    }
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"), namespace)
    return type("PhaseHarness", (), {name: namespace[name] for name in selected})


class BloodTrainingHooksTests(unittest.TestCase):
    def screens(self):
        for name in ("training_remove_needle.py", "training_remove_needle_mcu.py"):
            screen = screen_class(name)()
            screen._cleanup_done = False
            screen._set_blood_light = Mock()
            screen.text_display = Mock()
            screen.success_display = Mock()
            screen._start_phase_4 = Mock()
            screen.phase_transition_pending = False
            screen._draw_hand_skeleton = Mock()
            screen._overlay_png_with_alpha_scaled = Mock()
            screen._advance_wipe_blood_by_time = Mock()
            screen.blood_stain_icons = [object(), object(), object()]
            yield name, screen

    def test_stage_entry_and_success_control_real_light(self):
        for name, screen in self.screens():
            with self.subTest(screen=name):
                screen._start_phase_3_wipe_blood()
                screen._phase_3_wipe_blood_success()
                self.assertEqual([c.args[0] for c in screen._set_blood_light.call_args_list], [True, False])

    def test_physical_mode_removes_blood_png_but_virtual_mode_keeps_it(self):
        for name, screen in self.screens():
            with self.subTest(screen=name):
                screen._start_phase_3_wipe_blood()
                frame = SimpleNamespace(shape=(480, 640, 3))
                screen._uses_physical_blood = lambda: True
                screen._phase_3_wipe_blood_update(frame, [])
                screen._overlay_png_with_alpha_scaled.assert_not_called()
                screen._uses_physical_blood = lambda: False
                screen._phase_3_wipe_blood_update(frame, [])
                self.assertEqual(screen._overlay_png_with_alpha_scaled.call_count, 3)

    def test_delayed_phase_callbacks_after_exit_do_not_switch_light(self):
        for name, screen in self.screens():
            with self.subTest(screen=name):
                screen._cleanup_done = True
                screen._start_phase_3_wipe_blood()
                screen._phase_3_wipe_blood_success()
                screen._set_blood_light.assert_not_called()


if __name__ == "__main__":
    unittest.main()
