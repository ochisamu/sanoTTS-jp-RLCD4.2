import unittest
from ctc import PHONES, decode, frames


class CTCTest(unittest.TestCase):
    def test_collapse(self):
        self.assertEqual(decode([0,1,1,0,1,2,2,0]),[1,1,2])

    def test_vocab(self):
        self.assertEqual(PHONES[0],'<blank>')
        self.assertEqual(len(PHONES),len(set(PHONES)))

    def test_frame_lengths(self):
        self.assertEqual(frames(16000),40)
        self.assertEqual(frames(80000),207)


if __name__=='__main__':
    unittest.main()
