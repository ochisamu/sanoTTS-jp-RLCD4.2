import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
class UI(C.Structure):
    _fields_=[('heard',C.c_char*1024),('spoken',C.c_char*1024),('status',C.c_char*48),
              ('battery',C.c_char*24),('reply',C.c_bool),('captions',C.c_bool),('page',C.c_uint)]
class VoiceUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();so=Path(cls.tmp.name)/'ui.so'
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'.cache/font'),str(ROOT/'runtime/voice_ui.c'),'-o',str(so)],check=True)
        cls.lib=C.CDLL(str(so))
        cls.lib.voice_ui_pages.argtypes=[C.c_char_p];cls.lib.voice_ui_pages.restype=C.c_uint
        cls.lib.voice_ui_has_glyph.argtypes=[C.c_uint32];cls.lib.voice_ui_has_glyph.restype=C.c_bool
        cls.lib.voice_ui_copy.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p]
        cls.lib.voice_ui_draw.argtypes=[C.c_void_p,C.POINTER(UI)]
        cls.lib.voice_ui_mouth.argtypes=[C.c_void_p,C.c_uint8,C.c_bool]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_font_coverage(self):
        for c in '認識回答実験版ききとりよみあげおうむ返しかいわボタンをはなして。ー！？':
            self.assertTrue(self.lib.voice_ui_has_glyph(ord(c)),c)
        self.assertFalse(self.lib.voice_ui_has_glyph(0x1f600))
    def test_pages_and_newlines(self):
        for s,n in [('',1),('あ'*69,1),('あ'*70,2),('A'*141,1),('A'*142,2),('あ\nい\nう\nえ',2)]:
            self.assertEqual(self.lib.voice_ui_pages(s.encode()),n)
    def test_utf8_boundary_copy(self):
        buf=C.create_string_buffer(8);self.lib.voice_ui_copy(buf,8,'あいう'.encode())
        self.assertEqual(buf.value.decode(),'あい')
    def test_frame_bounds_invalid_utf8_and_mouth(self):
        buf=(C.c_ubyte*15032)(*([0xa5]*15032));ptr=C.byref(buf,16)
        ui=UI(heard=b'\xf0\x80\x80\x80\xff'+('あ'*90).encode(),spoken='こんにちは'.encode(),status=b'READY',battery=b'BAT 4.00V')
        self.lib.voice_ui_draw(ptr,C.byref(ui));before=bytes(buf)
        self.lib.voice_ui_mouth(ptr,255,True);after=bytes(buf)
        self.assertEqual(after[:16],b'\xa5'*16);self.assertEqual(after[-16:],b'\xa5'*16)
        for x in range(400):
            for y in range(300):
                iy=299-y;i=16+(x//2)*75+iy//4;bit=1<<(7-(((iy&3)<<1)|(x&1)))
                if (before[i]^after[i])&bit:self.assertTrue(137<=x<263 and 148<=y<199)
    def test_next_page_changes_text(self):
        fb=(C.c_ubyte*15000)();ui=UI(heard=('あ'*69+'いいね').encode(),status=b'READY',captions=True)
        self.lib.voice_ui_draw(fb,C.byref(ui));first=bytes(fb)
        ui.page=1;self.lib.voice_ui_draw(fb,C.byref(ui));self.assertNotEqual(first,bytes(fb))
    def test_idle_hides_transcripts(self):
        fb=(C.c_ubyte*15000)();ui=UI(heard='ひみつのことば'.encode(),spoken='へんとう'.encode(),status=b'READY')
        self.lib.voice_ui_draw(fb,C.byref(ui));hidden=bytes(fb)
        ui.heard=b'';ui.spoken=b'';self.lib.voice_ui_draw(fb,C.byref(ui));self.assertEqual(hidden,bytes(fb))

if __name__=='__main__':unittest.main()
