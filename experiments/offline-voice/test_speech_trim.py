import ctypes
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

class TrimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        path=Path(cls.tmp.name)/'trim.so'
        subprocess.run(['cc','-shared','-fPIC','-O2','runtime/speech_trim.c','-lm','-o',str(path)],check=True)
        cls.lib=ctypes.CDLL(str(path))
        cls.lib.speech_trim.argtypes=[ctypes.POINTER(ctypes.c_float),ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int)]
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def trim(self,values):
        data=(ctypes.c_float*len(values))(*values);a=ctypes.c_int();b=ctypes.c_int()
        result=self.lib.speech_trim(data,len(values),ctypes.byref(a),ctypes.byref(b))
        return result,a.value,b.value
    def test_silence_keeps_input(self):
        self.assertEqual(self.trim([0]*80000),(0,0,80000))
    def test_padding_and_internal_pause(self):
        x=[.0004*math.sin(i*.2) for i in range(80000)]
        for start,end in [(16000,28000),(32000,44000)]:
            for i in range(start,end): x[i]+=.02*math.sin(i*.3)
        ok,a,b=self.trim(x)
        self.assertEqual(ok,1);self.assertLessEqual(a,12000);self.assertGreaterEqual(b,48000)
        self.assertLess(b-a,50000)
    def test_no_crop_without_quiet_context(self):
        x=[.02*math.sin(i*.3) for i in range(80000)]
        self.assertEqual(self.trim(x),(0,0,80000))
    def test_spike_is_not_speech(self):
        x=[0.]*80000;x[20000]=1
        self.assertEqual(self.trim(x),(0,0,80000))

    def test_quiet_short_phrase_survives_global_rms_gate(self):
        x=[20/32768*math.sqrt(2)*math.sin(i*.2) for i in range(80000)]
        for i in range(16000,19200): x[i]+=100/32768*math.sqrt(2)*math.sin(i*.3)
        self.assertLess(math.sqrt(sum(v*v for v in x)/len(x)),.002)
        ok,a,b=self.trim(x)
        self.assertEqual(ok,1);self.assertLessEqual(a,16000);self.assertGreaterEqual(b,19200)
        self.assertGreaterEqual(b-a,16000)

    def test_short_phrase_near_boundaries(self):
        for start in (0,76800):
            x=[0.]*80000
            for i in range(start,start+3200): x[i]=.02*math.sin(i*.3)
            ok,a,b=self.trim(x)
            self.assertEqual(ok,1);self.assertGreaterEqual(a,0);self.assertLessEqual(b,80000)
            self.assertLessEqual(a,start);self.assertGreaterEqual(b,start+3200)

if __name__=='__main__': unittest.main()
