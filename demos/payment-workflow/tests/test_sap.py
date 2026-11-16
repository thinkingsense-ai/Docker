import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sap_facts, sap_rules

def facts(**inv):
    i = {"InvoiceGrossAmount": "1000.00", "DocumentCurrency": "USD", "PaymentBlockingReason": "A", "PostingDate": "2021-02-05", "DueCalculationBaseDate": "2021-02-05",
         "IsReversed": False, "IsReversal": False, "SupplierInvoicePaymentStatus": "Open"}; i.update(inv)
    return {"system": "sap", "invoice": i, "possible_duplicate_invoices": [], "supplier": {"id": "S1", "blocked_invoices": 1}}

class Gate(unittest.TestCase):
    def test_a_clean_open_invoice_may_be_released_with_one_approver(self):
        g = sap_rules.gate(facts()); self.assertEqual(g["allowed_actions"], ["release", "hold", "escalate"]); self.assertEqual(g["approvals_required"], 1); self.assertEqual(g["blocks"], [])
    def test_a_twin_invoice_blocks_release(self):
        f = facts(); f["possible_duplicate_invoices"] = [{"SupplierInvoice": "5100044226"}]; g = sap_rules.gate(f)
        self.assertNotIn("release", g["allowed_actions"]); self.assertIn("5100044226", g["blocks"][0])
    def test_a_cleared_invoice_with_a_block_is_a_contradiction_not_a_release(self):
        g = sap_rules.gate(facts(SupplierInvoicePaymentStatus="Cleared")); self.assertNotIn("release", g["allowed_actions"]); self.assertIn("Cleared", g["blocks"][0])
    def test_a_reversed_invoice_blocks_release(self):
        self.assertNotIn("release", sap_rules.gate(facts(IsReversed=True))["allowed_actions"])
    def test_dual_approval_above_the_limit_and_demo_fx_for_gbp(self):
        self.assertEqual(sap_rules.gate(facts(InvoiceGrossAmount="250000.01"))["approvals_required"], 2); self.assertEqual(sap_rules.gate(facts(InvoiceGrossAmount="250000.00"))["approvals_required"], 1)
        self.assertEqual(sap_rules.gate(facts(InvoiceGrossAmount="200000.00", DocumentCurrency="GBP"))["approvals_required"], 2, "200,000 GBP is 254,000 USD at the demo rate")
    def test_an_unknown_currency_blocks_release(self):
        self.assertNotIn("release", sap_rules.gate(facts(DocumentCurrency="JPY"))["allowed_actions"])
    def test_the_ai_and_automation_names_may_not_approve(self):
        self.assertIn("treasury-agent", sap_rules.gate(facts())["excluded_approvers"])

class Facts(unittest.TestCase):
    def test_a_key_part_is_checked_before_it_goes_into_a_url(self):
        for bad in ("5100044194'; drop", "abc", "", "1" * 11): self.assertRaises(ValueError, sap_facts._safe, bad, r"\d{1,10}")
        self.assertRaises(ValueError, sap_facts._safe, "S1' or 1 eq 1 or 'a'='a", r"[A-Za-z0-9_\-]{1,20}")
    def test_sap_dates_are_read_as_utc_days(self):
        self.assertEqual(sap_facts.date("/Date(1612396800000)/"), "2021-02-04"); self.assertIsNone(sap_facts.date(None))

class WriteBack(unittest.TestCase):
    def test_the_release_call_is_a_dry_run_naming_the_function_import_and_never_sent(self):
        try: import activities as A
        except ImportError: self.skipTest("temporalio is not installed here; run in the worker image")
        a = {"type": "release", "system": "sap", "payment_id": 5100043603, "invoice_id": 5100043603, "fiscal_year": "2021", "amount": "54.45", "currency": "USD", "idempotency_key": "sap-invoice-5100043603", "payload_hash": "x", "approvers": ["m.okafor"]}
        r = A.write_back.__wrapped__(a) if hasattr(A.write_back, "__wrapped__") else A.write_back(a)
        self.assertEqual(r["mode"], "dry-run"); self.assertIn("/Release?SupplierInvoice='5100043603'&FiscalYear='2021'", r["would_send"]["url"]); self.assertIn("read-only", r["note"])
        h = dict(a, type="hold"); self.assertEqual((A.write_back(h))["mode"], "no-write")

if __name__ == "__main__": unittest.main()
