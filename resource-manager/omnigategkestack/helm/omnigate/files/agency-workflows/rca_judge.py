"""The link judge for the IT-risk root-cause analysis (docs/agency-risk-it.md section 6.4). Pure functions, no I/O, no model: a risk partner can read, challenge and test every rule.

`judge_link(link)` recomputes, from a link's sources alone, the strongest grade they support. `audit_link(link)` compares that with the grade the link CARRIES and says whether the link
states more than its evidence does (overstated), less (understated), or the same. The grade vocabulary is the specification's: confirmed, stated, disputed, not_named, inferred, to_be_tested.

A link is {layer, grade, has_control, sources:[{signal_id, speaker, speaker_kind, source_kind, relation, asserts}]}:
  speaker_kind  operator (the company involved) | regulator (a government body or its head) | reporting | union | reference
  relation      states (the source says it) | context (background, never raises a grade) | silent (an official source that names no cause)
  asserts       a short key for WHAT is said, so two official sources that say different things are seen to differ

Rules, in order (the rubric a person can read):
  1. Social sources and context rows are leads, never evidence: they are ignored.
  2. symptom: acknowledged by anyone who is not a social source -> confirmed.
  3. cause: official statements (operator or regulator) with two or more different `asserts` -> disputed; exactly one `asserts` -> confirmed; an official source that is silent -> not_named;
     only reporting, union or reference statements -> stated (attributed to who said it); nothing usable -> inferred (our reasoning, with no source).
  4. driver, root_condition: two or more different official parties say the same thing -> confirmed; one official party -> stated (nobody corroborates it); nothing usable -> to_be_tested when the
     link has a control that could test it (has_control), else inferred.
A link states a fact only when graded confirmed or stated; anything else must read as open, disputed, inferred or to be tested."""
OFFICIAL = ("operator", "regulator")
FACT = ("confirmed", "stated")
STRENGTH = {"confirmed": 3, "stated": 2, "inferred": 1, "to_be_tested": 1, "disputed": 0, "not_named": 0}


def judge_link(link):
    layer = link["layer"]
    use = [s for s in link.get("sources", []) if s.get("source_kind") != "social" and s.get("relation") in ("states", "silent")]
    states = [s for s in use if s["relation"] == "states"]
    official = [s for s in states if s.get("speaker_kind") in OFFICIAL and s.get("asserts")]
    ignored = [s for s in link.get("sources", []) if s not in use]
    if layer == "symptom":
        if states: return {"grade": "confirmed", "why": "the event is acknowledged by a non-social source"}
        return {"grade": "inferred", "why": "no usable source acknowledges the event"}
    if layer == "cause":
        keys = sorted({s["asserts"] for s in official})
        if len(keys) >= 2: return {"grade": "disputed", "why": "official sources say different things: %s" % ", ".join(keys)}
        if len(keys) == 1: return {"grade": "confirmed", "why": "an operator or regulator states it and no official source differs"}
        if any(s["relation"] == "silent" and s.get("speaker_kind") in OFFICIAL for s in use): return {"grade": "not_named", "why": "an official source names no cause"}
        if any(s.get("asserts") for s in states): return {"grade": "stated", "why": "only reporting, a union or a reference page says it; no operator or regulator statement"}
        return {"grade": "inferred", "why": "no usable source%s" % (" (only social or context rows)" if ignored else "")}
    parties = sorted({s["speaker"] for s in official})
    if len(parties) >= 2: return {"grade": "confirmed", "why": "%d official parties say it" % len(parties)}
    if len(parties) == 1: return {"grade": "stated", "why": "one official party says it (%s) and nobody corroborates it" % parties[0]}
    return {"grade": "to_be_tested" if link.get("has_control") else "inferred", "why": "no official source says it" + (" (only social or context rows)" if ignored else "")}


def audit_link(link):
    j = judge_link(link); claimed = link["grade"]; sup = j["grade"]
    over = (claimed in FACT and sup not in FACT) or (claimed == "confirmed" and sup == "stated")
    under = (not over) and claimed != sup and STRENGTH.get(claimed, 0) < STRENGTH.get(sup, 0)
    kind = "overstated" if over else "understated" if under else "match" if claimed == sup else "different"
    return {"link_id": link.get("link_id"), "layer": link["layer"], "claimed": claimed, "judged": sup, "kind": kind, "ok": not over, "why": j["why"], "who": link.get("who")}


def audit(links):
    return [audit_link(l) for l in links]


def summary(results):
    bad = [r for r in results if not r["ok"]]
    return {"audited": len(results), "overstated": len(bad), "understated": sum(1 for r in results if r["kind"] == "understated"),
            "blocks": ["%s %s is graded %s but its sources support %s: %s" % (r.get("who") or "link %s" % r["link_id"], r["layer"].replace("_", " "), r["claimed"].replace("_", " "), r["judged"].replace("_", " "), r["why"]) for r in bad]}
