"""python3 -m unittest discover -s demos/payment-workflow/tests     The IT-risk vulnerability-exception workflow: rules, facts, recommender fallback and the gateway mapping. No Temporal needed."""
import os, sys, unittest
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import it_rules as R, it_facts, recommend, gateway_map as M

TODAY = date(2026, 11, 19)
def d(n): return str(date.fromordinal(TODAY.toordinal() - n))

def treasury_workstation():
    """CVE-2026-0871 on Treasury Workstation, as the sample data seeds it (relative to the day it is loaded)."""
    return {"vulnerability": {"vuln_id": 6, "app_id": 12, "cve": "CVE-2026-0871", "cvss": 9.9, "severity": "Critical", "found_on": d(70), "patch_due": d(56), "patched_on": None},
            "application": {"app_id": 12, "application": "Treasury Workstation", "hosting": "On-prem", "vendor_id": 4},
            "service": {"service_id": 6, "service": "Treasury Management", "tier": 1, "owner": "Aisha Bello", "rto_minutes": 45, "revenue_per_hour_usd": 320000},
            "vendor": {"vendor_id": 4, "name": "Helix Treasury Software", "tier": 1, "last_assessed": d(520), "assessment_rating": "High"},
            "incidents": [{"incident_id": 17, "started_on": d(20), "duration_minutes": 64, "severity": "SEV1"}, {"incident_id": 19, "started_on": d(70), "duration_minutes": 15, "severity": "SEV3"}],
            "risks": [{"risk_id": 6, "title": "Treasury software vendor not assessed in over a year", "category": "Third party", "residual_score": 12, "max_residual_score": 12}],
            "controls": [{"control_id": 9, "title": "Annual third-party security assessment", "control_type": "Detective", "risk_id": 6, "last_tested": d(520), "test_every_days": 365, "last_result": "Ineffective"}],
            "other_open_critical_on_service": []}

def collaboration_suite():
    """CVE-2026-1188, High, due in 20 days, on a tier-3 service with a short outage and nothing against it."""
    return {"vulnerability": {"vuln_id": 14, "cve": "CVE-2026-1188", "cvss": 8.4, "severity": "High", "patch_due": d(-20), "patched_on": None},
            "application": {"app_id": 16, "application": "Collaboration Suite", "vendor_id": 1}, "service": {"service_id": 8, "service": "Document Management", "tier": 3, "owner": "Ravi Menon", "rto_minutes": 960},
            "vendor": {"name": "Northwind Cloud Services", "tier": 1, "last_assessed": d(120)}, "incidents": [{"started_on": d(15), "duration_minutes": 55, "severity": "SEV3"}],
            "risks": [{"title": "Archive hardware degradation", "category": "Technology", "residual_score": 6, "max_residual_score": 12}], "controls": []}


class Rules(unittest.TestCase):
    def test_a_critical_flaw_on_a_tier1_service_with_a_recent_long_outage_cannot_be_excepted(self):
        g = R.gate(treasury_workstation(), "alice", TODAY)
        self.assertEqual(g["allowed_actions"], ["remediate", "escalate"]); self.assertEqual(g["approvals_required"], 2)
        text = " | ".join(g["blocks"])
        for must in ("56 days past its patch deadline", "64 minutes", "45-minute recovery objective", "Helix Treasury Software was last assessed 520 days ago"): self.assertIn(must, text)
        self.assertNotIn("15 minutes", text)                                    # the 70-day-old 15-minute outage is inside the window but within the objective

    def test_a_clean_low_tier_finding_allows_an_exception_and_needs_one_approver(self):
        g = R.gate(collaboration_suite(), "alice", TODAY)
        self.assertEqual(g["blocks"], []); self.assertEqual(g["allowed_actions"], ["remediate", "grant_exception", "escalate"]); self.assertEqual(g["approvals_required"], 1)

    def test_an_outage_older_than_the_window_does_not_block(self):
        f = collaboration_suite(); f["incidents"] = [{"started_on": d(200), "duration_minutes": 5000, "severity": "SEV1"}]
        self.assertEqual(R.gate(f, "a", TODAY)["blocks"], [])

    def test_risk_above_appetite_and_an_overdue_preventive_control_block(self):
        f = collaboration_suite()
        f["risks"] = [{"title": "R", "category": "Cyber", "residual_score": 16, "max_residual_score": 9}]
        f["controls"] = [{"title": "Patch in 14 days", "control_type": "Preventive", "last_tested": d(100), "test_every_days": 90, "last_result": "Effective"}]
        t = " | ".join(R.gate(f, "a", TODAY)["blocks"]); self.assertIn("residual score 16 against the board's appetite of 9", t); self.assertIn("overdue for testing", t)

    def test_a_detective_control_never_blocks_by_itself(self):
        f = collaboration_suite(); f["controls"] = [{"title": "Scan", "control_type": "Detective", "last_tested": d(900), "test_every_days": 30, "last_result": "Ineffective"}]
        self.assertEqual(R.gate(f, "a", TODAY)["blocks"], [])

    def test_a_patched_vulnerability_leaves_only_escalation(self):
        f = collaboration_suite(); f["vulnerability"]["patched_on"] = d(2)
        g = R.gate(f, "a", TODAY); self.assertEqual(g["allowed_actions"], ["escalate"]); self.assertIn("already patched", g["blocks"][0])

    def test_the_initiator_and_automation_may_not_approve_and_one_person_counts_once(self):
        g = R.gate(treasury_workstation(), "alice", TODAY)
        self.assertFalse(R.may_approve("alice", [], g)); self.assertFalse(R.may_approve("Treasury-Agent", [], g)); self.assertFalse(R.may_approve("claude", [], g))
        self.assertTrue(R.may_approve("bob", [], g)); self.assertFalse(R.may_approve("BOB", ["bob"], g)); self.assertFalse(R.may_approve("", [], g))

    def test_dates_arrive_as_text_or_dates(self):
        self.assertEqual(R.days_between("2026-11-19T00:00:00", date(2026, 11, 9)), 10); self.assertIsNone(R.to_date(None)); self.assertIsNone(R.to_date(""))


class Facts(unittest.TestCase):
    def test_every_read_is_one_governed_query_and_ids_are_integers(self):
        seen = []
        def fake(sql):
            seen.append(sql)
            if "FROM security.vulnerabilities WHERE vuln_id" in sql: return [{"vuln_id": 6, "app_id": 12, "cve": "C", "cvss": 9.9, "severity": "Critical", "found_on": "x", "patch_due": "x", "patched_on": None}]
            if "FROM risk.applications a JOIN" in sql: return [{"app_id": 12, "application": "TW", "hosting": "On-prem", "vendor_id": 4, "service_id": 6, "service": "TM", "tier": 1, "owner": "o", "rto_minutes": 45, "revenue_per_hour_usd": 1}]
            if "risk.risk_register" in sql: return [{"risk_id": 6, "title": "t", "category": "c", "owner": "o", "residual_score": 1, "status": "Open", "max_residual_score": 2}]
            return []
        it_facts.query = fake
        try:
            f = it_facts.gather("6")
            with self.assertRaises(ValueError): it_facts.gather("6; DROP TABLE x")
        finally: it_facts.query = it_facts.base.query
        self.assertEqual(f["service"]["service"], "TM"); self.assertEqual(f["vendor"], None)
        self.assertTrue(all("/api" not in q for q in seen)); self.assertTrue(any("risk_id IN (6)" in q for q in seen))
        self.assertFalse(any("mdb." in q or "pg." in q for q in seen))
        self.assertEqual(sum(1 for q in seen if "security." in q and "risk." in q), 0, "no statement joins the two systems")

    def test_an_unknown_vulnerability_is_an_error_not_an_empty_run(self):
        it_facts.query = lambda sql: []
        try: self.assertRaises(RuntimeError, it_facts.gather, 999)
        finally: it_facts.query = it_facts.base.query


class Recommender(unittest.TestCase):
    def setUp(self): self._k = {k: os.environ.pop(k, None) for k in ("OMNIGATE_LLM_API_KEY", "ANTHROPIC_API_KEY")}
    def tearDown(self): [os.environ.__setitem__(k, v) for k, v in self._k.items() if v]

    def test_without_a_key_blocked_cases_get_remediate_and_clean_cases_an_exception(self):
        f = treasury_workstation(); out = recommend.recommend(f, R.gate(f, "alice", TODAY), "vulnerability")
        self.assertEqual((out["recommendation"], out["model"]), ("remediate", "rules-only")); self.assertTrue(out["reasons"])
        c = collaboration_suite(); self.assertEqual(recommend.recommend(c, R.gate(c, "alice", TODAY), "vulnerability")["recommendation"], "grant_exception")

    def test_a_model_choosing_a_blocked_action_is_changed_to_escalate(self):
        f = treasury_workstation(); old = recommend._ask_model
        recommend._ask_model = lambda facts, gate, domain="payment": {"recommendation": "grant_exception", "confidence": 0.9, "reasons": ["fine"]}
        os.environ["OMNIGATE_LLM_API_KEY"] = "x"
        try: out = recommend.recommend(f, R.gate(f, "alice", TODAY), "vulnerability")
        finally: recommend._ask_model = old; os.environ.pop("OMNIGATE_LLM_API_KEY")
        self.assertEqual(out["recommendation"], "escalate"); self.assertIn("rules do not allow", out["reasons"][0])

    def test_the_vulnerability_prompt_is_about_vulnerabilities(self):
        self.assertIn("remediate|grant_exception|escalate", recommend.PROMPTS["vulnerability"]); self.assertIn("payment", recommend.PROMPTS["payment"])


class GatewayMapping(unittest.TestCase):
    def test_vulnerability_runs_have_their_own_id_and_definition(self):
        self.assertEqual(M.run_id(" 6 ", M.IT_DEFINITION), "vuln-6"); self.assertEqual(M.run_id("35"), "payment-35")
        for bad in ("", "x", "6; drop", "1" * 13): self.assertRaises(M.Refusal, M.run_id, bad, M.IT_DEFINITION)
        self.assertTrue(M.RUN_ID.match("vuln-6")); self.assertFalse(M.RUN_ID.match("vuln-6/x")); self.assertFalse(M.RUN_ID.match("vulnerability-6"))
        spec = M.check_start({"definition": "vulnerability-exception", "key": "6", "initiator": "alice"})
        self.assertEqual((spec["id"], spec["definition"]), ("vuln-6", "vulnerability-exception"))
        self.assertEqual(M.check_start({"definition": "payment-exception", "key": "35", "initiator": "alice"})["id"], "payment-35")
        with self.assertRaises(M.Refusal) as c: M.check_start({"definition": "other", "key": "1", "initiator": "a"})
        self.assertEqual(c.exception.code, "unknown_definition")

    def test_a_run_card_shows_the_facts_rules_recommendation_and_a_dry_run(self):
        f = treasury_workstation(); g = R.gate(f, "alice", TODAY)
        st = {"stage": "done", "initiator": "alice", "gate": g, "approvals_required": 2, "payload_hash": "ab" * 32, "approvals": [{"approver": "bob", "at": "t"}, {"approver": "carol", "at": "t"}], "ignored": [],
              "recommendation": {"recommendation": "remediate", "reasons": ["r1", "r2"], "model": "rules-only"}, "facts_summary": {"cve": "CVE-2026-0871", "cvss": 9.9, "vendor": "Helix Treasury Software"},
              "write_back": {"mode": "dry-run", "would_send": {"method": "POST", "path": "/grc/remediation-requests"}}}
        run = M.to_run("vuln-6", st, 2, "c", "u")
        self.assertEqual((run["definition"], run["key"], run["stage"]), ("vulnerability-exception", "6", "written_back"))
        self.assertEqual(run["evidence"]["vuln_id"], "6"); self.assertEqual(run["evidence"]["cve"], "CVE-2026-0871")
        self.assertEqual(run["writeBack"]["status"], "simulated"); self.assertEqual(run["writeBack"]["call"], "POST /grc/remediation-requests"); self.assertEqual(run["requiredApprovals"], 2)
        self.assertEqual(M.to_run("payment-35", {"stage": "facts"}, 2)["definition"], "payment-exception")

    def test_precheck_uses_the_runs_own_exclusions(self):
        g = R.gate(treasury_workstation(), "alice", TODAY)
        st = {"stage": "awaiting_approval", "initiator": "alice", "gate": g, "payload_hash": "ab" * 32, "approvals": []}
        with self.assertRaises(M.Refusal) as c: M.precheck(st, {"type": "approve", "user": "alice", "payloadHash": "ab" * 32})
        self.assertEqual(c.exception.code, "initiator_cannot_approve")
        with self.assertRaises(M.Refusal) as c: M.precheck(st, {"type": "approve", "user": "bob", "payloadHash": "00"})
        self.assertEqual(c.exception.code, "payload_hash_mismatch")
        self.assertIsNone(M.precheck(st, {"type": "approve", "user": "bob", "payloadHash": "ab" * 32}))


class Activities(unittest.TestCase):
    def test_the_write_back_is_always_a_dry_run_with_the_exact_call(self):
        try: import activities as A
        except ImportError: self.skipTest("temporalio is not installed")
        a = {"type": "grant_exception", "system": "grc", "vuln_id": 14, "cve": "CVE-2026-1188", "service_id": 8, "idempotency_key": "vuln-14", "payload_hash": "h", "approvers": ["bob"]}
        os.environ["WRITE_BACK"] = "live"
        r = A.it_write_back(a); self.assertEqual(r["mode"], "dry-run"); self.assertEqual(r["would_send"]["path"], "/grc/exceptions"); self.assertEqual(r["would_send"]["body"]["valid_days"], 30)
        self.assertEqual(A.build_it_call(dict(a, type="remediate"))["path"], "/grc/remediation-requests")


if __name__ == "__main__": unittest.main()
