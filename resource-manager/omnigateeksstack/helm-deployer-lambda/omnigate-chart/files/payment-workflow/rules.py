"""The rules gate: hard limits that apply whatever the AI recommends (controls 4 and 5 of the design brief). Pure functions, no I/O, so a partner can read and test them.
`gate(facts)` returns which actions are allowed, how many distinct human approvals are needed, who may not approve, and why. The AI only ever chooses among the allowed actions."""
from decimal import Decimal

RELEASE, HOLD, ESCALATE = "release", "hold", "escalate"
AGENT_ACTORS = {"treasury-agent", "policy-auto", "ai", "claude"}        # the AI and automation never approve (control 4)

def _d(x):
    return Decimal(str(x)) if x not in (None, "") else None

def gate(facts):
    p, pol, inv, bal = facts["payment"], facts["policy"], facts.get("invoice"), facts.get("balance")
    blocks, notes = [], []
    amount, amount_usd = _d(p["amount"]), _d(p["amount_usd"])
    if inv is None:
        blocks.append("no invoice in the ERP for this payment")
    else:
        if inv["status"] == "Paid":
            blocks.append("the invoice is already marked Paid in the ERP: releasing again would be a duplicate payment")
        elif inv["status"] == "On hold":
            blocks.append("the invoice is On hold in the ERP")
        if _d(inv["amount"]) != amount:
            blocks.append("the payment amount (%s) differs from the invoice amount (%s)" % (p["amount"], inv["amount"]))
        if inv.get("po_number") and inv.get("po_status") not in (None, "Open", "Closed"):
            notes.append("purchase order %s is %s" % (inv["po_number"], inv.get("po_status")))
    if bal is None:
        blocks.append("no balance on record for the paying account")
    elif _d(bal["available_balance"]) < amount:
        blocks.append("the available balance (%s) is below the payment (%s)" % (bal["available_balance"], p["amount"]))
    dual = amount_usd > _d(pol["dual_approval_above_usd"])
    if dual:
        notes.append("above the %s USD dual-approval limit: two different approvers are required" % pol["dual_approval_above_usd"])
    elif amount_usd > _d(pol["auto_release_limit_usd"]):
        notes.append("above the %s USD auto-release limit: one approver is required" % pol["auto_release_limit_usd"])
    allowed = [HOLD, ESCALATE] if blocks else [RELEASE, HOLD, ESCALATE]
    return {"allowed_actions": allowed, "approvals_required": 2 if dual else 1, "blocks": blocks, "notes": notes,
            "excluded_approvers": sorted({p["initiated_by"]} | AGENT_ACTORS)}

def may_approve(approver, already, gate_result):
    """True when this person can add an approval: not excluded (initiator, the AI) and not already counted."""
    a = (approver or "").strip().lower()
    return bool(a) and a not in {x.lower() for x in gate_result["excluded_approvers"]} and a not in {x.lower() for x in already}
