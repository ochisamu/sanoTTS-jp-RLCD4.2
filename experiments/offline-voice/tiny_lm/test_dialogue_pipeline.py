"""Offline data boundary tests; no downloads, GPU model or device required."""
import json
import tempfile
from pathlib import Path
import unittest
from dialogue_data import group_key, sources, parse, Kana
from data import encode

class PipelineTests(unittest.TestCase):
    def test_family_stays_together(self):
        first=[{'from':'human','value':'図書館で本を借りる方法を教えて'}, {'from':'gpt','value':'利用カードを作ります。'}]
        second=first+[{'from':'human','value':'カードは無料ですか'}, {'from':'gpt','value':'図書館に確認してください。'}]
        self.assertEqual(group_key(first),group_key(second))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data.jsonl'
            p.write_text('\n'.join(json.dumps({'conversations':c},ensure_ascii=False) for c in (first,second)))
            rows=sources(p)
            self.assertEqual(len(rows),2)
            self.assertEqual(len({r['split'] for r in rows}),1)
            self.assertEqual(len({r['group'] for r in rows}),1)
    def test_json_schema(self):
        self.assertEqual(parse('{"question":"こんにちは","answer":"こんにちは。"}')['answer'],'こんにちは。')
        for text in ('garbage','{"question":2,"answer":"こんにちは"}','{"question":"あああ","answer":"いいい","code":"x"}'):
            with self.assertRaises(ValueError):parse(text)
    def test_phone_matches_device(self):
        c=Kana()
        self.assertEqual(c('今日は良い天気ですね'),'きょおわよいてんきですね')
        self.assertNotIn(4,encode(c('明日は雨です')))
        with self.assertRaises(ValueError):c('https://example.com')

if __name__=='__main__':unittest.main()
