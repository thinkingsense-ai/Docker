"""The rules gate for a payment-blocked SAP supplier invoice. Same shape as rules.gate, so the workflow, the model clamp and the approval checks are shared.
Actions: release (release the payment block: SAP's `Release` function import), hold (keep the block; nothing is written), escalate (a person investigates).
The thresholds are a demo policy configured here (SAP's sandbox holds no policy), the FX rates are fixed demo constants, and the supplier-invoice header carries no creator,
so the initiator cannot be excluded as an approver the way the Treasury payment's is: a real tenant needs a creator field (not checked)."""
from decimal import Decimal
from rules import RELEASE, HOLD, ESCALATE, AGENT_ACTORS
POLICY = {"auto_release_limit_usd": "50000", "dual_approval_above_usd": "250000"}
FX_TO_USD = {"USD": Decimal("1"), "EUR": Decimal("1.08"), "GBP": Decimal("1.27")}
ACTION_HELP = {RELEASE: "release the payment block so the invoice can be paid (SAP Release function import)", HOLD: "keep the payment block in place (nothing is written to SAP)", ESCALATE: "a person investigates (nothing is written)"}

def amount_usd(facts):
    inv = facts["invoice"]; fx = FX_TO_USD.get(inv["DocumentCurrency"])
    return None if fx is None else Decimal(str(inv["InvoiceGrossAmount"])) * fx

def gate(facts):
    inv, sup = facts["invoice"], facts["supplier"]; blocks, notes = [], []
    if inv.get("IsReversed") or inv.get("IsReversal"): blocks.append("the invoice is reversed or is a reversal")
    if inv.get("SupplierInvoicePaymentStatus") == "Cleared": blocks.append("SAP shows the invoice as Cleared (already paid) although a payment block is still set: a contradiction to investigate, not a block to release")
    dups = facts.get("possible_duplicate_invoices") or []
    if dups: blocks.append("%d other invoice(s) from the same supplier have the same gross amount (%s): a possible duplicate" % (len(dups), ", ".join(d["SupplierInvoice"] for d in dups[:5])))
    usd = amount_usd(facts)
    if usd is None: blocks.append("no demo exchange rate for %s, so the amount cannot be checked against the limits" % inv["DocumentCurrency"])
    dual = usd is not None and usd > Decimal(POLICY["dual_approval_above_usd"])
    if dual: notes.append("above the %s USD dual-approval limit (demo policy): two different approvers are required" % POLICY["dual_approval_above_usd"])
    elif usd is not None and usd > Decimal(POLICY["auto_release_limit_usd"]): notes.append("above the %s USD auto-release limit (demo policy): one approver is required" % POLICY["auto_release_limit_usd"])
    if sup["blocked_invoices"] >= 10: notes.append("supplier %s has %d blocked invoices: look for one common cause before releasing them one by one" % (sup["id"], sup["blocked_invoices"]))
    notes.append("block reason %s; posting date %s; due calculation base %s" % (inv["PaymentBlockingReason"], inv["PostingDate"], inv["DueCalculationBaseDate"]))
    allowed = [HOLD, ESCALATE] if blocks else [RELEASE, HOLD, ESCALATE]
    return {"allowed_actions": allowed, "approvals_required": 2 if dual else 1, "blocks": blocks, "notes": notes, "excluded_approvers": sorted(AGENT_ACTORS), "action_help": ACTION_HELP}
