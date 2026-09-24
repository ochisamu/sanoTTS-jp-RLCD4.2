"""Windows or Linux pyserial console. Sends text only; no PC LM or TTS inference."""
import argparse
import json
from pathlib import Path
import time
import serial
from data import normalize

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',default='COM4')
    parser.add_argument('--question',help='Kana question; omit for an interactive console')
    parser.add_argument('--say',action='store_true',help='Play the generated answer on the RLCD')
    parser.add_argument('--log',type=Path,help='Explicitly save this session locally (may contain private text)')
    args=parser.parse_args();lines=[]
    if args.log and args.log.exists():raise FileExistsError(args.log)
    port=serial.Serial();port.port=args.port;port.baudrate=115200;port.timeout=.5;port.write_timeout=3
    port.dtr=False;port.rts=False
    with port:
        port.reset_input_buffer();port.write(b'ID\n');deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            response=port.readline().decode('utf-8',errors='replace').strip()
            if response.startswith('RLCD42_MIC_PROBE:v1') and 'ASKSAY' in response:break
        else:raise RuntimeError('Expected RLCD LM experiment not detected; nothing sent')
        print('Experimental kana LM. Not a general assistant. /quit to exit.',flush=True)
        while True:
            try:q=args.question if args.question is not None else input('kana> ')
            except (EOFError,KeyboardInterrupt):break
            if q.strip()=='/quit':break
            q=normalize(q)
            if not q or '\n' in q or '\r' in q or len(q)>80:
                raise ValueError('Use 1–80 kana characters, one line')
            command=('ASKSAY ' if args.say else 'ASK ')+q
            port.write((command+'\n').encode('utf-8'));deadline=time.monotonic()+120
            lines.append('QUESTION:'+q)
            while time.monotonic()<deadline:
                line=port.readline().decode('utf-8',errors='replace').strip()
                if not line:continue
                print(line,flush=True);lines.append(line)
                if line.startswith('ERROR:') or 'Guru Meditation' in line or 'stack overflow' in line:
                    raise RuntimeError(line)
                if (not args.say and line.startswith('LM_DONE:')) or (args.say and line.startswith('ECHO_DONE:')):break
            else:raise TimeoutError('RLCD did not finish')
            if args.question is not None:break
    if args.log:
        args.log.parent.mkdir(parents=True,exist_ok=True)
        args.log.write_text(json.dumps({'lines':lines},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
