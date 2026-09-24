import ctypes as C
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from data import corpus, encode, VOCAB, CASES

ROOT=Path(__file__).resolve().parents[1]

class CorpusTests(unittest.TestCase):
    def test_split_and_vocabulary(self):
        train,dev=corpus()
        self.assertFalse({e['question'] for e in train}&{e['question'] for e in dev})
        self.assertEqual(len(VOCAB),128)
        for e in dev:self.assertNotIn(4,encode(e['question']))
    def test_normalization(self):
        self.assertEqual(encode('キョウ ハ'),encode('きょうは'))

class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(os.environ.get('KLM_TEST_MODEL',str(ROOT/'.cache/tiny-lm/model.bin')))
        if not path.exists():raise unittest.SkipTest('Train model first')
        cls.temp=tempfile.TemporaryDirectory();library=Path(cls.temp.name)/'klm.so'
        cls.blob=path.read_bytes();header=struct.unpack('<8s10I',cls.blob[:48]);cls.dim,cls.heads,cls.ff=header[3:6]
        cls.vocab,cls.context=header[6:8];cls.bpe=header[0]==b'KLMW8v2\0';cls.header=header
        cls.encode_text=staticmethod(encode)
        if cls.bpe:
            from tokenizers import Tokenizer
            cls.tokenizer=Tokenizer.from_file(os.environ.get('KLM_TEST_TOKENIZER',str(ROOT/'.cache/bpe-dialogue/tokenizer.json')))
            cls.encode_text=staticmethod(lambda s:cls.tokenizer.encode(s).ids)
        flags=[f'-DKLM_DIM={cls.dim}',f'-DKLM_HEADS={cls.heads}',f'-DKLM_FF={cls.ff}',f'-DKLM_LAYERS={header[2]}']
        if cls.bpe:flags.append('-DKLM_BPE=1')
        subprocess.run(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',*flags,str(ROOT/'tiny_lm/klm.c'),str(ROOT/'third_party/sanoTTS-jp/csrc/g2p.c'),'-lm','-o',str(library)],check=True)
        cls.lib=C.CDLL(str(library))
        cls.lib.klm_open.argtypes=[C.c_void_p,C.c_size_t];cls.lib.klm_open.restype=C.c_void_p
        cls.lib.klm_close.argtypes=[C.c_void_p];cls.lib.klm_reset.argtypes=[C.c_void_p]
        cls.lib.klm_step.argtypes=[C.c_void_p,C.c_int,C.c_void_p]
        cls.lib.klm_encode.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_int),C.c_int]
        cls.lib.klm_tts_text.argtypes=[C.c_char_p,C.c_void_p,C.c_size_t]
        cls.lib.saan_g2p.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(C.c_int32),C.c_int32,C.POINTER(C.c_int32),C.c_void_p]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def open(self,blob=None):
        raw=self.blob if blob is None else blob
        self.backing=C.create_string_buffer(len(raw)+16);ptr=(C.addressof(self.backing)+15)&~15
        C.memmove(ptr,raw,len(raw));return self.lib.klm_open(ptr,len(raw))
    def test_kernel(self):self.assertEqual(self.lib.klm_kernel_selftest(),0)
    def test_truncated_and_corrupt(self):
        for n in (0,1,47,48,100,len(self.blob)-1):self.assertFalse(self.open(self.blob[:n]))
        b=bytearray(self.blob);b[-1]^=1;self.assertFalse(self.open(bytes(b)))
        b=bytearray(self.blob);b[16]^=1;self.assertFalse(self.open(bytes(b)))
    def test_input_and_context_limits(self):
        m=self.open();self.assertTrue(m)
        try:
            ids=(C.c_int*82)()
            for bad in (b'',b'abc',b'\xe3',b'\xe3\x81',b'\xed\xa0\x80','漢字'.encode(),('あ'*81).encode()):
                self.assertLess(self.lib.klm_encode(m,bad,ids,82),0)
            n=self.lib.klm_encode(m,'キョウハツカレタ'.encode(),ids,82)
            self.assertEqual(list(ids)[:n],[1]+self.encode_text('きょうはつかれた')+[2])
            self.assertLess(self.lib.klm_step(m,self.vocab,None),0)
            for _ in range(self.context):self.assertGreaterEqual(self.lib.klm_step(m,1,None),0)
            self.assertLess(self.lib.klm_step(m,1,None),0)
            self.lib.klm_reset(m);self.assertGreaterEqual(self.lib.klm_step(m,1,None),0)
        finally:self.lib.klm_close(m)
    def test_repeat_is_deterministic(self):
        m=self.open();self.assertTrue(m)
        try:
            seq=[1]+self.encode_text('きょうはつかれた')+[2];runs=[]
            for _ in range(2):
                self.lib.klm_reset(m);runs.append([self.lib.klm_step(m,t,None) for t in seq])
            self.assertEqual(runs[0],runs[1])
        finally:self.lib.klm_close(m)
    def test_all_reply_texts_accepted_by_actual_tts_g2p(self):
        for _,_,_,answers in CASES:
            for answer in answers.split('|'):
                out=C.create_string_buffer(256);ids=(C.c_int32*350)();count=C.c_int32()
                n=self.lib.klm_tts_text(answer.encode(),out,256)
                self.assertGreater(n,0)
                self.assertEqual(self.lib.saan_g2p(out.value,n,ids,350,C.byref(count),None),0,answer)
                self.assertGreater(count.value,3)
        tiny=C.create_string_buffer(2)
        self.assertLess(self.lib.klm_tts_text('こんにちは'.encode(),tiny,2),0)
        self.assertEqual(tiny.value,b'')

    def test_independent_pytorch_w8a8_reference(self):
        try:
            import numpy as np
            import torch
            from torch.nn import functional as F
        except ImportError:self.skipTest('PyTorch and numpy required for numerical reference')
        torch.set_num_threads(2);offset=48
        def array(n,dtype):
            nonlocal offset
            offset=(offset+15)&~15
            a=np.frombuffer(self.blob,dtype=dtype,count=n,offset=offset).copy();offset+=a.nbytes
            return torch.from_numpy(a).float()
        def mat(rows,cols):
            w=array(rows*cols,'i1').reshape(rows,cols);scale=array(rows,'<f4')
            return w*scale[:,None]
        d,h,f=self.dim,self.heads,self.ff
        if self.bpe:
            array(self.vocab*self.header[10],'u1');array(self.header[9]*3,'<u2')
        else:array(self.vocab,'<u4')
        emb=mat(self.vocab,d);pos=array(self.context*d,'<f4').reshape(self.context,d);blocks=[]
        for _ in range(self.header[2]):blocks.append((array(d,'<f4'),mat(3*d,d),mat(d,d),array(d,'<f4'),mat(f,d),mat(d,f)))
        final=array(d,'<f4');self.assertEqual(offset,len(self.blob))
        def norm(x,w):return x*torch.rsqrt(x.square().mean(-1,keepdim=True)+1e-5)*w
        def linear(x,w):
            scale=x.abs().amax(-1,keepdim=True).clamp(min=1e-8)/127
            q=(x/scale).round().clamp(-127,127)*scale
            return F.linear(q,w)
        m=self.open();self.assertTrue(m);seq=[1]+self.encode_text('きょうはつかれた')+[2]
        try:
            for length,token in enumerate(seq,1):
                actual=(C.c_float*self.vocab)();next_token=self.lib.klm_step(m,token,actual)
                with torch.inference_mode():
                    x=emb[seq[:length]]+pos[:length]
                    for n1,qkv,o,n2,up,down in blocks:
                        q,k,v=linear(norm(x,n1),qkv).reshape(length,3,h,d//h).permute(1,2,0,3).unbind(0)
                        a=F.scaled_dot_product_attention(q,k,v,is_causal=True).transpose(0,1).reshape(length,d)
                        x=x+linear(a,o);x=x+linear(F.relu(linear(norm(x,n2),up)),down)
                    expected=linear(norm(x,final),emb)[-1].numpy()
                np.testing.assert_allclose(np.array(actual),expected,atol=.025,rtol=.003)
                expected[:3]=-np.inf;expected[4]=-np.inf
                if not self.bpe:expected[106:]=-np.inf
                self.assertEqual(next_token,int(expected.argmax()))
        finally:self.lib.klm_close(m)

    def test_bpe_tokenizer_parity(self):
        if not self.bpe:self.skipTest('BPE only')
        import random
        from data import CHARS
        rng=random.Random(67)
        samples=['きょおわつかれた','あめ。きょおわなにをしよお','12345','あ'*80]
        samples.extend(''.join(rng.choices(CHARS,k=rng.randint(1,80))) for _ in range(100))
        path=ROOT/'.cache/daily-kana/dev.jsonl'
        if path.exists():samples.extend(json.loads(s)['question_kana'] for s in path.read_text().splitlines())
        m=self.open();self.assertTrue(m)
        try:
            for s in samples:
                ids=(C.c_int*82)();n=self.lib.klm_encode(m,s.encode(),ids,82)
                self.assertEqual(list(ids)[:n],[1]+self.encode_text(s)+[2],s)
        finally:self.lib.klm_close(m)

    def test_bpe_rejects_invalid_tokens_and_merges_with_valid_checksum(self):
        if not self.bpe:self.skipTest('BPE only')
        merge_offset=(48+self.vocab*self.header[10]+15)&~15
        for offset,value in ((48+5*40+1,ord('x')),(48+5*40,39),(merge_offset,0),(merge_offset+4,0)):
            b=bytearray(self.blob);b[offset]=value;checksum=2166136261
            for v in b[48:]:checksum=((checksum^v)*16777619)&0xffffffff
            struct.pack_into('<I',b,36,checksum)
            self.assertFalse(self.open(bytes(b)))

if __name__=='__main__':unittest.main()
