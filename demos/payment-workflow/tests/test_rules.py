import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import rules

def facts(**kw):
    f = {"payment": {"amount": "100000.00", "amount_usd": "100000.00", "initiated_by": "a.tanaka"},
         "policy": {"auto_release_limit_usd": "50000", "dual_approval_above_usd": "250000"},
         "invoice": {"status": "Open", "amount": "100000.00", "po_number": "PO-1", "po_status": "Open"},
         "balance": {"available_balance": "900000.00"}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(f.get(k), dict): f[k].update(v)
        else: f[k] = v
    return f

class Gate(unittest.TestCase):
    def test_clean_payment_may_be_released_with_one_approver(self):
        g = rules.gate(facts()); self.assertEqual(g["allowed_actions"], ["release", "hold", "escalate"]); self.assertEqual(g["approvals_required"], 1); self.assertEqual(g["blocks"], [])
    def test_above_dual_limit_needs_two_approvers(self):
        g = rules.gate(facts(payment={"amount_usd": "300000.00"})); self.assertEqual(g["approvals_required"], 2)
    def test_exactly_the_dual_limit_needs_only_one(self):
        self.assertEqual(rules.gate(facts(payment={"amount_usd": "250000.00"}))["approvals_required"], 1)
    def test_already_paid_invoice_blocks_release(self):
        g = rules.gate(facts(invoice={"status": "Paid"})); self.assertNotIn("release", g["allowed_actions"]); self.assertIn("duplicate", g["blocks"][0])
    def test_held_invoice_blocks_release(self):
        self.assertNotIn("release", rules.gate(facts(invoice={"status": "On hold"}))["allowed_actions"])
    def test_amount_mismatch_blocks_release(self):
        self.assertNotIn("release", rules.gate(facts(invoice={"amount": "99999.00"}))["allowed_actions"])
    def test_equal_amounts_in_different_spelling_match(self):
        self.assertEqual(rules.gate(facts(invoice={"amount": "100000.0"}))["blocks"], [])
    def test_insufficient_balance_blocks_release(self):
        self.assertNotIn("release", rules.gate(facts(balance={"available_balance": "5.00"}))["allowed_actions"])
    def test_missing_invoice_or_balance_blocks_release(self):
        self.assertNotIn("release", rules.gate(facts(invoice=None))["allowed_actions"]); self.assertNotIn("release", rules.gate(facts(balance=None))["allowed_actions"])

class Approvers(unittest.TestCase):
    def setUp(self): self.g = rules.gate(facts())
    def test_initiator_and_the_ai_may_not_approve(self):
        for who in ("a.tanaka", "A.Tanaka", "treasury-agent", "policy-auto", "claude", ""): self.assertFalse(rules.may_approve(who, [], self.g), who)
    def test_a_different_person_may_approve_once(self):
        self.assertTrue(rules.may_approve("m.okafor", [], self.g)); self.assertFalse(rules.may_approve("M.Okafor", ["m.okafor"], self.g))

class Record(unittest.TestCase):
    def test_chain_detects_an_edit_and_ignores_a_repeat(self):
        import decisions
        decisions.PATH = os.path.join(tempfile.mkdtemp(), "d.jsonl")
        decisions.append({"decision_id": "a", "x": 1}); decisions.append({"decision_id": "b", "x": 2}); decisions.append({"decision_id": "b", "x": 2})
        self.assertEqual(len(decisions.read()), 2); self.assertEqual(decisions.verify(), "ok")
        lines = open(decisions.PATH).read().replace('"x": 1', '"x": 9'); open(decisions.PATH, "w").write(lines)
        self.assertEqual(decisions.verify(), "broken at record 1")

if __name__ == "__main__": unittest.main()
