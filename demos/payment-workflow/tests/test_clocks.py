"""The notification clocks port: must agree with the screen's rules on the shared gold set (demos/it-risk-register/clocks_gold.json). No Temporal needed."""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import clock_rules as C
with open(os.path.join(HERE, "..", "..", "it-risk-register", "clocks_gold.json")) as f: GOLD = json.load(f)["cases"]
with open(os.path.join(HERE, "..", "..", "it-risk-register", "seed-register-postgres.sql")) as f: SEED = f.read()

class Gold(unittest.TestCase):
    def test_every_gold_case(self):
        for c in GOLD:
            with self.subTest(c["name"][:70]):
                r = C.compute(c["rules"], c["declared"], c["decision"], C.parse_ts(c["now"]))
                self.assertEqual(r["state"], c["state"]); self.assertEqual([[x["rule_id"], x["due_at"], x["state"]] for x in r["clocks"]], c["expect"])
    def test_flags_match_the_screen(self):
        r = C.compute(GOLD[2]["rules"], GOLD[2]["declared"], GOLD[2]["decision"], C.parse_ts(GOLD[2]["now"]))["clocks"]
        self.assertIn("already past when it was recorded as major", r[0]["flags"]); self.assertIn("depends on when the previous report is sent", r[1]["flags"])
        self.assertEqual(C.compute(GOLD[0]["rules"], GOLD[0]["declared"], GOLD[0]["decision"], C.parse_ts("2026-11-20 00:00:00"))["clocks"][0]["flags"], [])
    def test_the_gold_rules_are_the_seeded_rules(self):
        for r in GOLD[3]["rules"]:
            self.assertIn("('%s'," % r["rule_id"], SEED)
        self.assertEqual({r["rule_id"] for r in GOLD[3]["rules"]}, {"dora-initial", "dora-intermediate", "dora-final", "mas-notify", "mas-root-cause"})
    def test_timestamps_without_a_zone_are_utc(self):
        self.assertEqual(C.iso(C.parse_ts("2026-11-20 08:15:00.0")), "2026-11-20T08:15:00Z"); self.assertEqual(C.iso(C.parse_ts("2026-11-20T09:00:00+02:00")), "2026-11-20T07:00:00Z"); self.assertIsNone(C.parse_ts("soon"))

if __name__ == "__main__": unittest.main()
