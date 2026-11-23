"""The major-incident decision workflow (Temporal): how a person's decision that an incident is MAJOR gets recorded, which is what starts the notification clocks (clock_rules.py).
facts (the firm's incident, the declared regulators, the rules) -> rules gate (NO rule decides major; it only checks the decision can be recorded) -> a named second-line approver, bound to the exact incident,
regulators and rules -> one appended row in register.major_incident_decisions -> decision record. Nothing is sent to any regulator. Workflow id: major-<incident_id>.
There is no recommendation step on purpose. Approving IS the decision; rejecting records nothing and no clock starts."""
import hashlib, json, os
from datetime import timedelta
from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import activities as A, major_rules as rules
    from major_rules import RECORD

APPROVAL_TIMEOUT = timedelta(minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "2880")))      # 48 h
RETRY = {"start_to_close_timeout": timedelta(seconds=120)}


def summarize(facts, gate=None):
    inc = facts["incident"]
    out = {"incident": inc.get("title"), "the_firm_became_aware": str(inc.get("awareness_at")), "summary": inc.get("summary")}
    out["regulators_declared"] = ", ".join(rules.declared(facts)) or "none"
    if gate and not gate["blocks"]: out["clocks_it_would_start"] = " | ".join(n for n in gate["notes"] if " would be due " in n)
    return out


def payload_hash(action):
    return hashlib.sha256(json.dumps({k: action[k] for k in sorted(action) if k not in ("payload_hash", "approvers")}, sort_keys=True).encode()).hexdigest()


@workflow.defn
class MajorIncidentDecision:
    def __init__(self):
        self.state = {"stage": "starting"}; self.approvals = []; self.rejection = None; self.ignored = []; self.meta = {}

    def _st(self, **kw): self.state = dict(self.meta, **kw)

    @workflow.query
    def status(self) -> dict: return dict(self.state, approvals=list(self.approvals), rejection=self.rejection, ignored=list(self.ignored))

    @workflow.signal
    def approve(self, approver: str, payload_hash: str):
        if self.state.get("stage") != "awaiting_approval": return
        if payload_hash != self.state["payload_hash"]: self.ignored.append({"approver": approver, "why": "the hash does not match the current proposal"}); return
        if not rules.may_approve(approver, [a["approver"] for a in self.approvals], self.state["gate"]): self.ignored.append({"approver": approver, "why": "not allowed to approve this decision, or already counted"}); return
        self.approvals.append({"approver": approver, "at": workflow.now().isoformat()})

    @workflow.signal
    def reject(self, approver: str, reason: str):
        if self.state.get("stage") == "awaiting_approval" and approver and approver.lower() not in {x.lower() for x in self.state["gate"]["excluded_approvers"]}:
            self.rejection = {"approver": approver, "reason": reason, "at": workflow.now().isoformat()}

    @workflow.run
    async def run(self, incident_id: int, meta: dict | None = None) -> dict:
        wid = workflow.info().workflow_id
        self.meta = {k: v for k, v in (meta or {}).items() if k in ("initiator", "queryId") and isinstance(v, str)}
        initiator = self.meta.get("initiator", "")
        self._st(stage="facts")
        facts = await workflow.execute_activity(A.major_gather_facts, incident_id, **RETRY)
        self._st(stage="rules", facts_summary=summarize(facts))
        gate = await workflow.execute_activity(A.major_rules_gate, args=[facts, initiator], **RETRY)
        record = {"decision_id": wid, "incident_id": incident_id, "definition": "major-incident", "facts": facts, "rules": gate, "started_at": workflow.now().isoformat()}
        action = {"type": RECORD, "system": "register", "incident_id": incident_id, "idempotency_key": wid, "regimes": gate["regimes"], "proposal_digest": rules.proposal_digest(facts)}
        action["payload_hash"] = payload_hash(action)
        self._st(stage="awaiting_approval", payload_hash=action["payload_hash"], action=action, gate=gate, approvals_required=gate["approvals_required"], facts_summary=summarize(facts, gate))
        try:
            await workflow.wait_condition(lambda: self.rejection is not None or len(self.approvals) >= gate["approvals_required"], timeout=APPROVAL_TIMEOUT)
        except TimeoutError:
            self.state["stage"] = "expired"; record.update(outcome="no decision before the deadline", action=action, approvals=self.approvals)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        if self.rejection:
            self.state["stage"] = "rejected"; record.update(outcome="not recorded as major: declined by %s" % self.rejection["approver"], action=action, approvals=self.approvals, rejection=self.rejection)
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        self.state["stage"] = "writing_back"
        action["approvers"] = [a["approver"] for a in self.approvals]
        result = await workflow.execute_activity(A.major_write_back, args=[action, workflow.now().isoformat()], **RETRY)
        self.state["stage"] = "done"; self.state["write_back"] = result
        record.update(outcome="recorded as major by %s: %s" % (", ".join(action["approvers"]), result["mode"]), action=action, approvals=self.approvals, write_back=result, ignored_signals=self.ignored)
        await workflow.execute_activity(A.record_decision, record, **RETRY)
        return {"outcome": record["outcome"], "write_back": result}
