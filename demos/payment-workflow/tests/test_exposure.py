"""The exposure rating port: must agree with the screen's rules on the shared gold set (demos/it-risk-estate/exposure_gold.json). No Temporal needed."""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import exposure_rules as X
GOLD = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "exposure_gold.json")))["cases"]

class Gold(unittest.TestCase):
    def test_every_gold_case(self):
        for c in GOLD:
            with self.subTest(c["name"][:60]):
                r = X.rate(c["answers"])
                self.assertEqual([s["score"] for s in r["scores"]], c["scores"])
                self.assertEqual(r["level"], c["level"]); self.assertEqual(r["set_by"], c["setBy"]); self.assertEqual(r["unknown"], c.get("unknown", []))
    def test_the_sentences_match_the_screen(self):
        self.assertEqual(X.rate(GOLD[0]["answers"])["sentence"], "Critical: set by questions 4 and 5.")
        miss = next(c for c in GOLD if "missing answer" in c["name"])
        self.assertEqual(X.rate(miss["answers"])["sentence"], "At least Medium: set by question 1; question 3 could not be scored, so the rating may be higher.")
    def test_an_unanswered_question_is_never_zero(self):
        r = X.rate({}); self.assertIsNone(r["level"]); self.assertEqual(r["unknown"], [1, 2, 3, 4, 5]); self.assertFalse(r["complete"])

if __name__ == "__main__": unittest.main()
