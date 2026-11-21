"""The Priorities list for the risk-assessment workflow (docs/agency-risk-register-plan.md, section 4). A Python port of agency/web/src/priorityModel.ts: the same rules, tested against the shared
gold set (demos/it-risk-estate/priority_gold.json), so the screen and the approval gate cannot disagree. Pure functions, no I/O. A method, not a standard; every threshold is a demo constant."""
from datetime import date

AS_OF = "2026-11-20"
T = {"highEpss": 0.5, "midEpss": 0.1, "supportDays": 90, "recoveryDays": 180, "manyDependants": 3}
RATINGS = ("Low", "Medium", "High", "Critical")
NEEDS = ("system", "tier", "environment", "data_class", "internet_facing", "dependents", "open_patches", "known_exploited_open", "untested_changes", "days_since_test", "credentials_wide")
TRIGGERS = {
    "kev_exposed": "A known-exploited flaw is open on an internet-facing system of the top business tier.",
    "credential_shared": "A credential is visible beyond its owners or team.",
    "exposed_untested": "An internet-facing system has no recovery test in more than 180 days (or never).",
    "exposure_critical": "The exposure rating is already Critical and this system runs the affected technology.",
}


def _records(t):
    cols = [str(c).lower() for c in t["columns"]]
    return [{c: ("" if v is None else str(v)) for c, v in zip(cols, r)} for r in t["rows"]]


def _num(s):
    if s is None or s == "": return None
    try: return float(s)
    except ValueError: return None


def _yes(s): return str(s or "").strip().lower() in ("true", "t", "1", "yes", "y")
def _band(n): return RATINGS[max(0, min(3, n))]
def _days(a, b): return (date.fromisoformat(a[:10]) - date.fromisoformat(b)).days
def _fmt(v): return str(int(v)) if v == int(v) else str(v)


def _score(r, as_of, exposure_level):
    tier = _num(r.get("tier")); deps = int(_num(r.get("dependents")) or 0); kev = _num(r.get("known_exploited_open")) or 0; opn = _num(r.get("open_patches")) or 0
    epss = _num(r.get("max_epss_open")); untested = _num(r.get("untested_changes")) or 0; creds = _num(r.get("credentials_wide")) or 0
    since = _num(r.get("days_since_test")); net = _yes(r.get("internet_facing"))
    never = r.get("recovery_result", "").lower() == "never tested"
    stale = never or (since is not None and since > T["recoveryDays"])
    eos = _days(r["end_of_support"], as_of) if r.get("end_of_support") else None
    notes = []
    lk = []; l = 0
    if kev > 0: l = 3; lk.append("a known-exploited flaw is open")
    if creds > 0: l = 3; lk.append("a credential is visible beyond its owners or team")
    if l < 2 and (epss or 0) >= T["highEpss"]: l = 2; lk.append("an open flaw has an exploit score of %s" % _fmt(epss))
    if l < 2 and net and opn > 0: l = 2; lk.append("it is internet-facing with a flaw open")
    if l < 1:
        if (epss or 0) >= T["midEpss"]: l = 1; lk.append("an open flaw has an exploit score of %s" % _fmt(epss))
        if untested > 0: l = 1; lk.append("a change skipped pre-production testing")
        if eos is not None and eos <= T["supportDays"]: l = 1; lk.append("vendor support has ended" if eos < 0 else "vendor support ends in %d days" % eos)
        if stale: l = 1; lk.append("recovery was never tested" if never else "the last recovery test was %s days ago" % _fmt(since))
    if since is None and not never: notes.append("No recovery test on record.")
    im = []; i = 2 if tier == 1 else 1 if tier == 2 else 0
    im.append("no business tier recorded" if tier is None else "tier %s" % _fmt(tier))
    if r.get("data_class") == "restricted": i += 1; im.append("restricted data")
    if deps >= T["manyDependants"]: i += 1; im.append("%d dependants" % deps)
    if r.get("environment", "").lower() not in ("production", "dr"): i -= 1; im.append("not production")
    i = max(0, min(3, i))
    trig = []
    if kev > 0 and net and tier == 1: trig.append("kev_exposed")
    if creds > 0: trig.append("credential_shared")
    if net and stale: trig.append("exposed_untested")
    if exposure_level == "Critical" and _num(r.get("in_scenario")) == 1: trig.append("exposure_critical")
    base = l + i
    rating = _band(0 if base <= 1 else 1 if base <= 3 else 2 if base <= 5 else 3)
    lifted = bool(trig) and RATINGS.index(rating) < 2
    if lifted: rating = "High"
    reason = "%s: %s likelihood (%s), %s impact (%s)." % (rating, _band(l), ", ".join(lk) if lk else "nothing found that raises it", _band(i), ", ".join(im))
    if trig: reason += " %s: %s" % ("Lifted to High by" if lifted else "Also hit", " ".join(TRIGGERS[t] for t in trig))
    return {"system": r.get("system", ""), "tier": tier, "rating": rating, "likelihood": _band(l), "impact": _band(i), "triggers": trig, "lifted": lifted, "dependents": deps, "reason": reason, "notes": notes}


def prioritise(t, exposure_level=None, as_of=AS_OF):
    if not t: return {"rows": [], "ok": False, "missing": list(NEEDS), "sentence": "The question was not answered, so there is no list."}
    cols = [str(c).lower() for c in t["columns"]]
    missing = [c for c in NEEDS if c not in cols]
    if missing: return {"rows": [], "ok": False, "missing": missing, "sentence": "The answer did not have the columns the rules need (%s), so there is no list." % ", ".join(missing)}
    rows = [_score(r, as_of, exposure_level) for r in _records(t)]
    rows.sort(key=lambda x: (-RATINGS.index(x["rating"]), -len(x["triggers"]), -x["dependents"], x["tier"] if x["tier"] is not None else 9, x["system"]))
    n = lambda r: sum(1 for x in rows if x["rating"] == r)
    return {"rows": rows, "ok": True, "missing": [], "sentence": "%d systems ranked: %d Critical, %d High, %d Medium, %d Low." % (len(rows), n("Critical"), n("High"), n("Medium"), n("Low"))}
