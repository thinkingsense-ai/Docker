"""The rules gate for the incident-brief workflow (IT-risk root-cause analysis, docs/agency-risk-it.md section 6.3). Pure functions, no I/O: a risk partner can read and test them.
`gate(facts, initiator)` says which actions are allowed, how many distinct people must approve, who may not approve, and why. Whatever recommends only chooses among the allowed actions.

Actions: "publish" (the brief is fixed as this version and may go out) and "hold" (the brief stays a draft and the run records what it waits for). Publish is allowed only when every
check below holds, so a flat statement the evidence does not support can never be approved as a publication. Nothing is written to a customer system: the write-back is a dry run.
Facts come from rca_facts.gather: the claim, one cause per incident with its grade and source count, the open links, the controls, and who said each confirmed cause."""
import hashlib, json
import rca_judge, exposure_rules

PUBLISH, HOLD = "publish", "hold"
AGENT_ACTORS = {"treasury-agent", "policy-auto", "ai", "claude"}            # the AI and automation never approve
SPEAKERS_THAT_CONFIRM = ("operator", "regulator")                            # a cause is confirmed only when the company involved or a regulator says it
UNSOURCED_OK = ("inferred", "to_be_tested")
ACTION_HELP = {PUBLISH: "fix this brief, together with its exposure rating when it has one, as the published version (a dry run: nothing is sent anywhere)",
               HOLD: "keep the brief a draft and record what it is waiting for"}


def verdict_sentence(facts):
    """The one sentence on the claim. It names every open incident with its grade (the specification's costliest error is a flat 'no attack' while a cause is unnamed)."""
    c = facts.get("claim")
    if not c: return ""
    inc = facts.get("incidents", [])
    open_ = [i for i in inc if i["grade"] != "confirmed"]
    if c["verdict"] == "not_supported":
        names = ["%s (%s)" % (i["operator"], i["grade"].replace("_", " ")) for i in open_]
        return "No official source attributes any of the %d incidents to an attack" % len(inc) + (", but %s %s still open." % (" and ".join(names), "is" if len(names) == 1 else "are") if names else ".")
    if c["verdict"] == "supported": return "An official source supports the claim."
    return "There is not enough evidence to test the claim yet."


def checks(facts):
    inc, spk, c = facts.get("incidents", []), facts.get("speakers", []), facts.get("claim")
    out = []
    bad = [i["operator"] for i in inc if int(i["sources"]) == 0 and i["grade"] not in UNSOURCED_OK]
    out.append({"rule": "no_cause_without_evidence", "ok": not bad, "detail": ("%s: a cause with no source can only be inferred or to be tested" % ", ".join(bad)) if bad else "every cause has at least one source"})
    audited = facts.get("links") is not None          # with per-link sources the judge (below) covers this rule on every layer, so it is not reported twice
    weak = [] if audited else [i["operator"] for i in inc if i["grade"] == "confirmed" and not any(s["operator"] == i["operator"] and s["speaker_kind"] in SPEAKERS_THAT_CONFIRM for s in spk)]
    out.append({"rule": "confirmed_means_an_operator_or_regulator_said_it", "ok": not weak,
                "detail": ("%s: graded confirmed, but the source is reporting, not a named statement; get a primary source or regrade it as stated" % ", ".join(weak)) if weak else "covered by the link audit" if audited else "every confirmed cause has an operator or regulator behind it"})
    sentence = verdict_sentence(facts)
    open_ = [i["operator"] for i in inc if i["grade"] != "confirmed"]
    ok = bool(c) and (c["verdict"] != "not_supported" or all(o in sentence for o in open_))
    out.append({"rule": "no_flat_no_attack_while_a_cause_is_open", "ok": ok,
                "detail": "the verdict names the %d open incident(s)" % len(open_) if ok and open_ else "no incident is open" if ok else "the verdict must name every open incident"})
    links = facts.get("links")
    if links is None: out.append({"rule": "grades_match_the_evidence", "ok": True, "detail": "the links were not audited (no per-link sources in the facts)"})
    else:
        s = rca_judge.summary(rca_judge.audit(links))
        out.append({"rule": "grades_match_the_evidence", "ok": not s["blocks"], "detail": "; ".join(s["blocks"]) if s["blocks"] else "%d links audited: none graded above what its sources support" % s["audited"]})
    out.append(exposure_check(facts))
    out.append({"rule": "the_claim_has_a_verdict", "ok": bool(c) and bool(inc), "detail": "a verdict and at least one incident are present" if c and inc else "there is no claim or no incident for this case"})
    return out


def exposure_rating(facts):
    """The rating, recomputed here from the five answers (never trusted from a stored value), or None when this brief carries no assessed exposure."""
    e = facts.get("exposure")
    return exposure_rules.rate(e["answers"]) if e and e.get("assessed") else None


def exposure_check(facts):
    """The brief and the exposure rating are published together, so a rating that could not be completed (an unread estate, or a question with no answer) blocks publishing."""
    e = facts.get("exposure")
    if e is None: return {"rule": "exposure_is_rated", "ok": True, "detail": "no exposure assessment is part of these facts"}
    if e.get("error"): return {"rule": "exposure_is_rated", "ok": False, "detail": e["error"]}
    if not e.get("assessed"): return {"rule": "exposure_is_rated", "ok": True, "detail": "not assessed: %s" % e.get("reason", "no estate for this case")}
    r = exposure_rules.rate(e["answers"])
    if r["complete"]: return {"rule": "exposure_is_rated", "ok": True, "detail": "all five exposure questions were scored: %s" % r["sentence"]}
    why = "; ".join("question %d: %s" % (s["n"], s["reason"]) for s in r["scores"] if s["score"] is None)
    return {"rule": "exposure_is_rated", "ok": False, "detail": "the exposure rating is incomplete (%s)" % why}


def brief_digest(facts):
    """What an approval is bound to: the exact content of the brief (causes, grades, source counts, verdict, controls). A change in the data changes the hash."""
    body = {k: facts.get(k) for k in ("claim", "incidents", "open_links", "controls", "speakers", "links")}
    r = exposure_rating(facts)
    if r: body["exposure"] = {"answers": facts["exposure"]["answers"], "level": r["level"], "set_by": r["set_by"]}       # the approval covers the rating and the answers behind it
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def gate(facts, initiator="", today=None):
    cs = checks(facts)
    blocks = [c["detail"] for c in cs if not c["ok"]]
    notes = []
    inc = facts.get("incidents", [])
    open_ = [i for i in inc if i["grade"] != "confirmed"]
    if open_: notes.append("%d of %d causes are not confirmed: %s" % (len(open_), len(inc), "; ".join("%s (%s)" % (i["operator"], i["grade"].replace("_", " ")) for i in open_)))
    for l in facts.get("open_links", []): notes.append("%s is %s: %s" % (l["layer"].replace("_", " "), l["grade"].replace("_", " "), l["reason"]))
    er = exposure_rating(facts)
    if er: notes.append("Exposure: %s" % er["sentence"])
    excluded = sorted({initiator} | AGENT_ACTORS) if initiator else sorted(AGENT_ACTORS)
    return {"allowed_actions": [HOLD] if blocks else [PUBLISH, HOLD], "blocks": blocks, "notes": notes, "approvals_required": 1, "excluded_approvers": excluded,
            "action_help": ACTION_HELP, "checks": cs, "verdict_sentence": verdict_sentence(facts),
            "exposure": {"level": er["level"], "set_by": er["set_by"], "sentence": er["sentence"]} if er else None}


def may_approve(approver, already, gate_result):
    a = (approver or "").strip().lower()
    return bool(a) and a not in {x.lower() for x in gate_result["excluded_approvers"]} and a not in {x.lower() for x in already}
