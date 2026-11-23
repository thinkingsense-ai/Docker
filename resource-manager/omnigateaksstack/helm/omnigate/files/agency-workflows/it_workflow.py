"""The vulnerability-exception workflow (Temporal), for the IT and operational risk pack. Same shape as the payment exception:
facts (read where they live, through thinking sense) -> rules gate -> AI recommendation clamped to the allowed actions -> named approvers, bound to the exact payload ->
dry-run write-back -> decision record. The workflow only decides and waits; all I/O is in activities.py. Workflow id: vuln-<vuln_id>."""
import hashlib, json, os
from datetime import timedelta
from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import activities as A, it_rules as rules
    from it_rules import ESCALATE

APPROVAL_TIMEOUT = timedelta(minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "2880")))      # 48 h
RETRY = {"start_to_close_timeout": timedelta(seconds=120)}


def summarize(facts):
    """The few facts a person needs on the approval card."""
    v, s, ven = facts["vulnerability"], facts["service"], facts.get("vendor") or {}
    return {"cve": v["cve"], "cvss": v["cvss"], "severity": v["severity"], "patch_due": v["patch_due"], "application": facts["application"]["application"], "service": s["service"],
            "service_tier": s["tier"], "service_owner": s["owner"], "vendor": ven.get("name"), "vendor_last_assessed": ven.get("last_assessed")}


def payload_hash(action):
    body = {k: action[k] for k in sorted(action) if k not in ("payload_hash", "approvers")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@workflow.defn
class VulnerabilityException:
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
        if payload_hash != self.state["payload_hash"]: self.ignored.append({"approver": approver, "why": "the hash does not match the current payload"}); return
        if not rules.may_approve(approver, [a["approver"] for a in self.approvals], self.state["gate"]):
            self.ignored.append({"approver": approver, "why": "not allowed to approve this item, or already counted"}); return
        self.approvals.append({"approver": approver, "at": workflow.now().isoformat()})

    @workflow.signal
    def reject(self, approver: str, reason: str):
        if self.state.get("stage") == "awaiting_approval" and approver and approver.lower() not in {x.lower() for x in self.state["gate"]["excluded_approvers"]}:
            self.rejection = {"approver": approver, "reason": reason, "at": workflow.now().isoformat()}

    @workflow.run
    async def run(self, vuln_id: int, meta: dict | None = None) -> dict:
        wid = workflow.info().workflow_id
        self.meta = {k: v for k, v in (meta or {}).items() if k in ("initiator", "queryId") and isinstance(v, str)}
        initiator = self.meta.get("initiator", "")
        self._st(stage="facts")
        facts = await workflow.execute_activity(A.it_gather_facts, vuln_id, **RETRY)
        self._st(stage="rules", facts_summary=summarize(facts))
        gate = await workflow.execute_activity(A.it_rules_gate, args=[facts, initiator], **RETRY)
        self._st(stage="recommendation", facts_summary=summarize(facts), gate=gate)
        rec = await workflow.execute_activity(A.it_recommend, args=[facts, gate], **RETRY)
        record = {"decision_id": wid, "vuln_id": vuln_id, "definition": "vulnerability-exception", "facts": facts, "rules": gate, "recommendation": rec, "started_at": workflow.now().isoformat()}
        if rec["recommendation"] == ESCALATE:
            self._st(stage="escalated", recommendation=rec, gate=gate, facts_summary=summarize(facts))
            record.update(outcome="escalated to a person", action=None, approvals=[])
            await workflow.execute_activity(A.record_decision, record, **RETRY); return {"outcome": record["outcome"]}
        v, s = facts["vulnerability"], facts["service"]
        action = {"type": rec["recommendation"], "system": "grc", "vuln_id": vuln_id, "cve": v["cve"], "service_id": int(s["service_id"]), "idempotency_key": wid}
        action["payload_hash"] = payload_hash(action)
        self._st(stage="awaiting_approval", payload_hash=action["payload_hash"], action=action, recommendation=rec, gate=gate, approvals_required=gate["approvals_required"], facts_summary=summarize(facts))
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
        result = await workflow.execute_activity(A.it_write_back, action, **RETRY)
        self.state["stage"] = "done"; self.state["write_back"] = result
        record.update(outcome="%s approved by %s: %s" % (action["type"], ", ".join(action["approvers"]), result["mode"]), action=action, approvals=self.approvals, write_back=result, ignored_signals=self.ignored)
        await workflow.execute_activity(A.record_decision, record, **RETRY)
        return {"outcome": record["outcome"], "write_back": result}
