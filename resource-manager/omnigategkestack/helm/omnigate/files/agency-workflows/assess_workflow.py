"""The risk-assessment workflow (Temporal): the way a rating gets into the risk register (docs/agency-risk-register-plan.md, section 3). Same shape as the others:
facts (one system's estate row, the register's current rating, the exposure rating) -> rules gate (the Priorities rules propose rating, category and control evidence) -> recommendation clamped to
the allowed actions (record or hold) -> second-line approval bound to the exact proposal (two people for a Critical rating) -> one appended row in the register -> decision record.
The workflow only decides and waits; all I/O is in activities.py. Workflow id: assess-<system_id>. Approving carries out what the run recommends; rejecting declines it and needs a reason."""
import hashlib, json, os
from datetime import timedelta
from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import activities as A, assess_rules as rules
    from assess_rules import HOLD, RECORD

APPROVAL_TIMEOUT = timedelta(minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "2880")))      # 48 h
RETRY = {"start_to_close_timeout": timedelta(seconds=120)}


def summarize(facts, gate=None):
    """The few facts a person needs on the approval card."""
    row = dict(zip([str(c).lower() for c in facts["table"]["columns"]], facts["table"]["rows"][0]))
    out = {"system": row.get("system"), "business_tier": row.get("tier"), "environment": row.get("environment")}
    cur = facts.get("register")
    out["in_the_register_now"] = "%s (set by %s)" % (cur["rating"], cur["set_by"]) if cur else "not rated yet"
    p = (gate or {}).get("proposal")
    if p:
        out["proposed_rating"] = "%s (likelihood %s, impact %s)" % (p["rating"], p["likelihood"], p["impact"]); out["proposed_category"] = p["category"]
        out["control_evidence"] = p["control_evidence"]
        if p["triggers"]: out["triggers"] = ", ".join(p["triggers"])
    ex = facts.get("exposure") or {}
    out["exposure"] = ex["sentence"] if ex.get("assessed") else "not applied: %s" % ex.get("reason", "not assessed")
    return out


def payload_hash(action):
    body = {k: action[k] for k in sorted(action) if k not in ("payload_hash", "approvers")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@workflow.defn
class RiskAssessment:
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
        if payload_hash != self.state["payload_hash"]: self.ignored.append({"approver": approver, "why": "the hash does not match the current proposal"}); return
        if not rules.may_approve(approver, [a["approver"] for a in self.approvals], self.state["gate"]):
            self.ignored.append({"approver": approver, "why": "not allowed to approve this rating, or already counted"}); return
        self.approvals.append({"approver": approver, "at": workflow.now().isoformat()})

    @workflow.signal
    def reject(self, approver: str, reason: str):
        if self.state.get("stage") == "awaiting_approval" and approver and approver.lower() not in {x.lower() for x in self.state["gate"]["excluded_approvers"]}:
            self.rejection = {"approver": approver, "reason": reason, "at": workflow.now().isoformat()}

    @workflow.run
    async def run(self, system_id: int, meta: dict | None = None) -> dict:
        wid = workflow.info().workflow_id
        self.meta = {k: v for k, v in (meta or {}).items() if k in ("initiator", "queryId") and isinstance(v, str)}
        initiator = self.meta.get("initiator", "")
        self._st(stage="facts")
        facts = await workflow.execute_activity(A.assess_gather_facts, system_id, **RETRY)
        self._st(stage="rules", facts_summary=summarize(facts))
        gate = await workflow.execute_activity(A.assess_rules_gate, args=[facts, initiator], **RETRY)
        self._st(stage="recommendation", facts_summary=summarize(facts, gate), gate=gate)
        rec = await workflow.execute_activity(A.assess_recommend, args=[facts, gate], **RETRY)
        prop = gate["proposal"]
        record = {"decision_id": wid, "system_id": system_id, "definition": "risk-assessment", "facts": facts, "rules": gate, "recommendation": rec, "started_at": workflow.now().isoformat()}
        action = {"type": rec["recommendation"], "system": "register", "system_id": system_id, "idempotency_key": wid, "item_type": "system"}
        if prop:
            action.update(item_ref=prop["system"], rating=prop["rating"], category=prop["category"], proposal_digest=rules.assessment_digest(facts, prop))
            action["likelihood"], action["impact"] = prop["likelihood"], prop["impact"]
        if action["type"] == HOLD: action["waiting_for"] = list(gate["blocks"]) or list(gate["notes"][:3])
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
        result = await workflow.execute_activity(A.assess_write_back, args=[action, gate["proposal"]], **RETRY)
        self.state["stage"] = "done"; self.state["write_back"] = result
        record.update(outcome="%s approved by %s: %s" % (action["type"], ", ".join(action["approvers"]), result["mode"]), action=action, approvals=self.approvals, write_back=result, ignored_signals=self.ignored)
        await workflow.execute_activity(A.record_decision, record, **RETRY)
        return {"outcome": record["outcome"], "write_back": result}
