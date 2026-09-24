import unittest
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from prepare_bpe import dialogue_row,T
from data import CHARS

class BPETests(unittest.TestCase):
    def setUp(self):
        self.tok=Tokenizer(BPE(unk_token='<unk>'))
        self.tok.train_from_iterator(['きょおわはれ。あめだよ。']*4,BpeTrainer(vocab_size=128,min_frequency=2,
            initial_alphabet=list(CHARS),special_tokens=['<pad>','<bos>','<sep>','<eos>','<unk>'],max_token_length=12,show_progress=False))
    def test_roundtrip(self):
        s='きょおわはれ。あめだよ。'
        ids=self.tok.encode(s).ids
        self.assertEqual(''.join(self.tok.id_to_token(i) for i in ids),s)
        self.assertLess(len(ids),len(s))
    def test_response_only_labels(self):
        q='きょおわはれ。';a='あめだよ。'
        row,labels=dialogue_row(self.tok,q,a)
        self.assertEqual(len(row),T);self.assertEqual(len(labels),T-1)
        sep=row.index(2)
        self.assertTrue(all(t==-100 for t in labels[:sep]))
        self.assertEqual(labels[sep:sep+len(self.tok.encode(a).ids)+1],self.tok.encode(a).ids+[3])
        self.assertEqual([i for i in labels if i!=-100],self.tok.encode(a).ids+[3])
    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):dialogue_row(self.tok,'漢字','あめ')
        with self.assertRaises(ValueError):dialogue_row(self.tok,'ぬ'*100,'あめ')

if __name__=='__main__':unittest.main()
