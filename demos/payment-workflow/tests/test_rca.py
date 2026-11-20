"""python3 -m unittest discover -s demos/payment-workflow/tests     The incident-brief workflow (IT-risk root-cause analysis): rules gate, facts, recommender and the gateway mapping. No Temporal needed."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import rca_rules as R, rca_facts, recommend, gateway_map as M

def inc(op, grade, sources=1, cause="x"): return {"operator": op, "cause": cause, "grade": grade, "sources": sources}
def spk(op, kind): return {"operator": op, "speaker": "s", "speaker_kind": kind, "publisher": "p"}

def november():
    """The six November 2026 incidents as the sample data holds them (Leo's specification): four confirmed, the FAA disputed, United not named, NSANet confirmed on reporting."""
    return {"claim": {"claim_id": 1, "case_id": "nov-2026-cluster", "claim": "The November outages are AI hacking.", "verdict": "not_supported", "open_incidents": 2},
            "case_id": "nov-2026-cluster",
            "incidents": [inc("Microsoft 365", "confirmed"), inc("FAA", "disputed", 2), inc("JPMorgan Chase", "confirmed"), inc("United Airlines", "not_named"), inc("NSA (NSANet)", "confirmed"), inc("Apple", "confirmed")],
            "open_links": [{"layer": "driver", "grade": "inferred", "reason": "Our reasoning"}, {"layer": "root_condition", "grade": "to_be_tested", "reason": "Needs the firm's records"}],
            "controls": [{"owning_control": "Change management and pre-production testing", "owner_role": "Head of technology risk", "framework": "NIST CSF 2.0", "category": "PR.PS"}],
            "speakers": [spk("Microsoft 365", "operator"), spk("FAA", "regulator"), spk("JPMorgan Chase", "operator"), spk("NSA (NSANet)", "reporting"), spk("Apple", "operator")]}

def july():
    return {"claim": {"claim_id": 2, "case_id": "jul-2026-breakout", "claim": "x", "verdict": "insufficient_evidence", "open_incidents": 0}, "case_id": "jul-2026-breakout",
            "incidents": [inc("OpenAI / Hugging Face", "confirmed")], "open_links": [], "controls": [], "speakers": [spk("OpenAI / Hugging Face", "operator")]}

class Rules(unittest.TestCase):
    def test_the_verdict_names_every_open_incident(self):
        self.assertEqual(R.verdict_sentence(november()), "No official source attributes any of the 6 incidents to an attack, but FAA (disputed) and United Airlines (not named) are still open.")
    def test_november_holds_because_nsanet_is_confirmed_on_reporting(self):
        g = R.gate(november(), "alice")
        self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(any("NSA (NSANet)" in b for b in g["blocks"]))
    def test_july_may_be_published(self):
        g = R.gate(july(), "alice"); self.assertEqual(g["allowed_actions"], [R.PUBLISH, R.HOLD]); self.assertEqual(g["blocks"], [])
    def test_regrading_nsanet_as_stated_lets_november_publish(self):
        f = november(); f["incidents"][4]["grade"] = "stated"; self.assertIn(R.PUBLISH, R.gate(f)["allowed_actions"])
    def test_a_cause_without_a_source_blocks_publication_unless_inferred(self):
        f = july(); f["incidents"][0]["sources"] = 0; self.assertEqual(R.gate(f)["allowed_actions"], [R.HOLD])
        f["incidents"][0]["grade"] = "inferred"; self.assertIn(R.PUBLISH, R.gate(f)["allowed_actions"])
    def test_no_claim_means_nothing_to_publish(self):
        f = july(); f["claim"] = None; self.assertEqual(R.gate(f)["allowed_actions"], [R.HOLD])
    def test_the_initiator_and_ai_identities_never_approve(self):
        g = R.gate(july(), "alice")
        self.assertFalse(R.may_approve("alice", [], g)); self.assertFalse(R.may_approve("claude", [], g)); self.assertFalse(R.may_approve("Policy-Auto", [], g))
        self.assertTrue(R.may_approve("bob", [], g)); self.assertFalse(R.may_approve("bob", ["Bob"], g))
    def test_the_digest_changes_when_a_grade_changes(self):
        a = R.brief_digest(november()); f = november(); f["incidents"][1]["grade"] = "stated"
        self.assertNotEqual(a, R.brief_digest(f)); self.assertEqual(a, R.brief_digest(november()))

class Recommend(unittest.TestCase):
    def test_publish_when_the_rules_allow_it_and_hold_when_they_do_not(self):
        r = recommend.recommend(july(), R.gate(july(), "alice"), "incident"); self.assertEqual((r["recommendation"], r["model"]), ("publish", "rules-only"))
        r = recommend.recommend(november(), R.gate(november(), "alice"), "incident"); self.assertEqual(r["recommendation"], "hold"); self.assertTrue(r["reasons"])

class Facts(unittest.TestCase):
    def test_every_statement_is_a_governed_read_on_the_rca_schema_with_the_stack_prefix(self):
        seen = []
        def fake(sql):
            seen.append(sql)
            if "FROM pg.rca.claims" in sql: return [{"claim_id": 1, "case_id": "nov-2026-cluster", "claim": "c", "verdict": "not_supported", "open_incidents": 2, "note": ""}]
            if "GROUP BY" in sql: return [{"operator": "FAA", "cause": "x", "grade": "disputed", "sources": "2"}]
            return []
        os.environ["RCA_TABLE_PREFIX"] = "pg."; rca_facts.query = fake
        try: f = rca_facts.gather(1)
        finally: os.environ.pop("RCA_TABLE_PREFIX", None)
        self.assertEqual(f["incidents"][0]["sources"], 2); self.assertEqual(len(seen), 6); self.assertTrue(all(" rca." not in s.replace("pg.rca.", "") for s in seen))
    def test_an_unknown_claim_is_an_error_and_a_hostile_case_id_is_refused(self):
        rca_facts.query = lambda sql: []
        with self.assertRaises(RuntimeError): rca_facts.gather(9)
        rca_facts.query = lambda sql: [{"claim_id": 1, "case_id": "x'; drop", "claim": "c", "verdict": "supported", "open_incidents": 0, "note": ""}]
        with self.assertRaises(RuntimeError): rca_facts.gather(1)

class Addressing(unittest.TestCase):
    def test_connectors_are_added_after_from_and_join_only_when_configured(self):
        import facts
        sql = "SELECT a.name FROM risk.applications a JOIN security.vendors v ON v.vendor_id = a.vendor_id WHERE a.name = 'risk.x'"
        self.assertEqual(facts.addressed(sql, ""), sql)
        self.assertEqual(facts.addressed(sql, "risk=pg,security=mdb"), "SELECT a.name FROM pg.risk.applications a JOIN mdb.security.vendors v ON v.vendor_id = a.vendor_id WHERE a.name = 'risk.x'")

class Gateway(unittest.TestCase):
    def test_the_definition_and_run_id(self):
        self.assertEqual(M.run_id(1, M.RCA_DEFINITION), "rca-1"); self.assertEqual(M.definition_of("rca-1"), "incident-cluster-rca"); self.assertTrue(M.RUN_ID.match("rca-12"))
        self.assertEqual(M.check_start({"definition": "incident-cluster-rca", "key": "2", "initiator": "alice"})["id"], "rca-2")
    def test_a_run_reads_as_a_server_run(self):
        st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "approvals_required": 1, "gate": R.gate(november(), "alice"),
              "recommendation": {"recommendation": "hold", "reasons": ["r"], "model": "rules-only"}, "facts_summary": {"causes_confirmed": "4 of 6"}}
        r = M.to_run("rca-1", st, 1, "t0", "t1"); self.assertEqual((r["definition"], r["stage"], r["requiredApprovals"]), ("incident-cluster-rca", "awaiting_approval", 1))
        self.assertEqual(r["evidence"]["claim_id"], "1"); self.assertEqual(r["recommendation"]["action"], "hold")
    def test_precheck_refuses_the_initiator_and_a_stale_hash(self):
        st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "gate": R.gate(july(), "alice"), "approvals": []}
        with self.assertRaises(M.Refusal) as e: M.precheck(st, {"type": "approve", "user": "alice", "payloadHash": "h"})
        self.assertEqual(e.exception.code, "initiator_cannot_approve")
        with self.assertRaises(M.Refusal) as e: M.precheck(st, {"type": "approve", "user": "bob", "payloadHash": "old"})
        self.assertEqual(e.exception.code, "payload_hash_mismatch"); self.assertIsNone(M.precheck(st, {"type": "approve", "user": "bob", "payloadHash": "h"}))

if __name__ == "__main__": unittest.main()
