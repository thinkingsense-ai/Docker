"""The major-incident decision: gate, preview of the clocks it would start, digest, the register row and the gateway mapping. No Temporal and no database needed."""
import json, os, sys, unittest
from datetime import datetime, timezone
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import major_rules as R, major_facts, register_write as W, gateway_map as M, clock_rules as C
with open(os.path.join(HERE, "..", "..", "it-risk-register", "clocks_gold.json")) as f: RULES = json.load(f)["cases"][0]["rules"]
with open(os.path.join(HERE, "..", "..", "it-risk-register", "seed-register-postgres.sql")) as f: SEED = f.read()
NOW = datetime(2026, 11, 21, 9, 0, 0, tzinfo=timezone.utc)


def facts(declared=("DORA", "MAS"), decision=None, incident=True):
    return {"incident": {"incident_id": 1, "title": "Payment gateway slowdown", "system_id": 1, "awareness_at": "2026-11-20 08:15:00.0", "summary": "x"} if incident else {},
            "decision": decision, "profile": [{"regulator": r, "declared": "t" if r in declared else "f"} for r in ("DORA", "MAS")], "rules": RULES + [r for r in []]}


class Gate(unittest.TestCase):
    def test_a_fresh_incident_can_be_recorded_by_one_person_and_previews_the_clocks(self):
        g = R.gate(facts(declared=("DORA",)), "alice", NOW)
        self.assertEqual((g["allowed_actions"], g["approvals_required"], g["blocks"]), ([R.RECORD, R.HOLD], 1, []))
        self.assertTrue(any(n.startswith("DORA: Initial notification would be due 2026-11-21T08:15:00Z") for n in g["notes"]))     # awareness + 24 h (08:15) comes before 09:00 + 4 h, so the awareness limit governs
        self.assertTrue(any("the latest possible" in n for n in g["notes"]))
    def test_no_rule_decides_major_and_the_note_says_so(self):
        self.assertTrue(any("No rule decides that an incident is major" in n for n in R.gate(facts(), "alice", NOW)["notes"]))
        self.assertEqual(R.gate(facts(), "alice", NOW)["regimes"], ["DORA", "MAS"])
    def test_an_incident_already_recorded_cannot_be_recorded_again(self):
        g = R.gate(facts(decision={"classified_at": "2026-11-20 10:00:00", "set_by": "bob"}), "alice", NOW)
        self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(any("already recorded as major (by bob)" in b for b in g["blocks"]))
    def test_no_declared_regulator_means_nothing_to_start(self):
        g = R.gate(facts(declared=()), "alice", NOW); self.assertEqual(g["allowed_actions"], [R.HOLD]); self.assertTrue(any("no regulator is declared" in b for b in g["blocks"]))
    def test_a_missing_incident_blocks(self):
        self.assertTrue(R.gate(facts(incident=False), "alice", NOW)["blocks"])
    def test_the_initiator_and_ai_identities_never_approve(self):
        g = R.gate(facts(), "alice", NOW)
        for who in ("alice", "Claude", "policy-auto"): self.assertFalse(R.may_approve(who, [], g), who)
        self.assertTrue(R.may_approve("bob", [], g)); self.assertFalse(R.may_approve("bob", ["Bob"], g))
    def test_the_digest_changes_when_the_incident_the_regulators_or_the_rules_change(self):
        d = R.proposal_digest(facts()); self.assertEqual(d, R.proposal_digest(facts()))
        self.assertNotEqual(d, R.proposal_digest(facts(declared=("DORA",))))
        f = facts(); f["incident"]["awareness_at"] = "2026-11-20 08:16:00.0"; self.assertNotEqual(d, R.proposal_digest(f))
        f = facts(); f["rules"] = [dict(r, hours="5") if r["rule_id"] == "dora-initial" else r for r in f["rules"]]; self.assertNotEqual(d, R.proposal_digest(f))


class Register(unittest.TestCase):
    def action(self): return {"incident_id": 1, "regimes": ["DORA", "MAS"], "idempotency_key": "major-1", "proposal_digest": R.proposal_digest(facts()), "approvers": ["bob"]}
    def test_the_row_carries_the_approver_the_run_the_digest_and_the_time(self):
        row = W.build_major_row(self.action(), "2026-11-21T09:00:00+00:00")
        self.assertEqual((row["set_by"], row["role"], row["run_id"], row["regimes"], row["classified_at"]), ("bob", "second", "major-1", "DORA,MAS", "2026-11-21T09:00:00+00:00"))
    def test_dry_run_adds_nothing(self):
        old = W.REGISTER_WRITE; W.REGISTER_WRITE = "dry-run"
        try: out = W.write_major(self.action(), "2026-11-21T09:00:00+00:00"); self.assertEqual(out["mode"], "dry-run"); self.assertEqual(out["would_send"]["body"]["incident_id"], 1)
        finally: W.REGISTER_WRITE = old
    def test_the_table_matches_the_insert_and_refuses_changes(self):
        for col in ("incident_id", "classified_at", "regimes", "set_by", "role", "run_id", "evidence_digest"): self.assertIn(col, SEED); self.assertIn(col, W.MAJOR_INSERT)
        self.assertIn("BEFORE UPDATE OR DELETE ON register.major_incident_decisions", SEED); self.assertIn("BEFORE TRUNCATE ON register.major_incident_decisions", SEED)
        self.assertIn("CREATE UNIQUE INDEX major_decision_one_per_incident", SEED); self.assertIn("CHECK (decision = 'major')", SEED)
    def test_the_reload_drops_the_new_tables(self):
        drop = SEED.split("DROP TABLE IF EXISTS", 1)[1].split(";", 1)[0]
        for t in ("major_incident_decisions", "firm_incidents", "firm_profile", "notification_rules"): self.assertIn("register." + t, drop)


class Mapping(unittest.TestCase):
    def test_the_definition_and_run_id(self):
        self.assertEqual(M.run_id("2", "major-incident"), "major-2"); self.assertEqual(M.definition_of("major-2"), "major-incident"); self.assertTrue(M.RUN_ID.match("major-12"))
        with self.assertRaises(M.Refusal): M.run_id("x", "major-incident")
    def test_a_run_reads_as_a_server_run_without_a_recommendation(self):
        g = R.gate(facts(), "alice", NOW)
        st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "gate": g, "approvals": [], "approvals_required": 1, "facts_summary": {"incident": "Payment gateway slowdown"}}
        run = M.to_run("major-1", st, 1, "t", "t"); self.assertEqual((run["definition"], run["key"], run["recommendation"]), ("major-incident", "1", None)); self.assertEqual(run["evidence"]["incident"], "Payment gateway slowdown")
    def test_precheck_refuses_the_initiator(self):
        g = R.gate(facts(), "alice", NOW); st = {"stage": "awaiting_approval", "initiator": "alice", "payload_hash": "h", "gate": g, "approvals": []}
        with self.assertRaises(M.Refusal) as e: M.precheck(st, {"type": "approve", "user": "alice", "payloadHash": "h"})
        self.assertEqual(e.exception.code, "initiator_cannot_approve")
    def test_the_manifest_lists_it(self):
        with open(os.path.join(HERE, "..", "manifest.gateway.json")) as f: mf = json.load(f)["definitions"]
        d = next(x for x in mf if x["id"] == "major-incident"); self.assertEqual((d["keyField"], d["entity"]), ("incident_id", "incident"))
    def test_the_facts_read_only_the_register_tables_with_the_stack_prefix(self):
        seen = []; old = major_facts._q; major_facts._q = lambda sql: (seen.append(sql) or [{"incident_id": 1, "title": "t", "awareness_at": "2026-11-20 08:15:00.0", "summary": "s"}])
        os.environ["MAJOR_TABLE_PREFIX"] = "pg."
        try: major_facts.gather(1)
        finally: major_facts._q = old; os.environ.pop("MAJOR_TABLE_PREFIX")
        self.assertEqual(len(seen), 4); self.assertTrue(all("pg.register." in s for s in seen)); self.assertTrue(all(s.lstrip().startswith("SELECT") for s in seen))

if __name__ == "__main__": unittest.main()
