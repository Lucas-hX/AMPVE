"""Keep Companion Face procedural and outside the real-time audio path."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FACE = ROOT / "firmware/xiaozhi/overlay/main/ampve/companion_face.cc"
COMPANION = ROOT / "firmware/xiaozhi/overlay/main/ampve/companion.cc"
PREPARE = ROOT / "firmware/tools/prepare.py"


class CompanionFaceContractTests(unittest.TestCase):
    def test_face_uses_small_lvgl_primitives_only(self):
        source = FACE.read_text()
        self.assertIn("lv_arc_create", source)
        self.assertIn("rounded_bar", source)
        for forbidden in ("lv_image_create", "lv_canvas_create", "malloc(", "calloc(", "new "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_animation_timer_is_single_and_paused_while_hidden(self):
        source = FACE.read_text()
        self.assertEqual(source.count("lv_timer_create("), 1)
        self.assertIn("lv_timer_pause(timer)", source)
        self.assertIn("constexpr uint32_t kFrameMilliseconds = 50", source)

    def test_audio_exports_only_atomic_visual_data(self):
        source = COMPANION.read_text()
        self.assertIn("std::atomic<uint8_t> output_level", source)
        self.assertNotIn("lv_", source)

    def test_prepared_firmware_compiles_the_face_module(self):
        self.assertIn('"ampve/companion_face.cc"', PREPARE.read_text())


if __name__ == "__main__":
    unittest.main()
