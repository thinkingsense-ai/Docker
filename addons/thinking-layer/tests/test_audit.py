"""The audit reader: chain verification, summaries, filters and the export. Pure; no server. A tampered or reordered line must be caught."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit


def chain(bodies):
    prev, out = "genesis", []
    for b in bodies:
        h = audit.entry_hash(prev, b); out.append({"prev": prev, "body": b, "hash": h}); prev = h
    return out


def ap(*names): return [{"approver": n, "at": "2026-11-21T10:%02d:00+00:00" % i} for i, n in enumerate(names)]


BODIES = [
    {"decision_id": "payment-35", "payment_id": 35, "started_at": "2026-11-18T09:00:00+00:00", "outcome": "release approved by bob, carol: dry-run", "approvals": ap("bob", "carol"), "action": {"type": "release", "payload_hash": "ph1"}, "write_back": {"mode": "dry-run", "would_send": {"path": "/payments/35/release"}}, "facts": {"invoice": "x"}},
    {"decision_id": "assess-3", "definition": "risk-assessment", "started_at": "2026-11-21T09:00:00+00:00", "outcome": "record approved by bob, carol: live", "approvals": ap("bob", "carol"),
     "rules": {"proposal": {"category": "CR.AVM.PATCH", "rating": "Critical"}}, "action": {"type": "record", "proposal_digest": "d3"}, "write_back": {"mode": "live", "sent": {"path": "register.assessments #4"}}, "recommendation": {"recommendation": "record"}},
    {"decision_id": "rca-1", "definition": "incident-cluster-rca", "started_at": "2026-11-20T09:00:00+00:00", "outcome": "declined by carol", "approvals": [], "rejection": {"approver": "carol", "reason": "Sent back: x", "at": "2026-11-20T11:00:00+00:00"},
     "facts": {"controls": [{"owning_control": "Change management and pre-production testing"}]}, "action": {"type": "hold", "brief_digest": "b1"}},
    {"decision_id": "major-1", "definition": "major-incident", "started_at": "2026-11-21T15:00:00+00:00", "outcome": "recorded as major by bob: live", "approvals": ap("bob"), "rules": {"regimes": ["DORA", "MAS"]}, "action": {"type": "record", "proposal_digest": "m1"}},
    {"decision_id": "vuln-6", "definition": "vulnerability-exception", "started_at": "2026-11-19T09:00:00+00:00", "outcome": "no decision before the deadline: escalated", "approvals": []},
    {"decision_id": "payment-9", "payment_id": 9, "started_at": "2026-11-17T09:00:00+00:00", "outcome": "escalated to a person", "approvals": []},
]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.path = os.path.join(self.d.name, "decisions.jsonl"); self.write(chain(BODIES))
    def tearDown(self): self.d.cleanup()
    def write(self, entries):
        with open(self.path, "w") as f: f.write("".join(json.dumps(e) + "\n" for e in entries))


class Chain(Fixture):
    def test_an_intact_chain_verifies_and_reports_its_head(self):
        ok, bad, head = audit.verify(audit.read(self.path)); self.assertEqual((ok, bad), (True, None)); self.assertEqual(head, chain(BODIES)[-1]["hash"])
    def test_an_edited_line_is_caught_at_that_line(self):
        es = chain(BODIES); es[2]["body"]["outcome"] = "declined by nobody"; self.write(es); ok, bad, _ = audit.verify(audit.read(self.path)); self.assertEqual((ok, bad), (False, 3))
    def test_a_deleted_line_and_a_reordered_pair_are_caught(self):
        es = chain(BODIES); self.write(es[:1] + es[2:]); self.assertEqual(audit.verify(audit.read(self.path))[:2], (False, 2))
        self.write([es[1], es[0]] + es[2:]); self.assertFalse(audit.verify(audit.read(self.path))[0])
    def test_an_empty_record_is_a_valid_empty_chain(self):
        self.write([]); self.assertEqual(audit.verify(audit.read(self.path)), (True, None, "genesis"))


class Summaries(Fixture):
    def rows(self): return {r["runId"]: r for r in audit.view(self.path)["rows"]}
    def test_the_definition_outcome_and_actors_are_read_from_each_run(self):
        r = self.rows()
        self.assertEqual((r["payment-35"]["definition"], r["payment-35"]["outcome"], r["payment-35"]["approvers"]), ("payment-exception", "approved", ["bob", "carol"]))
        self.assertEqual((r["rca-1"]["outcome"], r["rca-1"]["rejectedBy"], r["rca-1"]["rejectionReason"]), ("declined", "carol", "Sent back: x"))
        self.assertEqual((r["vuln-6"]["outcome"], r["payment-9"]["outcome"]), ("expired", "escalated")); self.assertEqual(r["major-1"]["outcome"], "approved")
    def test_controls_come_from_the_facts_the_category_and_the_regulators(self):
        r = self.rows(); self.assertEqual(r["rca-1"]["controls"], ["Change management and pre-production testing"]); self.assertEqual(r["assess-3"]["controls"], ["CR.AVM.PATCH"]); self.assertEqual(r["major-1"]["controls"], ["DORA", "MAS"])
    def test_the_write_back_and_digest_point_at_what_was_done(self):
        r = self.rows(); self.assertEqual(r["assess-3"]["writeBack"]["call"], "register.assessments #4"); self.assertEqual(r["assess-3"]["evidenceDigest"], "d3"); self.assertEqual(r["payment-35"]["writeBack"]["mode"], "dry-run")
    def test_decided_at_is_the_latest_approval_or_the_rejection(self):
        r = self.rows(); self.assertEqual(r["payment-35"]["decidedAt"], "2026-11-21T10:01:00+00:00"); self.assertEqual(r["rca-1"]["decidedAt"], "2026-11-20T11:00:00+00:00")
    def test_the_summary_does_not_carry_the_facts(self):
        self.assertNotIn("invoice", json.dumps(self.rows()["payment-35"]))


class Filters(Fixture):
    def ids(self, **f): return [r["runId"] for r in audit.view(self.path, **f)["rows"]]
    def test_each_filter_narrows_and_they_combine(self):
        self.assertEqual(self.ids(definition="risk-assessment"), ["assess-3"]); self.assertEqual(sorted(self.ids(outcome="approved")), ["assess-3", "major-1", "payment-35"])
        self.assertEqual(sorted(self.ids(actor="BOB")), ["assess-3", "major-1", "payment-35"]); self.assertEqual(self.ids(actor="carol", outcome="declined"), ["rca-1"])
        self.assertEqual(self.ids(control="dora"), ["major-1"]); self.assertEqual(self.ids(run="vuln-6"), ["vuln-6"]); self.assertEqual(self.ids(actor="nobody"), [])
    def test_dates_are_inclusive_days_on_when_it_was_decided(self):
        self.assertEqual(sorted(self.ids(since="2026-11-21")), ["assess-3", "major-1", "payment-35"]); self.assertEqual(self.ids(since="2026-11-21", until="2026-11-21", definition="major-incident"), ["major-1"])
        self.assertEqual(sorted(self.ids(until="2026-11-17")), ["payment-9"])
    def test_the_view_lists_what_can_be_filtered_by(self):
        v = audit.view(self.path); self.assertIn("risk-assessment", v["definitions"]); self.assertIn("DORA", v["controls"]); self.assertEqual(v["total"], 6)


class Export(Fixture):
    def lines(self, **f): return [json.loads(l) for l in audit.export(self.path, **f).splitlines()]
    def test_the_header_says_it_is_not_signed_and_carries_the_head_and_the_verdict(self):
        h = self.lines()[0]; self.assertIsNone(h["signature"]); self.assertTrue(h["chainValidAtExport"]); self.assertEqual(h["chainHead"], chain(BODIES)[-1]["hash"]); self.assertEqual((h["entries"], h["totalInFile"]), (6, 6))
        self.assertIn("NO signature", h["how_to_check"])
    def test_every_exported_entry_checks_on_its_own(self):
        ls = self.lines(definition="risk-assessment", outcome="approved"); e = ls[1]
        self.assertEqual(audit.entry_hash(e["prev"], e["body"]), e["hash"]); self.assertEqual(e["body"]["decision_id"], "assess-3"); self.assertEqual(ls[0]["firstEntryPrev"], e["prev"])
    def test_a_selection_says_whether_it_is_contiguous(self):
        self.assertTrue(self.lines()[0]["selectionContiguous"]); self.assertFalse(self.lines(outcome="approved")[0]["selectionContiguous"])
    def test_a_tampered_file_is_reported_in_the_header_not_hidden(self):
        es = chain(BODIES); es[0]["body"]["outcome"] = "x"; self.write(es); h = self.lines()[0]; self.assertFalse(h["chainValidAtExport"]); self.assertEqual(h["firstBadEntry"], 1)
    def test_the_filters_are_recorded(self):
        self.assertEqual(self.lines(actor="bob", since=None)[0]["filters"], {"actor": "bob"})

if __name__ == "__main__": unittest.main()
