"""The Priorities port: must agree with the screen's rules on the shared gold set (demos/it-risk-estate/priority_gold.json). No Temporal needed."""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import priority_rules as P
GOLD = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "priority_gold.json")))["cases"]

class Gold(unittest.TestCase):
    def test_every_gold_case(self):
        for c in GOLD:
            with self.subTest(c["name"][:70]):
                p = P.prioritise(c["answer"], c.get("exposureLevel"))
                self.assertEqual(p["ok"], c.get("ok", True))
                self.assertEqual([r["system"] for r in p["rows"]], c["order"])
                self.assertEqual([r["rating"] for r in p["rows"]], c["ratings"])
                for r in p["rows"]:
                    self.assertEqual(r["triggers"], c["triggers"].get(r["system"], []))
                    self.assertEqual(r["lifted"], r["system"] in c.get("lifted", []))
    def test_the_sentence_and_reasons_match_the_screen(self):
        p = P.prioritise(GOLD[0]["answer"])
        self.assertEqual(p["sentence"], "11 systems ranked: 1 Critical, 2 High, 6 Medium, 2 Low.")
        self.assertTrue(p["rows"][0]["reason"].startswith("Critical: Critical likelihood (a known-exploited flaw is open), Critical impact (tier 1, 4 dependants)."))
    def test_nothing_in_nothing_out(self):
        self.assertFalse(P.prioritise(None)["ok"])
        self.assertIn("internet_facing", P.prioritise(GOLD[13]["answer"])["missing"])

if __name__ == "__main__": unittest.main()
