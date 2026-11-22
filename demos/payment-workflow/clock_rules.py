"""The notification clocks after a MAJOR incident (docs/agency-risk-register-plan.md, section 5, step 8e). Pure functions, no I/O. A Python port of agency/web/src/clockModel.ts, tested against the shared
gold set (demos/it-risk-register/clocks_gold.json), so the screen and the workflow cannot disagree.

Nothing here decides that an incident is major or material: a person records that decision (the workflow major-incident), and only then do clocks exist. Nothing is sent to any regulator.
Rules come from register.notification_rules (our reading of public summaries, checked in SECONDARY sources, not against the regulations). Each rule counts `hours` from:
  classified       when a person recorded the incident as major
  awareness        when the firm became aware of it
  previous_report  when the stage before it was SENT. Nothing is sent here, so the latest possible time assumes the previous report went at ITS deadline.
A rule may also carry `also_within_hours_of_awareness`: a second limit; the earlier of the two applies. Only regulators the firm DECLARED apply. Timestamps are UTC (the Server returns them without a zone)."""
from datetime import datetime, timedelta, timezone
import re

_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$")


def parse_ts(s):
    """A timestamp as a UTC datetime. No zone means UTC. Returns None when it cannot be read."""
    if isinstance(s, datetime): return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    m = _TS.match(str(s or "").strip())
    if not m: return None
    y, mo, d, h, mi, se = (int(x) for x in m.groups()[:6]); z = m.group(7)
    off = 0 if z in (None, "Z") else (1 if z[0] == "+" else -1) * (int(z[1:3]) * 60 + (int(z[-2:]) if len(z) > 3 else 0))
    return datetime(y, mo, d, h, mi, se, tzinfo=timezone(timedelta(minutes=off))).astimezone(timezone.utc)


def iso(dt): return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(v):
    try: return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError): return None


def _hrs(h): return "%d hour%s" % (h, "" if h == 1 else "s")


def _true(v): return str(v).strip().lower() in ("true", "t", "1", "yes", "y")


def compute(rules, declared, decision, now):
    """rules: dicts with regulator, seq, stage, title, hours, starts_from, also_within_hours_of_awareness. declared: the regulators the firm declared. decision: {awareness_at, classified_at} or None.
    now: a datetime. Returns {"state": "no_decision" | "no_regulator" | "clocks", "clocks": [...]}, ordered by regulator then stage."""
    if not decision or not parse_ts(decision.get("classified_at")): return {"state": "no_decision", "clocks": []}
    cls, aw = parse_ts(decision["classified_at"]), parse_ts(decision.get("awareness_at"))
    mine = sorted((r for r in rules if r["regulator"] in set(declared)), key=lambda r: (r["regulator"], _num(r["seq"]) or 0))
    if not mine: return {"state": "no_regulator", "clocks": []}
    out, prev = [], {}
    for r in mine:
        h = _num(r["hours"]); w = _num(r.get("also_within_hours_of_awareness")); src = r["starts_from"]; why = []; flags = []; due = None
        if src == "classified": due = cls + timedelta(hours=h); why.append("%s after it was recorded as major" % _hrs(h))
        elif src == "awareness":
            if aw: due = aw + timedelta(hours=h); why.append("%s after the firm became aware" % _hrs(h))
            else: flags.append("no awareness time recorded")
        elif src == "previous_report":
            p = prev.get(r["regulator"])
            if p and p["due"]: due = p["due"] + timedelta(hours=h); why.append("%s after the previous report; the latest possible time, assuming it was sent at its deadline" % _hrs(h)); flags.append("depends on when the previous report is sent")
            else: flags.append("the previous stage has no deadline")
        if w is not None and aw:
            limit = aw + timedelta(hours=w)
            if due is None or limit < due: due = limit; why = ["%s after the firm became aware, which comes before %s after it was recorded as major" % (_hrs(w), _hrs(h))]
            else: why.append("and no later than %s after the firm became aware (%s), which is later" % (_hrs(w), iso(limit)))
        if due and due < cls and src == "classified": flags.append("already past when it was recorded as major")
        left = int((due - now).total_seconds()) if due else None
        c = {"rule_id": r.get("rule_id"), "regulator": r["regulator"], "stage": r["stage"], "title": r["title"], "due_at": iso(due) if due else None, "basis": "; ".join(why), "flags": flags,
             "state": None if due is None else "overdue" if left < 0 else "open", "seconds_left": left}
        out.append(c); prev[r["regulator"]] = {"due": due}
    return {"state": "clocks", "clocks": out}
