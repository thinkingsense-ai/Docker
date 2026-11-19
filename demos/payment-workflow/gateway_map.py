"""Pure mapping between the Server's workflow engine contract (docs/workflows-api.md in the Server repo, "Engine gateway contract") and the payment-exception Temporal workflow's
state. No Temporal import here, so it is unit-tested without the SDK (tests/test_gateway.py).

Server run stages: facts, rules, recommendation, awaiting_approval, approved, written_back, rejected. The workflow adds two endings the Server has no stage for:
`escalated` (the AI chose "escalate", nothing is written, a person takes over) and `expired` (no decision before the deadline). Both are reported as `rejected` by the user "engine"
with the reason spelled out, so the card reads honestly even though the stage name is not a perfect fit."""
import hmac, re

DEFINITION = "payment-exception"
IT_DEFINITION = "vulnerability-exception"
DEFINITIONS = {DEFINITION: {"prefix": "payment", "key": "payment_id", "what": "a payment id"}, IT_DEFINITION: {"prefix": "vuln", "key": "vuln_id", "what": "a vulnerability id"}}
RUN_ID = re.compile(r"^(payment|vuln)-(\d{1,12})$")
STAGES = {"starting": "facts", "facts": "facts", "rules": "rules", "recommendation": "recommendation", "awaiting_approval": "awaiting_approval",
          "writing_back": "approved", "done": "written_back", "rejected": "rejected", "escalated": "rejected", "expired": "rejected"}
AGENTS = {"treasury-agent", "policy-auto", "ai", "claude"}            # rules.AGENT_ACTORS: automation never approves


class Refusal(Exception):
    def __init__(self, status, code, message): super().__init__(message); self.status, self.code = status, code


def definition_of(rid):
    """The definition a run id belongs to (payment-35 -> payment-exception, vuln-6 -> vulnerability-exception)."""
    return next(d for d, x in DEFINITIONS.items() if rid.startswith(x["prefix"] + "-"))


def run_id(key, definition=DEFINITION):
    """The Temporal workflow id, deliberately the same one the approval inbox uses: one payment, one run, whichever front end started it."""
    d = DEFINITIONS[definition]; k = str(key).strip()
    if not re.fullmatch(r"\d{1,12}", k): raise Refusal(400, "bad_request", "key must be %s (digits only)" % d["what"])
    return "%s-%d" % (d["prefix"], int(k))


def check_start(body):
    if not isinstance(body, dict): raise Refusal(400, "bad_request", "a JSON object is required")
    definition = body.get("definition")
    if definition not in DEFINITIONS: raise Refusal(404, "unknown_definition", "this gateway runs: %s" % ", ".join(repr(d) for d in DEFINITIONS))
    initiator = body.get("initiator")
    if not isinstance(initiator, str) or not initiator.strip() or len(initiator) > 200: raise Refusal(400, "bad_request", "initiator is required")
    q = body.get("queryId")
    return {"id": run_id(body.get("key"), definition), "definition": definition, "initiator": initiator.strip(), "queryId": q if isinstance(q, str) and len(q) <= 200 else None,
            "requiredApprovals": body.get("requiredApprovals") if isinstance(body.get("requiredApprovals"), int) else 2}


def _rules(gate):
    out = [{"name": "block", "passed": False, "detail": b} for b in (gate or {}).get("blocks", [])]
    out += [{"name": "note", "passed": True, "detail": n} for n in (gate or {}).get("notes", [])]
    allowed = (gate or {}).get("allowed_actions")
    if allowed: out.append({"name": "allowed_actions", "passed": True, "detail": "The rules allow: " + ", ".join(allowed)})
    return out


def _call(wb):
    s = (wb or {}).get("would_send") or (wb or {}).get("sent") or {}
    target = s.get("path") or s.get("url") or ""
    return ("%s %s" % (s.get("method", "POST"), target)).strip()


def to_run(rid, st, requested=2, created=None, updated=None):
    """The Server's RunState (camelCase, ISO times, string evidence) from the workflow's `status` query."""
    stage = STAGES.get(st.get("stage"), "facts")
    rec, gate = st.get("recommendation"), st.get("gate")
    approvals = [{"user": a["approver"], "at": a["at"]} for a in st.get("approvals", [])]
    rejection = st.get("rejection")
    if rejection: rejection = {"user": rejection["approver"], "reason": rejection["reason"], "at": rejection["at"]}
    elif st.get("stage") == "escalated": rejection = {"user": "engine", "reason": "The recommendation was to escalate to a person; nothing was written.", "at": updated}
    elif st.get("stage") == "expired": rejection = {"user": "engine", "reason": "No decision before the deadline; escalated to a person.", "at": updated}
    wb = st.get("write_back")
    write_back = None
    if wb:
        dry = wb.get("mode") in ("dry-run", "no-write")
        write_back = {"mode": "dry_run" if dry else wb.get("mode", ""), "status": "simulated" if dry else "sent", "call": _call(wb) or wb.get("note", ""), "at": updated}
    definition = definition_of(rid)
    evidence = {DEFINITIONS[definition]["key"]: rid.split("-", 1)[1]}
    evidence.update({k: str(v) for k, v in (st.get("facts_summary") or {}).items() if v is not None})
    return {"id": rid, "definition": definition, "key": rid.split("-", 1)[1], "initiator": st.get("initiator") or "(started in the approval inbox)", "queryId": st.get("queryId"),
            "stage": stage,
            "recommendation": {"action": rec["recommendation"], "reason": "; ".join(rec.get("reasons") or []) or "no reasons given", "source": rec.get("model") or "workflow"} if rec else None,
            "rules": _rules(gate) if stage not in ("facts", "rules") else [], "evidence": evidence if stage != "facts" else {}, "approvals": approvals,
            "requiredApprovals": int(st.get("approvals_required") or requested), "payloadHash": st.get("payload_hash") if stage != "facts" else None,
            "rejection": rejection, "writeBack": write_back, "createdAt": created, "updatedAt": updated}


def precheck(st, signal):
    """The engine's second line (the Server has already checked): refuse synchronously, because a Temporal signal is fire-and-forget and the workflow would only ignore a bad one.
    Returns None when the signal may be sent, else raises Refusal with the Server's own codes."""
    kind = signal.get("type"); user = signal.get("user")
    if kind not in ("approve", "reject"): raise Refusal(400, "bad_request", "type must be approve or reject")
    if not isinstance(user, str) or not user.strip() or len(user) > 200: raise Refusal(400, "bad_request", "user is required")
    u = user.strip().lower()
    if u in AGENTS: raise Refusal(403, "non_human_identity", "an AI, agent or service identity cannot approve or reject")
    if st.get("stage") != "awaiting_approval": raise Refusal(409, "not_awaiting_approval", "this run is not waiting for approval")
    if kind == "reject":
        r = signal.get("reason")
        if not isinstance(r, str) or not r.strip() or len(r) > 1000: raise Refusal(400, "bad_request", "a reason is required to reject")
        if u in {x.lower() for x in (st.get("gate") or {}).get("excluded_approvers", [])}: raise Refusal(403, "not_an_approver", "this person may not decide on this item")
        return
    if (st.get("initiator") or "").lower() == u: raise Refusal(403, "initiator_cannot_approve", "the person who started a run cannot approve it")
    if u in {x.lower() for x in (st.get("gate") or {}).get("excluded_approvers", [])}: raise Refusal(403, "not_an_approver", "this person initiated the payment or is an automated actor")
    if u in {a["approver"].lower() for a in st.get("approvals", [])}: raise Refusal(403, "already_approved", "this person already approved; one person counts once")
    h = signal.get("payloadHash")
    if not isinstance(h, str) or h != st.get("payload_hash"): raise Refusal(409, "payload_hash_mismatch", "the payload hash does not match the run's current action")


def token_ok(header, token):
    """Constant-time check of `Authorization: Bearer <token>`. An unset token never matches (the service refuses to start without one)."""
    if not token: return False
    given = header[7:] if isinstance(header, str) and header.startswith("Bearer ") else ""
    return hmac.compare_digest(given.encode(), token.encode())
