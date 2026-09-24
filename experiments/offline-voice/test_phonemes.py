import ctypes
import subprocess
import unittest
from benchmark import ROOT
from ctc import PHONES


class PhonemeBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
            str(ROOT/'runtime/phonemes.c'),'-o',str(ROOT/'.cache/phonemes.so')],check=True)
        cls.library=ctypes.CDLL(str(ROOT/'.cache/phonemes.so'))
        cls.convert=cls.library.phonemes_to_kana
        cls.convert.argtypes=[ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.c_char_p,ctypes.c_size_t]

    def test_sentences(self):
        for phones,expected in [('ky o o w a i i t e N k i d e s u n e','きょおわいいてんきですね'),
                                ('a sh i t a w a a m e d e s u','あしたわあめです'),
                                ('t i d i','てぃでぃ'),('cl k a pau N','っか#ん')]:
            ids=[PHONES.index(p) for p in phones.split()]
            array=(ctypes.c_int*len(ids))(*ids);out=ctypes.create_string_buffer(256)
            self.assertEqual(self.convert(array,len(ids),out,len(out)),0)
            self.assertEqual(out.value.decode(),expected)

    def test_overflow_and_invalid(self):
        ids=(ctypes.c_int*1)(1);out=ctypes.create_string_buffer(3)
        self.assertEqual(self.convert(ids,1,out,3),-1)
        ids[0]=99
        self.assertEqual(self.convert(ids,1,out,3),-1)


if __name__=='__main__':
    unittest.main()
