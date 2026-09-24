import unittest
from benchmark import edit_distance
from budget import estimate


class HelpersTest(unittest.TestCase):
    def test_edit_distance(self):
        for a, b, expected in [("", "", 0), ("", "雨", 1), ("明日は雨", "明日は晴れ", 2), ("かな", "かな", 0)]:
            self.assertEqual(edit_distance(a, b), expected)

    def test_budget_excludes_decoder(self):
        result = estimate({"model.encoder.layers": 100, "model.decoder.layers": 100000})
        self.assertEqual(result["parameters"], 100 + 289 * 129)


if __name__ == "__main__":
    unittest.main()
