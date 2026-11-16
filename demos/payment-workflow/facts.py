"""Governed facts: every number comes from thinking sense's own query path (POST /api/query), so access policy, federation across Postgres and the ERP, and the audit log all apply.
No workflow code talks to a database directly."""
import json, os, urllib.request
ASK_URL = os.environ.get("ASK_URL", "http://omnigate:8080").rstrip("/")

def query(sql):
    req = urllib.request.Request(ASK_URL + "/api/query", json.dumps({"sql": sql}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: res = json.load(r)
    if not res.get("success"): raise RuntimeError("query failed: %s" % res.get("error"))
    cols = res["columns"]; return [dict(zip(cols, row)) for row in res["rows"]]

def pending_payments():
    """Each system is read on its own and merged here: a single statement that joins Postgres and the ERP comes back without its AS aliases (and with duplicate column names)."""
    pays = query("SELECT p.payment_id, p.invoice_id, p.vendor_id, p.amount, p.currency, p.amount_usd, p.initiated_by, pol.dual_approval_above_usd FROM treasury.payments p "
                 "JOIN treasury.payment_policies pol ON pol.policy_id = p.policy_id WHERE p.status = 'Pending approval' ORDER BY p.payment_id")
    if not pays: return []
    ids = ",".join(str(int(p["invoice_id"])) for p in pays)
    inv = {r["invoice_id"]: r for r in query("SELECT i.invoice_id, i.invoice_no, i.status AS invoice_status, i.amount AS invoice_amount, v.name AS vendor FROM erp.invoices i JOIN erp.vendors v ON v.vendor_id = i.vendor_id WHERE i.invoice_id IN (%s)" % ids)}
    return [dict(p, **{k: inv.get(p["invoice_id"], {}).get(k) for k in ("invoice_no", "invoice_status", "invoice_amount", "vendor")}) for p in pays]

def gather(payment_id):
    n = int(payment_id)
    pay = query("SELECT p.payment_id, p.entity_id, e.name AS entity, p.account_id, p.invoice_id, p.vendor_id, p.amount, p.currency, p.amount_usd, p.value_date, p.status, p.initiated_by, "
                "pol.name AS policy, pol.auto_release_limit_usd, pol.dual_approval_above_usd FROM treasury.payments p JOIN treasury.payment_policies pol ON pol.policy_id = p.policy_id "
                "JOIN treasury.entities e ON e.entity_id = p.entity_id WHERE p.payment_id = %d" % n)
    if not pay: raise RuntimeError("payment %d not found" % n)
    p = pay[0]
    bal = query("SELECT as_of_date, available_balance, ledger_balance FROM treasury.balances WHERE account_id = %d ORDER BY as_of_date DESC LIMIT 1" % int(p["account_id"]))
    inv = query("SELECT i.invoice_id, i.invoice_no, i.invoice_date, i.due_date, i.amount, i.currency, i.status, i.po_number, po.amount AS po_amount, po.status AS po_status, "
                "v.name AS vendor, v.country AS vendor_country, v.payment_terms_days FROM erp.invoices i LEFT JOIN erp.purchase_orders po ON po.po_number = i.po_number "
                "JOIN erp.vendors v ON v.vendor_id = i.vendor_id WHERE i.invoice_id = %d" % int(p["invoice_id"]))
    dup = query("SELECT invoice_id, invoice_no, status FROM erp.invoices WHERE vendor_id = %d AND amount = %s AND invoice_id <> %d" % (int(p["vendor_id"]), repr(float(p["amount"])), int(p["invoice_id"])))
    past = query("SELECT COUNT(*) AS payments, COALESCE(SUM(amount_usd), 0) AS total_usd FROM treasury.payments WHERE vendor_id = %d AND status = 'Released'" % int(p["vendor_id"]))
    acts = query("SELECT occurred_at, actor, action_type, detail, within_policy FROM treasury.agent_actions WHERE payment_id = %d ORDER BY occurred_at" % n)
    return {"payment": p, "policy": {k: p[k] for k in ("policy", "auto_release_limit_usd", "dual_approval_above_usd")}, "balance": bal[0] if bal else None,
            "invoice": inv[0] if inv else None, "possible_duplicate_invoices": dup, "vendor_history": past[0] if past else None, "agent_actions": acts}
