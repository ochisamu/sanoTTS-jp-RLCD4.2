"""Render actual portable firmware pixels as a PNG, not a design mock-up."""
import argparse
import ctypes as C
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_voice_ui import UI
from PIL import Image

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'.cache/ui-preview.png');p.add_argument('--captions',action='store_true');args=p.parse_args()
    so=ROOT/'.cache/voice-ui-preview.so'
    subprocess.run(['cc','-shared','-fPIC','-O2','-I'+str(ROOT/'.cache/font'),str(ROOT/'runtime/voice_ui.c'),'-o',str(so)],check=True)
    lib=C.CDLL(str(so));lib.voice_ui_draw.argtypes=[C.c_void_p,C.POINTER(UI)]
    ui=UI(heard='きょおわすこしつかれた。なにかげんきがでることおおしえて'.encode(),
        spoken='おつかれさま。あたたかいのみものでものんで、すこしやすもお。'.encode(),
        status=b'SPEAKING' if args.captions else b'VOICE READY',battery=b'BAT 4.02V',reply=True,captions=args.captions)
    fb=(C.c_ubyte*15000)();lib.voice_ui_draw(fb,C.byref(ui))
    im=Image.new('1',(400,300));pixels=im.load()
    for y in range(300):
        for x in range(400):
            iy=299-y;pixels[x,y]=255 if fb[(x//2)*75+iy//4]&(1<<(7-(((iy&3)<<1)|(x&1)))) else 0
    args.out.parent.mkdir(parents=True,exist_ok=True);im.save(args.out);print(args.out)
if __name__=='__main__':main()
