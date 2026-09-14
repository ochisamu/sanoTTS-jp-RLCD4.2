"""Contracts for the v1.0 model/API migration; no downloaded assets required."""
import unittest

from test_demo import demo, ROOT


class V1MigrationTests(unittest.TestCase):
    def test_model_pins_agree_with_cmake(self):
        cmake = (ROOT / "firmware/CMakeLists.txt").read_text()
        model = demo.ASSET_SPECS["model"]
        self.assertEqual(model["name"], "saanotts-jp-v4-int8.bin")
        self.assertEqual(model["size"], 654032)
        for spec in demo.ASSET_SPECS.values():
            self.assertIn("/v1.0.0/", spec["url"])
            for value in (spec["name"], str(spec["size"]), spec["sha256"]):
                self.assertIn(value, cmake)
        self.assertNotIn("v3-int8", cmake)

    def test_audio_api_and_per_utterance_reset(self):
        audio = (ROOT / "firmware/main/rlcd42_saan_i2s.c").read_text()
        self.assertIn('#include "saan_audio.h"', audio)
        self.assertIn('#include "saan_pcm.h"', audio)
        self.assertNotIn('"saan_i2s.h"', audio)
        begin = audio.split("bool saan_audio_begin_utterance(", 1)[1].split("\n}", 1)[0]
        for token in ("s_preroll_fill = 0", "s_preroll && s_stereo",
                      "n_samples <= SAAN_AUDIO_PREROLL_SAMPLES",
                      "return s_utterance_transport_ok"):
            self.assertIn(token, begin)
        self.assertIn("SPEECH_DURATION_SCALE 1.15f", audio)
        self.assertIn("PCM_PLAYBACK_GAIN     1.00f", audio)

    def test_console_implements_poll_api_without_unbounded_read(self):
        console = (ROOT / "firmware/main/rlcd42_console.c").read_text()
        self.assertIn("void saan_console_prompt(void)", console)
        self.assertIn("int saan_console_poll(const char **out, uint32_t wait_ms)", console)
        self.assertIn("wait_ms < KEY_POLL_MS ? wait_ms : KEY_POLL_MS", console)
        self.assertIn("if (!key_demo_requested()) return SAAN_CONSOLE_PENDING", console)
        self.assertNotIn("saan_console_readline", console)

    def test_v4_attribution_is_bundled(self):
        files = demo.DIST_NOTICE_FILES
        notice_path = ROOT / "licenses/sanoTTS-jp-NOTICE.txt"
        self.assertEqual(files[notice_path], "NOTICE.txt")
        self.assertEqual(files[ROOT / "licenses/sanoTTS-jp-Apache-2.0.txt"],
                         "LICENSE-APACHE-2.0.txt")
        notice = notice_path.read_text()
        for source in ("LibriTTS-R", "CML-TTS", "AISHELL-3", "つくよみちゃん"):
            self.assertIn(source, notice)


if __name__ == "__main__":
    unittest.main()
