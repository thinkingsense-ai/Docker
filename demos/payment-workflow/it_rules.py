"""The rules gate for the vulnerability-exception workflow (IT and operational risk pack). Pure functions, no I/O: a risk partner can read and test them.
`gate(facts, initiator)` says which actions are allowed, how many distinct people must approve, who may not approve, and why. The AI only ever chooses among the allowed actions.

Actions: "remediate" (raise an urgent remediation request with the application owner and the vendor, and bring the vendor assessment forward),
"grant_exception" (a time-limited exception, with a named owner accepting the risk) and "escalate" (a person investigates; nothing is written).
The numbers below are DEMO POLICY CONSTANTS, not read from the data: a real deployment takes them from its own policy."""
from datetime import date

REMEDIATE, GRANT, ESCALATE = "remediate", "grant_exception", "escalate"
AGENT_ACTORS = {"treasury-agent", "policy-auto", "ai", "claude"}        # the AI and automation never approve
MAX_DAYS_OVERDUE_FOR_EXCEPTION = 30     # a critical finding more than this many days past its patch deadline cannot be excepted
OUTAGE_WINDOW_DAYS = 90                 # an outage in this window longer than the service's recovery objective blocks an exception
VENDOR_ASSESSMENT_MAX_DAYS = 365        # a critical (tier 1) third party must have been assessed within this many days
ACTION_HELP = {REMEDIATE: "raise an urgent remediation request with the application owner and the vendor; bring the vendor assessment forward",
               GRANT: "grant a time-limited exception (30 days) with a named owner accepting the residual risk",
               ESCALATE: "a person investigates; nothing is written"}


def to_date(x):
    """The query path returns dates as text (or a date); None for empty."""
    if x in (None, ""): return None
    if isinstance(x, date): return x
    return date.fromisoformat(str(x)[:10])


def days_between(later, earlier):
    a, b = to_date(later), to_date(earlier)
    return (a - b).days if a and b else None


def gate(facts, initiator="", today=None):
    today = to_date(today) or date.today()
    v, svc, vendor = facts["vulnerability"], facts["service"], facts.get("vendor")
    blocks, notes = [], []
    open_ = to_date(v.get("patched_on")) is None
    overdue = days_between(today, v.get("patch_due")) if open_ else None
    if not open_:
        blocks.append("the vulnerability is already patched (%s): there is nothing to decide" % v["patched_on"])
    else:
        if v.get("severity") == "Critical" and overdue is not None and overdue > MAX_DAYS_OVERDUE_FOR_EXCEPTION:
            blocks.append("a critical vulnerability is %d days past its patch deadline; an exception is allowed up to %d days" % (overdue, MAX_DAYS_OVERDUE_FOR_EXCEPTION))
        elif overdue is not None and overdue > 0:
            notes.append("%d days past its patch deadline" % overdue)
        elif overdue is not None:
            notes.append("the patch deadline is in %d days" % -overdue)
    for i in facts.get("incidents", []):
        d = days_between(today, i["started_on"])
        if d is not None and d <= OUTAGE_WINDOW_DAYS and int(i["duration_minutes"]) > int(svc["rto_minutes"]):
            blocks.append("%s had a %s outage of %s minutes %d days ago, longer than its %s-minute recovery objective" % (svc["service"], i["severity"], i["duration_minutes"], d, svc["rto_minutes"]))
    for r in facts.get("risks", []):
        if r.get("max_residual_score") is not None and int(r["residual_score"]) > int(r["max_residual_score"]):
            blocks.append("risk \"%s\" has residual score %s against the board's appetite of %s for %s" % (r["title"], r["residual_score"], r["max_residual_score"], r["category"]))
    for c in facts.get("controls", []):
        if c.get("control_type") != "Preventive": continue
        if c.get("last_result") == "Ineffective":
            blocks.append("preventive control \"%s\" was rated Ineffective" % c["title"])
        elif c.get("last_tested") and c.get("test_every_days") and days_between(today, c["last_tested"]) > int(c["test_every_days"]):
            blocks.append("preventive control \"%s\" is overdue for testing (last tested %s, due every %s days)" % (c["title"], c["last_tested"], c["test_every_days"]))
    if vendor and int(vendor.get("tier") or 9) == 1:
        age = days_between(today, vendor.get("last_assessed"))
        if age is not None and age > VENDOR_ASSESSMENT_MAX_DAYS:
            blocks.append("critical third party %s was last assessed %d days ago (limit %d)" % (vendor["name"], age, VENDOR_ASSESSMENT_MAX_DAYS))
    tier1 = int(svc["tier"]) == 1
    if tier1: notes.append("%s is a tier-1 service: two different approvers are required" % svc["service"])
    allowed = [REMEDIATE, ESCALATE] if (blocks and open_) else ([ESCALATE] if not open_ else [REMEDIATE, GRANT, ESCALATE])
    return {"allowed_actions": allowed, "action_help": ACTION_HELP, "approvals_required": 2 if tier1 else 1, "blocks": blocks, "notes": notes,
            "excluded_approvers": sorted(({initiator} if initiator else set()) | AGENT_ACTORS)}


def may_approve(approver, already, gate_result):
    a = (approver or "").strip().lower()
    return bool(a) and a not in {x.lower() for x in gate_result["excluded_approvers"]} and a not in {x.lower() for x in already}
