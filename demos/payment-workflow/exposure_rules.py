"""The exposure rating for the incident-brief workflow (docs/agency-it-risk-flow.md, section 6.3). A Python port of agency/web/src/exposureModel.ts: the same rules, tested against the same
gold set (demos/it-risk-estate/exposure_gold.json), so the screen and the approval gate cannot disagree. Pure functions, no I/O.
Each of five answers scores 0 to 3; the overall rating is the HIGHEST score, never an average, with the question(s) that set it. A question that cannot be answered is unknown, never 0.
Answers are tables {"columns": [...], "rows": [[...]]} as the five approved questions return them."""
THRESHOLDS = {"patchDays": 15, "recoveryDays": 180, "retestSoonDays": 90, "widePeople": 100}      # demo constants; the head of technology risk owns them in a real deployment
KEYS = ("systems", "access", "places", "exposures", "recovery")
LEVELS = ("Low", "Moderate", "High", "Critical")
SCORE_LABEL = ("No concern", "Watch", "Concern", "Critical")
NEEDS = {"systems": ["system", "technology", "tier"], "access": ["resource", "data_class", "reachable_by", "people", "reach"], "places": ["system", "location", "kind", "visible_to", "people"],
         "exposures": ["system", "finding", "detail", "days"], "recovery": ["system", "tier", "dependents", "result", "days_since_test"]}
WIDE = ("department", "company", "external", "anyone", "public")
T = THRESHOLDS


def records(t):
    cols = [str(c).lower() for c in t["columns"]]
    return [{c: ("" if v is None else str(v)) for c, v in zip(cols, r)} for r in t["rows"]]


def num(s):
    if s is None or s == "": return None
    try: return float(s)
    except ValueError: return None


def names(r, f): return ", ".join(dict.fromkeys(x[f] for x in r))
def plural(n): return "" if n == 1 else "s"


def systems(r):
    tier1 = [x for x in r if num(x["tier"]) == 1]
    if tier1: return 2, "%d system%s run the affected technology, %d of them tier 1 (%s)." % (len(r), plural(len(r)), len(tier1), names(tier1, "system")), tier1
    if r: return 1, "%d system%s run the affected technology, none tier 1." % (len(r), plural(len(r))), r
    return 0, "No system here runs the affected technology.", []


def access(r):
    wide = [x for x in r if x["reach"] != "owner team"]
    big = lambda x: (num(x["people"]) or 0) >= T["widePeople"]
    a = [x for x in wide if x["data_class"] == "restricted" and big(x)]
    if a: return 3, "Restricted data is reachable beyond its owner team by %d or more people: %s." % (T["widePeople"], names(a, "resource")), a
    b = [x for x in wide if x["data_class"] == "restricted"]; c = [x for x in wide if x["data_class"] == "confidential" and big(x)]
    if b or c:
        parts = ([("Restricted data is reachable beyond its owner team (%s)" % names(b, "resource"))] if b else []) + ([("confidential data by %d or more people (%s)" % (T["widePeople"], names(c, "resource")))] if c else [])
        return 2, "; ".join(parts) + ".", b + c
    d = [x for x in wide if x["data_class"] == "confidential"]
    if d: return 1, "Confidential data is reachable beyond its owner team by fewer than %d people (%s)." % (T["widePeople"], names(d, "resource")), d
    return 0, ("Data of this class is reachable only by its owner team." if r else "No restricted or confidential data in scope."), []


def places(r):
    wide = [x for x in r if x["visible_to"] in WIDE]
    cred = [x for x in wide if x["kind"] == "credential"]
    if cred: return 3, "A credential is visible beyond its owners or team: %s." % "; ".join("%s (%s, %s people)" % (x["location"], x["visible_to"], x["people"]) for x in cred), cred
    big = [x for x in wide if (num(x["people"]) or 0) >= T["widePeople"]]
    if big: return 2, "Runbooks or recovery steps are visible to %d or more people: %s." % (T["widePeople"], "; ".join("%s (%s)" % (x["location"], x["people"]) for x in big)), big
    if wide: return 1, "Runbooks or recovery steps are visible beyond the team to fewer than %d people: %s." % (T["widePeople"], "; ".join(x["location"] for x in wide)), wide
    return 0, ("Runbooks, credentials and recovery steps are visible only to their owners or team." if r else "None found in SharePoint or Slack."), []


def exposures(r):
    patch = [x for x in r if x["finding"] == "security patch overdue"]; change = [x for x in r if x["finding"] == "change without a pre-production test"]
    long_ = [x for x in patch if (num(x["days"]) or 0) > T["patchDays"]]
    both = [p for p in long_ if any(c["system"] == p["system"] for c in change)]
    if both: return 3, "%s: a security patch overdue by more than %d days and a recent change that skipped pre-production testing." % (names(both, "system"), T["patchDays"]), both + [c for c in change if any(p["system"] == c["system"] for p in both)]
    if long_ or len(change) >= 2:
        parts = ([("Security patch overdue by more than %d days: %s" % (T["patchDays"], ", ".join("%s (%s)" % (x["system"], x["days"]) for x in long_)))] if long_ else []) + ([("%d recent changes skipped pre-production testing" % len(change))] if len(change) >= 2 else [])
        return 2, "; ".join(parts) + ".", long_ + (change if len(change) >= 2 else [])
    if patch or change:
        parts = (["A security patch is overdue by up to %d days" % T["patchDays"]] if patch else []) + (["one recent change skipped pre-production testing"] if change else [])
        return 1, "; ".join(parts) + ".", patch + change
    return 0, "No security patch is overdue and no recent change skipped testing.", []


def recovery(r):
    age = lambda x: num(x["days_since_test"])
    stale = lambda x: age(x) is None or age(x) > T["recoveryDays"]
    t1 = [x for x in r if num(x["tier"]) == 1 and stale(x)]
    shown = lambda x: "never" if age(x) is None else "%d days" % age(x)
    if t1: return 3, "Tier 1 and last recovery-tested more than %d days ago or never: %s." % (T["recoveryDays"], ", ".join("%s (%s)" % (x["system"], shown(x)) for x in t1)), t1
    slow = [x for x in r if num(x.get("rto_actual_minutes")) is not None and num(x.get("rto_target_minutes")) is not None and num(x["rto_actual_minutes"]) > num(x["rto_target_minutes"])]
    other = [x for x in r if stale(x)]
    if other or slow:
        parts = ([("Last tested more than %d days ago or never: %s" % (T["recoveryDays"], ", ".join(x["system"] for x in other)))] if other else []) + ([("Took longer than its target: %s" % ", ".join(x["system"] for x in slow))] if slow else [])
        return 2, "; ".join(parts) + ".", other + [s for s in slow if s not in other]
    old = [x for x in r if age(x) is not None and age(x) > T["retestSoonDays"]]
    if old: return 1, "A recovery test is more than %d days old: %s." % (T["retestSoonDays"], ", ".join("%s (%d)" % (x["system"], age(x)) for x in old)), old
    return 0, "Every system was recovery-tested recently and within its target.", []


FN = {"systems": systems, "access": access, "places": places, "exposures": exposures, "recovery": recovery}


def _unknown(i, k, why): return {"key": k, "n": i + 1, "score": None, "label": "Unknown", "reason": why}


def rate(answers):
    """Scores the five answers. A missing answer, one without the expected columns, or a recovery answer that does not cover every system scores unknown, never 0."""
    in_scope = len(answers["systems"]["rows"]) if answers.get("systems") else None
    scores = []
    for i, k in enumerate(KEYS):
        t = answers.get(k)
        if not t: scores.append(_unknown(i, k, "This question was not answered, so it cannot be scored.")); continue
        cols = [str(c).lower() for c in t["columns"]]
        missing = [c for c in NEEDS[k] if c not in cols]
        if missing: scores.append(_unknown(i, k, "The answer did not have the columns this rule needs (%s), so it cannot be scored." % ", ".join(missing))); continue
        if k == "recovery" and in_scope is not None and len(t["rows"]) < in_scope: scores.append(_unknown(i, k, "Recovery answered for %d of %d systems, so it cannot be scored." % (len(t["rows"]), in_scope))); continue
        s, why, evidence = FN[k](records(t))
        scores.append({"key": k, "n": i + 1, "score": s, "label": SCORE_LABEL[s], "reason": why, "evidence_rows": len(evidence)})
    known = [s for s in scores if s["score"] is not None]; unknown = [s["n"] for s in scores if s["score"] is None]
    top = max(s["score"] for s in known) if known else None
    set_by = [s["n"] for s in known if s["score"] == top] if known else []
    level = LEVELS[top] if top is not None else None
    q = lambda ns: "question%s %s" % ("" if len(ns) == 1 else "s", " and ".join(map(str, ns)))
    sentence = "No question could be scored, so there is no rating." if level is None else (("At least %s: " if unknown else "%s: ") % level) + "set by %s%s." % (q(set_by), ("; %s could not be scored, so the rating may be higher" % q(unknown)) if unknown else "")
    return {"scores": scores, "score": top, "level": level, "set_by": set_by, "unknown": unknown, "complete": not unknown, "sentence": sentence, "thresholds": dict(T)}
