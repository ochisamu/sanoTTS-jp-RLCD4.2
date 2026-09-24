"""Run with Windows Python/pyserial when the RLCD is attached as COM4."""
import argparse
import json
from pathlib import Path
import time
import wave
import serial


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port', default='COM4')
    parser.add_argument('--record', type=Path, help='Explicit five-second capture to a local WAV')
    parser.add_argument('--arm',action='store_true',help='Wait for the RLCD KEY button before recording')
    parser.add_argument('--command',choices=['TEST','ECHO','SAY','LISTEN'],help='Run an on-device diagnostic')
    parser.add_argument('--watch',action='store_true',help='Watch a local KEY-triggered recognition')
    args=parser.parse_args()
    port=serial.Serial()
    port.port=args.port
    port.baudrate=115200
    port.timeout=1
    port.dtr=False
    port.rts=False
    with port:
        port.reset_input_buffer()
        port.write(b'ID\n')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            line=port.readline()
            if b'RLCD42_MIC_PROBE:v1 READY PA_OFF' in line:
                print(line.decode().strip(), flush=True)
                break
        else:
            raise RuntimeError('Expected RLCD microphone probe not detected; no recording requested')
        if args.command or args.watch:
            if args.command:
                port.write(args.command.encode()+b'\n')
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                line=port.readline().decode(errors='replace').strip()
                if line:
                    print(line,flush=True)
                if line.startswith('ERROR:') or 'stack overflow' in line or 'Guru Meditation' in line:
                    raise RuntimeError(line)
                if line.startswith('NO_SPEECH:'):
                    return
                if line.startswith('ECHO_DONE:') or (args.command=='TEST' and line.startswith('STT_DONE:')):
                    return
            raise TimeoutError('ESP32 inference did not finish')
        if not args.record:
            return
        if args.record.exists():
            raise FileExistsError(args.record)
        port.write(b'ARM\n' if args.arm else b'REC\n')
        deadline=time.monotonic()+(120 if args.arm else 15)
        while time.monotonic()<deadline:
            line=port.readline()
            if line.startswith((b'ARMED:',b'RECORDING:')):
                print(line.decode().strip(),flush=True)
            if line.startswith(b'RECORDING:'):
                deadline=time.monotonic()+15
            if line.startswith(b'ERROR:'):
                raise RuntimeError(line.decode())
            if line.startswith(b'PCM:'):
                fields=line.decode().strip().split(':')
                size, rate, channels, bits=map(int, fields[1:])
                if (size,rate,channels,bits)!=(320000,16000,2,16):
                    raise ValueError('Unexpected audio framing')
                data=bytearray()
                while len(data)<size and time.monotonic()<deadline:
                    data.extend(port.read(size-len(data)))
                if len(data)!=size:
                    raise TimeoutError(f'Truncated PCM ({len(data)}/{size}); not saving corrupt audio')
                break
        else:
            raise TimeoutError('No PCM frame')
        trailer=[]
        while time.monotonic()<deadline:
            line=port.readline().decode(errors='replace').strip()
            if line:
                trailer.append(line)
            if line=='DONE':
                break
        if not trailer or trailer[-1]!='DONE':
            raise RuntimeError('Missing capture completion marker')
        args.record.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(args.record),'wb') as wav:
            wav.setnchannels(channels); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(data)
        print(json.dumps({'seconds':5,'bytes':len(data),'device':trailer}), flush=True)


if __name__=='__main__':
    main()
