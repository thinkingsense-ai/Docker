"""The incident-brief workflow (Temporal), for the IT-risk root-cause analysis in docs/agency-risk-it.md. Same shape as the payment and vulnerability workflows:
facts (the case's causes, grades and sources, read through thinking sense) -> rules gate -> recommendation clamped to the allowed actions (publish or hold) -> a named approver, bound to
the exact brief -> dry-run write-back -> decision record. The workflow only decides and waits; all I/O is in activities.py. Workflow id: rca-<claim_id>.
Approving carries out the recommended action: publish the brief as this version, or record the hold. Rejecting declines the recommendation and needs a reason."""
import hashlib, json, os
from datetime import timedelta
from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import activities as A, rca_rules as rules
    from rca_rules import HOLD, PUBLISH

APPROVAL_TIMEOUT = timedelta(minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "2880")))      # 48 h
RETRY = {"start_to_close_timeout": timedelta(seconds=120)}


def summarize(facts, gate=None):
    """The few facts a person needs on the approval card."""
    inc = facts["incidents"]; conf = [i for i in inc if i["grade"] == "confirmed"]; open_ = [i for i in inc if i["grade"] != "confirmed"]
    out = {"claim": facts["claim"]["claim"], "case": facts["case_id"], "causes_confirmed": "%d of %d" % (len(conf), len(inc)),
           "open_incidents": "; ".join("%s (%s)" % (i["operator"], i["grade"].replace("_", " ")) for i in open_) or "none"}
    if gate: out["verdict"] = gate["verdict_sentence"]
    for c in facts.get("controls", []): out["control_to_fix"] = "%s (%s); %s %s" % (c["owning_control"], c["owner_role"], c["framework"], c["category"])
    return out


def payload_hash(action):
    body = {k: action[k] for k in sorted(action) if k not in ("payload_hash", "approvers")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@workflow.defn
class IncidentClusterRca:
    def __init__(self):
        self.state = {"stage": "starting"}; self.approvals = []; self.rejection = None; self.ignored = []; self.meta = {}

    def _st(self, **kw):
        self.state = dict(self.meta, **kw)

    @workflow.query
    def status(self) -> dict:
        return dict(self.state, approvals=list(self.approvals), rejection=self.rejection, ignored=list(self.ignored))

    @workflow.signal
    def approve(self, approver: str, payload_hash: str):
        if self.state.get("stage") != "awaiting_approval": return
        if payload_hash != self.state["payload_hash"]: self.ignored.append({"approver": approver, "why": "the hash does not match the current brief"}); return
        if not rules.may_approve(approver, [a["approver"] for a in self.approvals], self.state["gate"]):
            self.ignored.append({"approver": approver, "why": "not allowed to approve this brief, or already counted"}); return
        self.approvals.append({"approver": approver, "at": workflow.now().isoformat()})

    @workflow.signal
    def reject(self, approver: str, reason: str):
        if self.state.get("stage") == "awaiting_approval" and approver and approver.lower() not in {x.lower() for x in self.state["gate"]["excluded_approvers"]}:
            self.rejection = {"approver": approver, "reason": reason, "at": workflow.now().isoformat()}

    @workflow.run
    async def run(self, claim_id: int, meta: dict | None = None) -> dict:
        wid = workflow.info().workflow_id
        self.meta = {k: v for k, v in (meta or {}).items() if k in ("initiator", "queryId") and isinstance(v, str)}
        initiator = self.meta.get("initiator", "")
        self._st(stage="facts")
        facts = await workflow.execute_activity(A.rca_gather_facts, claim_id, **RETRY)
        self._st(stage="rules", facts_summary=summarize(facts))
        gate = await workflow.execute_activity(A.rca_rules_gate, args=[facts, initiator], **RETRY)
        self._st(stage="recommendation", facts_summary=summarize(facts, gate), gate=gate)
        rec = await workflow.execute_activity(A.rca_recommend, args=[facts, gate], **RETRY)
        record = {"decision_id": wid, "claim_id": claim_id, "definition": "incident-cluster-rca", "case_id": facts["case_id"], "facts": facts, "rules": gate, "recommendation": rec, "started_at": workflow.now().isoformat()}
        action = {"type": rec["recommendation"], "system": "briefing", "claim_id": claim_id, "case_id": facts["case_id"], "brief_digest": rules.brief_digest(facts), "idempotency_key": wid}
        if action["type"] == HOLD: action["waiting_for"] = list(gate["blocks"]) or [n for n in gate["notes"][:3]]
        action["payload_hash"] = payload_hash(action)
        self._st(stage="awaiting_approval", payload_hash=action["payload_hash"], action=action, recommendation=rec, gate=gate, approvals_required=gate["approvals_required"], facts_summary=summarize(facts, gate))
        try:
            await workflow.wait_condition(lambda: self.rejection is not None or len(self.approvals) >= gate["approvals_required"], timeout=APPROVAL_TIMEOUT)
        except TimeoutError:
            self.state["stage"] = "expired"; record.update(outcome="no decision before the deadline: escalated", action=action, approvals=self.approvals)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        if self.rejection:
            self.state["stage"] = "rejected"; record.update(outcome="declined by %s" % self.rejection["approver"], action=action, approvals=self.approvals, rejection=self.rejection)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        self.state["stage"] = "writing_back"
        action["approvers"] = [a["approver"] for a in self.approvals]
        result = await workflow.execute_activity(A.rca_write_back, action, **RETRY)
        self.state["stage"] = "done"; self.state["write_back"] = result
        record.update(outcome="%s approved by %s: %s" % (action["type"], ", ".join(action["approvers"]), result["mode"]), action=action, approvals=self.approvals, write_back=result, ignored_signals=self.ignored)
        await workflow.execute_activity(A.record_decision, record, **RETRY)
        return {"outcome": record["outcome"], "write_back": result}
