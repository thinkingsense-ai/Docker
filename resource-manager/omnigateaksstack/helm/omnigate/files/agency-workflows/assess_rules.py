"""The rules gate for the risk-assessment workflow (docs/agency-risk-register-plan.md, section 3 and 4). Pure functions, no I/O.
A first-line person starts a run for ONE system; the run reads the estate facts, proposes the rating the Priorities rules give (priority_rules, the same module the screen's port is tested against),
a category and the control evidence, and a second-line person approves or sends back. Approving writes one row to the register, never an edit: the register is append-only.
Actions: "record" (add this rating to the register) and "hold" (add nothing; say what the run is waiting for). Recording is allowed only when the rules can rate the system. Nothing computes residual
risk: the rating is inherent, with the control evidence beside it for the second line to judge."""
import hashlib, json
import priority_rules as P

RECORD, HOLD = "record", "hold"
AGENT_ACTORS = {"treasury-agent", "policy-auto", "ai", "claude"}                 # the AI and automation never approve
ACTION_HELP = {RECORD: "add this rating, its category and the control evidence to the risk register as a new row (the register is append-only; nothing in a customer system changes)",
               HOLD: "add nothing to the register and record what the run is waiting for"}
DUAL_ABOVE = "Critical"                                                         # a Critical rating needs two people, as the kill switch does (a demo constant)


def category_for(row):
    """The register category for a system, from the finding that most drives its likelihood. Ours, to be confirmed; the L2 category CR.TMF is used when nothing stands out."""
    n = lambda k: P._num(row.get(k)) or 0
    since = P._num(row.get("days_since_test"))
    never = str(row.get("recovery_result", "")).lower() == "never tested"
    if n("known_exploited_open") > 0 or n("open_patches") > 0: return "CR.AVM.PATCH"
    if n("credentials_wide") > 0: return "CR.TMF.DEC"
    if n("untested_changes") > 0: return "CR.TMF.CHG"
    if never or (since is not None and since > P.T["recoveryDays"]): return "CR.TMF.RRT"
    eos = row.get("end_of_support")
    if eos and P._days(str(eos), P.AS_OF) <= P.T["supportDays"]: return "CR.TMF.LEG"
    return "CR.TMF"


def control_evidence(row):
    """The facts a second-line person weighs. Plain text, built only from the row."""
    g = lambda k: row.get(k) if row.get(k) not in (None, "") else None
    parts = []
    parts.append("open patches: %s (known-exploited %s, highest exploit score %s)" % (g("open_patches") or 0, g("known_exploited_open") or 0, g("max_epss_open") or "none"))
    parts.append("changes without a pre-production test: %s" % (g("untested_changes") or 0))
    parts.append("last recovery test: %s" % ("never tested" if str(row.get("recovery_result", "")).lower() == "never tested" else "%s days ago" % g("days_since_test") if g("days_since_test") else "no record"))
    parts.append("credentials visible too widely: %s" % (g("credentials_wide") or 0))
    parts.append("end of vendor support: %s" % (g("end_of_support") or "none announced"))
    parts.append("dependants: %s" % (g("dependents") or 0))
    return "; ".join(parts) + "."


def proposal(facts):
    """The rating, recomputed here from the system's row (never trusted from a stored value), or None when the rules cannot rate it."""
    t = facts.get("table")
    level = (facts.get("exposure") or {}).get("level") if (facts.get("exposure") or {}).get("assessed") else None
    p = P.prioritise(t, level)
    if not p["ok"] or len(p["rows"]) != 1: return None
    r = p["rows"][0]; row = dict(zip([str(c).lower() for c in t["columns"]], t["rows"][0]))
    return {"system": r["system"], "rating": r["rating"], "likelihood": r["likelihood"], "impact": r["impact"], "triggers": r["triggers"], "lifted": r["lifted"], "reason": r["reason"],
            "likelihood_inputs": r["likelihood_inputs"], "impact_inputs": r["impact_inputs"], "category": category_for(row), "control_evidence": control_evidence(row)}


def assessment_digest(facts, prop):
    """What an approval is bound to: the exact row, the exposure rating used, and the proposed rating, category and evidence. A change in the data changes the hash."""
    body = {"row": facts.get("table"), "exposure": (facts.get("exposure") or {}).get("level"), "proposal": prop}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def gate(facts, initiator=""):
    prop = proposal(facts)
    blocks, notes = [], []
    if prop is None: blocks.append("the rules cannot rate this system from the facts read (a column is missing or no row came back)")
    cur = facts.get("register")
    if prop and cur:
        notes.append("The register already holds %s for this system (set by %s); a new row will not replace it, it will sit after it." % (cur.get("rating"), cur.get("set_by"))
                     + (" The rating is unchanged." if cur.get("rating") == prop["rating"] else ""))
    ex = facts.get("exposure") or {}
    notes.append("Exposure rating applied: %s." % ex["level"] if ex.get("assessed") and ex.get("level") else "Exposure rating not applied: %s." % ex.get("reason", "not assessed"))
    if prop: notes.append(prop["reason"])
    excluded = sorted({initiator} | AGENT_ACTORS) if initiator else sorted(AGENT_ACTORS)
    required = 2 if prop and prop["rating"] == DUAL_ABOVE else 1
    return {"allowed_actions": [HOLD] if blocks else [RECORD, HOLD], "blocks": blocks, "notes": notes, "approvals_required": required, "excluded_approvers": excluded, "action_help": ACTION_HELP,
            "checks": [{"rule": "the_system_can_be_rated", "ok": prop is not None, "detail": prop["reason"] if prop else blocks[0]}],
            "proposal": prop}


def may_approve(approver, already, gate_result):
    a = (approver or "").strip().lower()
    return bool(a) and a not in {x.lower() for x in gate_result["excluded_approvers"]} and a not in {x.lower() for x in already}
