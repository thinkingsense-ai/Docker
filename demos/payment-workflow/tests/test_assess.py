"""The risk-assessment workflow: rules gate, proposal, digest, register row, facts SQL and the gateway mapping. No Temporal and no database needed."""
import json, os, re, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import assess_rules as R, assess_facts, register_write as A, gateway_map as M, recommend
GOLD = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "priority_gold.json")))["cases"]
QUESTION = json.load(open(os.path.join(HERE, "..", "..", "it-risk-estate", "demo-questions-priorities.json")))[0]["referenceSql"]
REGISTER_SQL = open(os.path.join(HERE, "..", "..", "it-risk-register", "seed-register-postgres.sql")).read()


def facts_for(name, case=0, exposure=None, register=None):
    t = GOLD[case]["answer"]; cols = t["columns"]; i = [r[0] for r in t["rows"]].index(name)
    return {"system_id": i + 1, "table": {"columns": cols, "rows": [t["rows"][i]]}, "register": register,
            "exposure": exposure or {"assessed": False, "reason": "the estate exposure rating is off on this stack"}}


class Gate(unittest.TestCase):
    def test_the_domain_controllers_are_rated_critical_and_need_two_people(self):
        g = R.gate(facts_for("Domain controllers"), "alice")
        self.assertEqual(g["proposal"]["rating"], "Critical"); self.assertEqual(g["approvals_required"], 2)
        self.assertEqual(g["allowed_actions"], [R.RECORD, R.HOLD]); self.assertEqual(g["blocks"], [])
        self.assertEqual(g["proposal"]["category"], "CR.AVM.PATCH")
    def test_a_high_rating_needs_one_person(self):
        g = R.gate(facts_for("Payment gateway (production)"), "alice")
        self.assertEqual(g["proposal"]["rating"], "High"); self.assertEqual(g["approvals_required"], 1); self.assertEqual(g["proposal"]["category"], "CR.TMF.RRT")
    def test_the_initiator_and_ai_identities_never_approve(self):
        g = R.gate(facts_for("Domain controllers"), "alice")
        for who in ("alice", "Claude", "policy-auto"): self.assertFalse(R.may_approve(who, [], g), who)
        self.assertTrue(R.may_approve("bob", [], g)); self.assertFalse(R.may_approve("bob", ["Bob"], g))
    def test_a_row_the_rules_cannot_rate_only_allows_a_hold(self):
        f = {"system_id": 1, "table": {"columns": ["system", "tier"], "rows": [["A", "1"]]}, "register": None, "exposure": {"assessed": False, "reason": "x"}}
        g = R.gate(f, "alice"); self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(g["blocks"]); self.assertIsNone(g["proposal"])
    def test_a_critical_exposure_lifts_a_system_in_scope_and_says_so(self):
        ex = {"assessed": True, "level": "Critical", "sentence": "Critical: set by questions 4 and 5."}
        p = R.gate(facts_for("Branch file servers", exposure=ex), "alice")["proposal"]
        self.assertEqual(p["rating"], "High"); self.assertTrue(p["lifted"]); self.assertEqual(R.gate(facts_for("Branch file servers"), "alice")["proposal"]["rating"], "Medium")
    def test_the_register_row_already_there_is_noted_not_replaced(self):
        cur = {"rating": "High", "set_by": "raj.second", "assessed_at": "2026-11-21", "node_id": "CR.TMF.CHG"}
        g = R.gate(facts_for("Payment gateway (production)", register=cur), "alice")
        self.assertTrue(any("sit after it" in n and "unchanged" in n for n in g["notes"]))
    def test_the_digest_changes_when_the_data_or_the_exposure_changes(self):
        f = facts_for("Domain controllers"); p = R.proposal(f); d = R.assessment_digest(f, p)
        f2 = json.loads(json.dumps(f)); f2["table"]["rows"][0][f2["table"]["columns"].index("open_patches")] = "2"
        self.assertNotEqual(d, R.assessment_digest(f2, R.proposal(f2)))
        f3 = dict(f, exposure={"assessed": True, "level": "Critical", "sentence": "x"}); self.assertNotEqual(d, R.assessment_digest(f3, R.proposal(f3)))
    def test_category_follows_the_driving_finding(self):
        self.assertEqual(R.category_for({"credentials_wide": "1"}), "CR.TMF.DEC")
        self.assertEqual(R.category_for({"untested_changes": "1"}), "CR.TMF.CHG")
        self.assertEqual(R.category_for({"recovery_result": "never tested"}), "CR.TMF.RRT")
        self.assertEqual(R.category_for({"end_of_support": "2026-12-31"}), "CR.TMF.LEG")
        self.assertEqual(R.category_for({}), "CR.TMF")
    def test_every_category_exists_in_the_register_taxonomy(self):
        for node in ("CR.AVM.PATCH", "CR.TMF.DEC", "CR.TMF.CHG", "CR.TMF.RRT", "CR.TMF.LEG", "CR.TMF"): self.assertIn("('%s'," % node, REGISTER_SQL)
    def test_the_evidence_is_plain_text_built_from_the_row(self):
        e = R.control_evidence(dict(zip(GOLD[0]["answer"]["columns"], GOLD[0]["answer"]["rows"][2])))
        self.assertIn("open patches: 1 (known-exploited 1, highest exploit score 0.912)", e); self.assertIn("dependants: 4", e)
    def test_the_recommendation_is_rules_only(self):
        g = R.gate(facts_for("Domain controllers"), "alice"); r = recommend.recommend(facts_for("Domain controllers"), g, "assessment")
        self.assertEqual((r["recommendation"], r["model"]), (R.RECORD, "rules-only"))
        bad = R.gate({"system_id": 1, "table": {"columns": ["system"], "rows": [["A"]]}, "register": None, "exposure": {}}, "a")
        self.assertEqual(recommend.recommend({}, bad, "assessment")["recommendation"], R.HOLD)


class Register(unittest.TestCase):
    def action(self):
        f = facts_for("Domain controllers"); g = R.gate(f, "alice"); p = g["proposal"]
        return {"type": "record", "system": "register", "system_id": 3, "idempotency_key": "assess-3", "item_type": "system", "item_ref": p["system"], "rating": p["rating"], "category": p["category"],
                "likelihood": p["likelihood"], "impact": p["impact"], "proposal_digest": R.assessment_digest(f, p), "approvers": ["bob", "carol"]}, p
    def test_the_row_carries_the_approvers_the_run_and_the_digest_and_is_second_line(self):
        a, p = self.action(); row = A.build_register_row(a, p)
        self.assertEqual((row["set_by"], row["role"], row["run_id"], row["rating"], row["node_id"]), ("bob, carol", "second", "assess-3", "Critical", "CR.AVM.PATCH"))
        self.assertEqual(row["evidence_digest"], a["proposal_digest"]); self.assertTrue(row["control_evidence"])
    def test_a_hold_writes_nothing_and_dry_run_writes_nothing(self):
        a, p = self.action(); self.assertEqual(A.write(dict(a, type="hold"), p)["mode"], "no-write")
        old = A.REGISTER_WRITE; A.REGISTER_WRITE = "dry-run"
        try:
            out = A.write(a, p)
            self.assertEqual(out["mode"], "dry-run"); self.assertEqual(out["would_send"]["body"]["set_by"], "bob, carol")
        finally: A.REGISTER_WRITE = old
    def test_the_register_table_matches_the_row_the_write_builds(self):
        for col in ("item_type", "item_ref", "node_id", "rating", "likelihood_band", "impact_band", "likelihood_inputs", "impact_inputs", "control_evidence", "set_by", "role", "run_id", "evidence_digest"):
            self.assertIn(col, REGISTER_SQL); self.assertIn(col, A.INSERT)
        self.assertIn("CREATE UNIQUE INDEX assessments_one_per_run ON register.assessments (run_id)", REGISTER_SQL)
        self.assertIn("ON CONFLICT (run_id) WHERE run_id IS NOT NULL DO NOTHING", A.INSERT)


class Facts(unittest.TestCase):
    def test_the_sql_is_the_approved_question_with_the_prefix_and_one_system(self):
        self.assertEqual(assess_facts.SQL.format(p="pg.", where=""), QUESTION)
        one = assess_facts.SQL.format(p="pg.", where="WHERE s.system_id = 3 ")
        self.assertIn("WHERE s.system_id = 3 ORDER BY", one)
    def test_the_priorities_question_has_no_window_function(self): self.assertNotRegex(QUESTION.upper(), r"\bOVER\s*\(")


class Mapping(unittest.TestCase):
    def test_the_definition_and_run_id(self):
        self.assertEqual(M.run_id("3", "risk-assessment"), "assess-3"); self.assertEqual(M.definition_of("assess-3"), "risk-assessment"); self.assertTrue(M.RUN_ID.match("assess-12"))
        self.assertEqual(M.check_start({"definition": "risk-assessment", "key": "3", "initiator": "alice"})["id"], "assess-3")
        with self.assertRaises(M.Refusal): M.run_id("x", "risk-assessment")
    def test_a_run_reads_as_a_server_run_with_the_proposal(self):
        f = facts_for("Domain controllers"); g = R.gate(f, "alice")
        st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "gate": g, "approvals": [], "approvals_required": g["approvals_required"], "recommendation": {"recommendation": "record", "reasons": ["r"], "model": "rules-only"}, "facts_summary": {"proposed_rating": "Critical"}}
        run = M.to_run("assess-3", st, 1, "t", "t")
        self.assertEqual((run["definition"], run["key"], run["requiredApprovals"], run["stage"]), ("risk-assessment", "3", 2, "awaiting_approval")); self.assertEqual(run["evidence"]["proposed_rating"], "Critical")
    def test_precheck_refuses_the_initiator_and_a_stale_hash(self):
        g = R.gate(facts_for("Domain controllers"), "alice"); st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "gate": g, "approvals": []}
        with self.assertRaises(M.Refusal) as e: M.precheck(st, {"type": "approve", "user": "alice", "payloadHash": "h"})
        self.assertEqual(e.exception.code, "initiator_cannot_approve")
        with self.assertRaises(M.Refusal) as e: M.precheck(st, {"type": "approve", "user": "bob", "payloadHash": "stale"})
        self.assertEqual(e.exception.code, "payload_hash_mismatch")
    def test_the_manifest_lists_the_definition(self):
        mf = json.load(open(os.path.join(HERE, "..", "manifest.gateway.json")))["definitions"]
        d = next(x for x in mf if x["id"] == "risk-assessment"); self.assertEqual((d["keyField"], d["entity"]), ("system_id", "system"))

if __name__ == "__main__": unittest.main()
