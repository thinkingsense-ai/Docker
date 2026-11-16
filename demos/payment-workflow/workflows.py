"""The payment-exception workflow (Temporal). Reads top to bottom as the design brief's flow:
facts -> rules gate -> AI recommendation -> human approval bound to the exact payload -> governed write-back -> decision record.
The workflow itself only decides and waits (so it is deterministic and survives restarts and days of waiting); all I/O is in activities.py."""
import hashlib, json, os
from datetime import timedelta
from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import activities as A, rules
    from rules import RELEASE, HOLD, ESCALATE

APPROVAL_TIMEOUT = timedelta(minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "2880")))      # 48 h
RETRY = {"start_to_close_timeout": timedelta(seconds=120)}

def payload_hash(action):
    body = {k: action[k] for k in sorted(action) if k not in ("payload_hash", "approvers")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

@workflow.defn
class PaymentException:
    def __init__(self):
        self.state = {"stage": "starting"}; self.approvals = []; self.rejection = None; self.ignored = []

    @workflow.query
    def status(self) -> dict:
        return dict(self.state, approvals=list(self.approvals), rejection=self.rejection, ignored=list(self.ignored))

    @workflow.signal
    def approve(self, approver: str, payload_hash: str):
        """One approval, valid only for the exact payload hash shown to the approver (control 3), from someone allowed and not already counted (control 4)."""
        if self.state.get("stage") != "awaiting_approval": return
        if payload_hash != self.state["payload_hash"]: self.ignored.append({"approver": approver, "why": "the hash does not match the current payload"}); return
        who = [a["approver"] for a in self.approvals]
        if not rules.may_approve(approver, who, self.state["gate"]):
            self.ignored.append({"approver": approver, "why": "not allowed to approve this payment, or already counted"}); return
        self.approvals.append({"approver": approver, "at": workflow.now().isoformat()})

    @workflow.signal
    def reject(self, approver: str, reason: str):
        if self.state.get("stage") == "awaiting_approval" and approver and approver.lower() not in {x.lower() for x in self.state["gate"]["excluded_approvers"]}:
            self.rejection = {"approver": approver, "reason": reason, "at": workflow.now().isoformat()}

    @workflow.run
    async def run(self, payment_id: int) -> dict:
        wid = workflow.info().workflow_id
        facts = await workflow.execute_activity(A.gather_facts, payment_id, **RETRY)
        gate = await workflow.execute_activity(A.rules_gate, facts, **RETRY)
        rec = await workflow.execute_activity(A.recommend, args=[facts, gate], **RETRY)
        p = facts["payment"]
        record = {"decision_id": wid, "payment_id": payment_id, "facts": facts, "rules": gate, "recommendation": rec, "started_at": workflow.now().isoformat()}
        if rec["recommendation"] == ESCALATE:                      # nothing is written; a person takes it from here
            self.state = {"stage": "escalated", "recommendation": rec, "gate": gate}
            record.update(outcome="escalated to a person", action=None, approvals=[])
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        action = {"type": rec["recommendation"], "payment_id": payment_id, "invoice_id": int(p["invoice_id"]), "amount": p["amount"], "currency": p["currency"], "idempotency_key": wid}
        action["payload_hash"] = payload_hash(action)
        self.state = {"stage": "awaiting_approval", "payload_hash": action["payload_hash"], "action": action, "recommendation": rec, "gate": gate, "approvals_required": gate["approvals_required"],
                      "facts_summary": {"vendor": (facts.get("invoice") or {}).get("vendor"), "invoice_no": (facts.get("invoice") or {}).get("invoice_no"), "amount": p["amount"], "currency": p["currency"], "amount_usd": p["amount_usd"], "initiated_by": p["initiated_by"]}}
        try:
            await workflow.wait_condition(lambda: self.rejection is not None or len(self.approvals) >= gate["approvals_required"], timeout=APPROVAL_TIMEOUT)
        except TimeoutError:
            self.state["stage"] = "expired"; record.update(outcome="no decision before the deadline: escalated", action=action, approvals=self.approvals)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        if self.rejection:
            self.state["stage"] = "rejected"; record.update(outcome="rejected by %s" % self.rejection["approver"], action=action, approvals=self.approvals, rejection=self.rejection)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        self.state["stage"] = "writing_back"
        action["approvers"] = [a["approver"] for a in self.approvals]
        result = await workflow.execute_activity(A.write_back, action, **RETRY)
        self.state["stage"] = "done"; self.state["write_back"] = result
        record.update(outcome="%s approved by %s: %s" % (action["type"], ", ".join(action["approvers"]), result["mode"]), action=action, approvals=self.approvals, write_back=result, ignored_signals=self.ignored)
        await workflow.execute_activity(A.record_decision, record, **RETRY)
        return {"outcome": record["outcome"], "write_back": result}
