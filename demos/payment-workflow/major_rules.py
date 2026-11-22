"""The gate for the major-incident decision (docs/agency-risk-register-plan.md, section 5). Pure functions, no I/O.
A first-line person starts a run for ONE incident; a second-line person records that it is MAJOR, or sends it back. NO rule decides that an incident is major or material: this run only records a person's
decision, and the decision is what starts the notification clocks (clock_rules.py). Approving adds one row to register.major_incident_decisions (append-only); rejecting adds nothing and no clock starts.
Actions: "record" and "hold". Recording is allowed only when the incident exists, is not already recorded, and at least one regulator is declared (otherwise there would be no clock to start).
Nothing is sent to any regulator."""
import hashlib, json
from datetime import datetime, timezone
import clock_rules

RECORD, HOLD = "record", "hold"
AGENT_ACTORS = {"treasury-agent", "policy-auto", "ai", "claude"}                 # the AI and automation never approve
ACTION_HELP = {RECORD: "record that a person decided this incident is major, which starts the notification clocks of the declared regulators (nothing is sent to any regulator)",
               HOLD: "record nothing and say what the run is waiting for"}


def declared(facts): return [p["regulator"] for p in facts.get("profile", []) if clock_rules._true(p.get("declared"))]


def preview(facts, now):
    """The clocks that WOULD start if the decision were recorded now. Shown on the card so the approver sees what the decision starts; not stored."""
    inc = facts["incident"]
    return clock_rules.compute(facts.get("rules", []), declared(facts), {"awareness_at": inc.get("awareness_at"), "classified_at": clock_rules.iso(now)}, now)


def proposal_digest(facts):
    """What an approval is bound to: the incident (including when the firm became aware), the declared regulators and the rules in force. A change in any of them changes the hash."""
    body = {"incident": facts["incident"], "declared": declared(facts), "rules": facts.get("rules", [])}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def gate(facts, initiator="", now=None):
    now = now or datetime.now(timezone.utc); blocks, notes = [], []
    inc = facts.get("incident") or {}; regs = declared(facts); dec = facts.get("decision")
    if not inc: blocks.append("there is no such incident")
    if dec: blocks.append("this incident is already recorded as major (by %s); a decision is recorded once" % dec.get("set_by"))
    if not regs: blocks.append("no regulator is declared for this firm, so there would be no clock to start")
    if not blocks:
        pv = preview(facts, now)
        for c in pv["clocks"]: notes.append("%s: %s would be due %s%s" % (c["regulator"], c["title"], c["due_at"], " (the latest possible, if the earlier report goes at its deadline)" if "depends on when the previous report is sent" in c["flags"] else ""))
    notes.append("No rule decides that an incident is major or material. Approving this IS that decision, made by a named person.")
    excluded = sorted({initiator} | AGENT_ACTORS) if initiator else sorted(AGENT_ACTORS)
    return {"allowed_actions": [HOLD] if blocks else [RECORD, HOLD], "blocks": blocks, "notes": notes, "approvals_required": 1, "excluded_approvers": excluded, "action_help": ACTION_HELP,
            "checks": [{"rule": "the_incident_can_be_classified", "ok": not blocks, "detail": "; ".join(blocks) or "the incident exists, is not yet recorded, and %d regulator(s) are declared" % len(regs)}],
            "regimes": regs}


def may_approve(approver, already, gate_result):
    a = (approver or "").strip().lower()
    return bool(a) and a not in {x.lower() for x in gate_result["excluded_approvers"]} and a not in {x.lower() for x in already}
