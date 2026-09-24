import array
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which("cc"), "C compiler required for DSP tests")
class SpeakerDsp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls.tmp.name) / "dsp")
        cls.sanitized = str(Path(cls.tmp.name) / "dsp-sanitized")
        base = ["cc", "-std=c99", "-O1", "-g", "-I", str(ROOT / "firmware/main"),
                str(ROOT / "tests/dsp_driver.c"), str(ROOT / "firmware/main/echo_dsp.c"), "-lm"]
        subprocess.run([*base, "-o", cls.binary], check=True)
        subprocess.run([*base, "-fsanitize=address,undefined", "-o", cls.sanitized], check=True)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def run_dsp(self, samples, chunk=256, tuned=True, gain=1, sanitized=False):
        raw = array.array("h", samples).tobytes()
        result = subprocess.check_output([self.sanitized if sanitized else self.binary,
                        str(chunk), str(int(tuned)), str(gain)], input=raw)
        out = array.array("h"); out.frombytes(result)
        return out

    def test_silence_short_tail_and_repeatable_reset(self):
        for n in (0, 1, 2, 13, 175, 176, 177, 512):
            self.assertEqual(list(self.run_dsp([0]*n, chunk=1)), [0]*n)
            out = self.run_dsp([12000]*n, chunk=13)
            self.assertEqual(len(out), n)
            if n: self.assertEqual(out[-1], 0)
            self.assertEqual(out, self.run_dsp([12000]*n, chunk=13))

    def test_chunk_boundaries_do_not_change_output(self):
        samples = [int(24000*math.sin(i*.127) + 5000*math.sin(i*.019)) for i in range(8192)]
        ref = self.run_dsp(samples, chunk=512)
        for chunk in (1, 13, 176, 177, 256):
            self.assertEqual(self.run_dsp(samples, chunk), ref)

    def test_limiter_and_sanitizers(self):
        samples = [32767, -32768]*22050
        for gain in (.5, 1, 1.5):
            output = self.run_dsp(samples, gain=gain, sanitized=True)
            self.assertEqual(len(output), len(samples))
            self.assertLessEqual(max(abs(x) for x in output), 22937)
        subprocess.run([self.sanitized, "--selftest"], check=True)

    def test_dc_and_low_bass_are_suppressed(self):
        dc = self.run_dsp([16000]*44100)
        self.assertLessEqual(max(abs(x) for x in dc[-11025:]), 2)
        def rms(hz):
            samples = [int(8000*math.sin(2*math.pi*hz*i/22050)) for i in range(22050)]
            out = self.run_dsp(samples)[11025:-176]
            return math.sqrt(sum(x*x for x in out)/len(out))
        self.assertLess(rms(100), rms(1000)*.3)

    def test_legacy_is_original_quarter_gain(self):
        samples = [-32768, -32767, -3, -1, 0, 1, 3, 32767]
        self.assertEqual(list(self.run_dsp(samples, tuned=False)), [int(x*.25) for x in samples])

    def test_rlcd_profile_limits_and_chunk_invariance(self):
        samples=[int(28000*math.sin(i*.137)) for i in range(8192)]
        ref=self.run_dsp(samples,tuned=2)
        self.assertEqual(ref,self.run_dsp(samples,tuned=2,chunk=13,sanitized=True))
        self.assertLessEqual(max(abs(x) for x in ref),22937)
        self.assertEqual(ref[-1],0)

    def test_rlcd_clear_profile_spectral_direction(self):
        def rms(hz,profile):
            samples=[int(400*math.sin(2*math.pi*hz*i/22050)) for i in range(22050)]
            out=self.run_dsp(samples,tuned=profile)[11025:-176]
            return math.sqrt(sum(x*x for x in out)/len(out))
        self.assertLess(rms(650,2),rms(650,3)*.9)
        self.assertGreater(rms(3300,2),rms(3300,3)*1.03)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for CharaDock comparison")
    def test_matches_charadock_reference_at_22050hz(self):
        samples = [int((.15 if i < 10000 else .75)*32767*math.sin(i*.137)) for i in range(30000)]
        raw = array.array("h", samples).tobytes()
        js = "const fs=require('fs');const r=require(process.argv[1]);process.stdout.write(r.processAtomEchoPcm16(fs.readFileSync(0),{sampleRate:22050,outputGain:Number(process.argv[2])}));"
        for gain in (.5, 1, 1.5):
            expected = array.array("h")
            expected.frombytes(subprocess.check_output(["node", "-e", js,
                str(ROOT / "tests/reference_atom_echo.cjs"), str(gain)], input=raw))
            actual = self.run_dsp(samples, chunk=13, gain=gain)
            self.assertEqual(len(actual), len(expected))
            self.assertLessEqual(max(abs(a-b) for a, b in zip(actual, expected)), 3,
                                 "C float vs JS double difference exceeds 3 PCM16 LSB")

if __name__ == "__main__": unittest.main()
