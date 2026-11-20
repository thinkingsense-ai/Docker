"""python3 -m unittest discover -s demos/payment-workflow/tests     The IT-risk link judge against its gold set: the specification's rows and planted errors. No model, no network."""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import rca_judge as J, rca_rules as R

GOLD = json.load(open(os.path.join(os.path.dirname(__file__), "..", "rca_judge_gold.json")))["cases"]

class Gold(unittest.TestCase):
    def test_the_judge_reproduces_every_specification_row_except_the_documented_disagreement(self):
        rows = [c for c in GOLD if not c.get("planted")]
        self.assertEqual(len(rows), 10)
        for c in rows: self.assertEqual(J.judge_link(c["link"])["grade"], c["expect_grade"], c["id"])
        disagree = [c["id"] for c in rows if c["spec_grade"] != c["expect_grade"]]
        self.assertEqual(disagree, ["nsanet-cause"])
    def test_every_planted_error_is_flagged_as_overstated_with_the_right_supported_grade(self):
        planted = [c for c in GOLD if c.get("planted")]
        self.assertEqual(len(planted), 8)
        for c in planted:
            a = J.audit_link(c["link"]); self.assertFalse(a["ok"], c["id"]); self.assertEqual(a["kind"], "overstated", c["id"]); self.assertEqual(a["judged"], c["expect_grade"], c["id"])
    def test_a_link_graded_as_the_judge_supports_it_passes_and_a_weaker_grade_is_only_a_note(self):
        nsa = next(c for c in GOLD if c["id"] == "nsanet-cause")["link"]; self.assertTrue(J.audit_link(nsa)["ok"]); self.assertEqual(J.audit_link(nsa)["kind"], "match")
        ms = next(c for c in GOLD if c["id"] == "ms-cause")["link"]; weak = dict(ms, grade="stated"); a = J.audit_link(weak); self.assertTrue(a["ok"]); self.assertEqual(a["kind"], "understated")
        low = dict(ms, grade="inferred"); self.assertEqual(J.audit_link(low)["kind"], "understated"); self.assertTrue(J.audit_link(low)["ok"])

class Rules(unittest.TestCase):
    def test_social_and_context_rows_never_raise_a_grade(self):
        link = {"layer": "cause", "grade": "inferred", "has_control": False, "sources": [{"signal_id": 1, "speaker": "x", "speaker_kind": "operator", "source_kind": "social", "relation": "states", "asserts": "a"},
                                                                                   {"signal_id": 2, "speaker": "y", "speaker_kind": "operator", "source_kind": "official", "relation": "context", "asserts": None}]}
        self.assertEqual(J.judge_link(link)["grade"], "inferred")
    def test_two_official_parties_agreeing_confirm_a_driver(self):
        link = {"layer": "driver", "grade": "confirmed", "has_control": False, "sources": [{"signal_id": 1, "speaker": "A", "speaker_kind": "operator", "source_kind": "official", "relation": "states", "asserts": "x"},
                                                                                       {"signal_id": 2, "speaker": "B", "speaker_kind": "regulator", "source_kind": "official", "relation": "states", "asserts": "x"}]}
        self.assertEqual(J.judge_link(link)["grade"], "confirmed"); self.assertTrue(J.audit_link(link)["ok"])
    def test_the_summary_words_each_overstated_link_for_the_approver(self):
        c = next(c for c in GOLD if c["id"] == "planted-faa-settled"); r = J.audit([dict(c["link"], who="FAA", link_id=4)]); s = J.summary(r)
        self.assertEqual((s["audited"], s["overstated"]), (1, 1)); self.assertIn("FAA cause is graded confirmed but its sources support disputed", s["blocks"][0])

class InTheGate(unittest.TestCase):
    def facts(self, links):
        import test_rca as T
        f = T.july(); f["links"] = links; return f
    def test_the_gate_removes_publish_when_a_link_is_graded_above_its_evidence_and_keeps_it_otherwise(self):
        good = next(c for c in GOLD if c["id"] == "jul-cause")["link"]; bad = next(c for c in GOLD if c["id"] == "planted-faa-settled")["link"]
        self.assertIn(R.PUBLISH, R.gate(self.facts([dict(good, who="OpenAI / Hugging Face", link_id=16)]), "alice")["allowed_actions"])
        g = R.gate(self.facts([dict(bad, who="FAA", link_id=4)]), "alice")
        self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(any("FAA cause is graded confirmed" in b for b in g["blocks"]))
        self.assertIn("grades_match_the_evidence", [c["rule"] for c in g["checks"] if not c["ok"]])
    def test_facts_without_links_are_not_audited_and_do_not_block(self):
        import test_rca as T
        g = R.gate(T.july(), "alice"); c = next(c for c in g["checks"] if c["rule"] == "grades_match_the_evidence"); self.assertTrue(c["ok"]); self.assertIn("not audited", c["detail"])

if __name__ == "__main__": unittest.main()
