import ctypes as C
import json
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class Fact(C.Structure):
    _fields_=[('id',C.c_char_p),('reading',C.c_char_p),('display',C.c_char_p)]
class Replies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();so=Path(cls.tmp.name)/'reply.so'
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'.cache/reply-assets'),str(ROOT/'runtime/reply_support.c'),'-o',str(so)],check=True)
        cls.lib=C.CDLL(str(so));cls.lib.reply_knowledge_lookup.argtypes=[C.c_char_p,C.POINTER(Fact)]
        cls.lib.reply_display_text.argtypes=[C.c_char_p];cls.lib.reply_display_text.restype=C.c_char_p
        cls.cards=json.loads((ROOT/'.cache/reply-assets/knowledge.json').read_text())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_every_alias_and_display(self):
        for r in self.cards:
            for q in r['aliases']:
                f=Fact();self.assertEqual(self.lib.reply_knowledge_lookup(q.encode(),C.byref(f)),1)
                self.assertEqual(f.id.decode(),r['id']);self.assertEqual(f.reading.decode(),r['reading'])
                self.assertEqual(f.display.decode(),r['display'])
    def test_prefix_and_punctuation(self):
        f=Fact();q='ねえ。'+self.cards[0]['aliases'][0]+'？'
        self.assertEqual(self.lib.reply_knowledge_lookup(q.encode(),C.byref(f)),1)
    def test_no_partial_negative_or_similar_math_match(self):
        for q in ['いちたすには','いちたすいちわからない','にたすさんじゃない','いっしゅうかんはなんにちじゃなくて','', 'あ'*1000]:
            f=Fact();self.assertEqual(self.lib.reply_knowledge_lookup(q.encode(),C.byref(f)),0,q)
            self.assertIsNone(f.id)
    def test_caption_table_and_unknown(self):
        for k,v in json.loads((ROOT/'.cache/reply-assets/captions.json').read_text()).items():
            self.assertEqual(self.lib.reply_display_text((k+'。').encode()).decode(),v)
        for s in ['はし','これはしらないぶん','あ'*1000]:
            self.assertEqual(self.lib.reply_display_text(s.encode()).decode(),s)
    def test_no_development_leak(self):
        root=ROOT/'.cache/improvement-bpe'
        if not (root/'train.jsonl').exists():self.skipTest('Training split check requires locally prepared training data')
        train={json.loads(s)['question_kana'] for s in (root/'train.jsonl').read_text().splitlines()}
        dev={json.loads(s)['question_kana'] for s in (root/'dev.jsonl').read_text().splitlines()}
        self.assertFalse(train&dev)
        aliases={q for r in self.cards for q in r['aliases']}
        self.assertFalse(aliases&dev)
if __name__=='__main__':unittest.main()
