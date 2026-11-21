"""The pilot harness (docs/agency-risk-register-plan.md, section 7, step 8h): put what the product raised in front of a risk partner as plain label sheets, then score the labels.
No model, no network except the Server's governed query path for `export`. Nothing here decides a rating; it only measures how often a person agrees with what the rules did.

  python3 demos/it-risk-pilot/pilot.py export --out DIR [--sample 40] [--seed 1]   write the three label sheets and manifest.json
  python3 demos/it-risk-pilot/pilot.py score  --dir DIR                           read the labelled sheets, write results.json and results.md
  python3 demos/it-risk-pilot/pilot.py bundle --dir DIR --to BUNDLE               a BLIND bundle for the reviewer (no ratings, no raised/not-raised split); our key stays in DIR/key.json
  python3 demos/it-risk-pilot/pilot.py merge  --dir DIR --returned RETURNED       put the reviewer's two returned sheets back, then run score

Three sheets (CSV, one label column each, filled in by the person):
  feed-raised.csv      what the feed raised as events under review      leo_label: relevant | not_for_us | not_real
  feed-not-raised.csv  a seeded random sample of what it did NOT raise   leo_label: the same three (what a person would have raised)
  priorities.csv       our ranked systems                               leo_rating: Critical | High | Medium | Low, leo_rank: 1 to n (his order of the top ten; blank allowed)
Labels mean: relevant = a real story that bears on AI-driven attack or weakness AND on a firm like ours; not_for_us = real but not for a firm like ours; not_real = not an incident (opinion, promotion, rumour).
Measured: precision of the feed (with a 95% Wilson interval, because the samples are small), an ESTIMATE of its recall from the not-raised sample, and for the priorities list precision and recall for Critical and High
only, the confusion by rating, and how well his order of the top ten matches ours. There is no target false-positive rate. Pure functions below are unit-tested (test_pilot.py)."""
import csv, datetime, json, math, os, random, re, sys

LABELS = ("relevant", "not_for_us", "not_real")
RATINGS = ("Low", "Medium", "High", "Critical")
HIGH = ("Critical", "High")
_ALIAS = {"relevant": "relevant", "realandrelevant": "relevant", "notforus": "not_for_us", "realbutnotforus": "not_for_us", "notreal": "not_real"}


def norm_label(s):
    """A label as typed (case, spaces, dashes, underscores ignored), or None when blank, or False when it is not one of the three."""
    k = re.sub(r"[^a-z]", "", (s or "").lower())
    return None if not k else _ALIAS.get(k, False)


def norm_rating(s):
    k = (s or "").strip().lower()
    return None if not k else next((r for r in RATINGS if r.lower() == k), False)


def wilson(k, n, z=1.96):
    """95% Wilson interval for k of n, or None when n is 0."""
    if n <= 0: return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - w) / d), min(1.0, (c + w) / d))


def _frac(k, n): return {"k": k, "n": n, "value": (k / n) if n else None, "wilson95": wilson(k, n)}


def feed_scores(raised, raised_population, unraised, unraised_population):
    """raised/unraised: lists of {"label": norm_label result}. Population sizes scale the recall estimate. Rows with no label are counted and left out."""
    lab = lambda rows: [r["label"] for r in rows if r["label"]]
    a = lab(raised); b = lab(unraised)
    out = {"raised": {"population": raised_population, "labelled": len(a), "unlabelled": len(raised) - len(a),
                      "relevant": a.count("relevant"), "not_for_us": a.count("not_for_us"), "not_real": a.count("not_real")}}
    out["raised"]["precision_relevant"] = _frac(a.count("relevant"), len(a))
    out["raised"]["precision_real"] = _frac(a.count("relevant") + a.count("not_for_us"), len(a))
    out["not_raised"] = {"population": unraised_population, "labelled": len(b), "unlabelled": len(unraised) - len(b), "relevant": b.count("relevant"), "not_for_us": b.count("not_for_us"), "not_real": b.count("not_real")}
    out["not_raised"]["relevant_share"] = _frac(b.count("relevant"), len(b))
    if a and b:
        got = a.count("relevant") / len(a) * raised_population                # relevant stories among everything raised, scaled from the labelled part
        lo, hi = wilson(b.count("relevant"), len(b))
        miss = lambda p: p * unraised_population
        est = lambda m: got / (got + m) if (got + m) else None
        out["recall_estimate"] = {"value": est(miss(b.count("relevant") / len(b))), "low": est(miss(hi)), "high": est(miss(lo)),
                                  "caveat": "An ESTIMATE from a small sample of what was not raised; the interval is wide on purpose. It counts only headlines the feed READ: a story no feed carried is invisible to it."}
    else: out["recall_estimate"] = None
    return out


def kendall_tau_b(pairs):
    """Rank correlation between two orders of the same items (-1 reversed to 1 identical), or None with fewer than two items."""
    n = len(pairs)
    if n < 2: return None
    c = d = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = pairs[i][0] - pairs[j][0], pairs[i][1] - pairs[j][1]
            if dx == 0 and dy == 0: continue
            if dx == 0: tx += 1
            elif dy == 0: ty += 1
            elif dx * dy > 0: c += 1
            else: d += 1
    den = math.sqrt((c + d + tx) * (c + d + ty))
    return (c - d) / den if den else None


def priorities_scores(rows):
    """rows: {system, our_rank (int), our_rating, leo_rating (canonical or None), leo_rank (int or None)}."""
    lab = [r for r in rows if r["leo_rating"]]
    ours = [r for r in lab if r["our_rating"] in HIGH]; his = [r for r in lab if r["leo_rating"] in HIGH]; both = [r for r in lab if r["our_rating"] in HIGH and r["leo_rating"] in HIGH]
    conf = {o: {h: 0 for h in RATINGS} for o in RATINGS}
    for r in lab: conf[r["our_rating"]][r["leo_rating"]] += 1
    step = {"exact": 0, "within_one": 0}
    for r in lab:
        g = abs(RATINGS.index(r["our_rating"]) - RATINGS.index(r["leo_rating"])); step["exact"] += g == 0; step["within_one"] += g <= 1
    out = {"labelled": len(lab), "unlabelled": len(rows) - len(lab), "critical_high": {"precision": _frac(len(both), len(ours)), "recall": _frac(len(both), len(his)),
           "we_said_high_he_did_not": [r["system"] for r in ours if r["leo_rating"] not in HIGH], "he_said_high_we_did_not": [r["system"] for r in his if r["our_rating"] not in HIGH]},
           "confusion_ours_by_his": conf, "agreement": {"exact": _frac(step["exact"], len(lab)), "within_one_step": _frac(step["within_one"], len(lab))}}
    ranked = [r for r in rows if r["leo_rank"] is not None]
    if ranked:
        k = min(10, len(ranked)); mine = {r["system"] for r in rows if r["our_rank"] <= k}; theirs = {r["system"] for r in ranked if r["leo_rank"] <= k}
        out["order"] = {"he_ranked": len(ranked), "k": k, "top_k_overlap": _frac(len(mine & theirs), k), "exact_positions": sum(1 for r in ranked if r["leo_rank"] == r["our_rank"]),
                        "kendall_tau_b": kendall_tau_b([(r["our_rank"], r["leo_rank"]) for r in ranked])}
    else: out["order"] = None
    return out


# ------------------------------------------------------------------------------------------------------------------------------------ sheets
FEED_COLS = ["candidate_id", "source", "source_kind", "claim_type", "first_seen", "headlines", "title", "url", "summary", "leo_label", "leo_note"]
UNRAISED_COLS = ["item_id", "source", "source_kind", "published_at", "title", "url", "leo_label", "leo_note"]
FACT_COLS = ["tier", "environment", "data_class", "internet_facing", "dependents", "end_of_support", "open_patches", "known_exploited_open", "max_epss_open", "untested_changes", "days_since_test", "recovery_result", "credentials_wide", "in_scenario", "loss_event"]
PRIO_COLS = ["our_rank", "system_id", "system", "our_rating", "our_reason"] + FACT_COLS + ["leo_rating", "leo_rank", "leo_note"]


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f: return list(csv.DictReader(f))


def sample_ids(ids, n, seed):
    """A reproducible random sample of ids: the same ids, population and seed give the same sample."""
    ids = sorted(ids); return sorted(random.Random(seed).sample(ids, min(n, len(ids))))


def load_labels(rows, col, parse, key):
    out, errors = [], []
    for i, r in enumerate(rows, 2):
        v = parse(r.get(col)); r = dict(r)
        if v is False: errors.append("row %d (%s): %r is not a valid %s" % (i, r.get(key), r.get(col), col)); v = None
        out.append(dict(r, label=v))
    return out, errors


def score(dirpath):
    with open(os.path.join(dirpath, "manifest.json")) as f: man = json.load(f)
    errors = []
    raised, e = load_labels(read_csv(os.path.join(dirpath, "feed-raised.csv")), "leo_label", norm_label, "candidate_id"); errors += e
    unraised, e = load_labels(read_csv(os.path.join(dirpath, "feed-not-raised.csv")), "leo_label", norm_label, "item_id"); errors += e
    prows, e = load_labels(read_csv(os.path.join(dirpath, "priorities.csv")), "leo_rating", norm_rating, "system"); errors += e
    plist = []
    for r in prows:
        try: lr = int(r["leo_rank"]) if (r.get("leo_rank") or "").strip() else None
        except ValueError: errors.append("system %s: leo_rank %r is not a number" % (r["system"], r["leo_rank"])); lr = None
        plist.append({"system": r["system"], "our_rank": int(r["our_rank"]), "our_rating": r["our_rating"], "leo_rating": r["label"], "leo_rank": lr})
    res = {"manifest": man, "errors": errors, "feed": feed_scores(raised, man["raised_population"], unraised, man["unraised_population"]), "priorities": priorities_scores(plist)}
    with open(os.path.join(dirpath, "results.json"), "w") as f: json.dump(res, f, indent=1, default=str)
    with open(os.path.join(dirpath, "results.md"), "w") as f: f.write(report(res))
    return res


def pct(f):
    if not f or f["value"] is None: return "n/a (nothing labelled)"
    lo, hi = f["wilson95"]; return "%d of %d = %.0f%% (95%% interval %.0f%% to %.0f%%)" % (f["k"], f["n"], 100 * f["value"], 100 * lo, 100 * hi)


def report(res):
    f, p, m = res["feed"], res["priorities"], res["manifest"]
    L = ["# Pilot results", "", "Sheets exported %s (as of %s). **Small samples: read the intervals, not the point values.** There is no target false-positive rate." % (m["created"], m["as_of"]), ""]
    if res["errors"]: L += ["## Labels that could not be read (left out)", ""] + ["- " + e for e in res["errors"]] + [""]
    r = f["raised"]; L += ["## The feed: what it raised", "", "- %d events under review; %d labelled, %d left blank." % (r["population"], r["labelled"], r["unlabelled"]),
                           "- Real and relevant: %s" % pct(r["precision_relevant"]), "- Real (relevant or not for us): %s" % pct(r["precision_real"]),
                           "- Not for us: %d. Not real: %d." % (r["not_for_us"], r["not_real"]), ""]
    n = f["not_raised"]; L += ["## The feed: what it did not raise (a sample)", "", "- %d headlines from reporting and official feeds were not raised; %d sampled and labelled, %d left blank." % (n["population"], n["labelled"], n["unlabelled"]),
                               "- A person would have raised: %s" % pct(n["relevant_share"])]
    e = f["recall_estimate"]
    L += ["- Estimated recall: " + ("%.0f%% (plausible range %.0f%% to %.0f%%). %s" % (100 * e["value"], 100 * e["low"], 100 * e["high"], e["caveat"]) if e and e["value"] is not None else "not available (label both sheets)"), ""]
    c = p["critical_high"]; L += ["## The priorities list (Critical and High)", "", "- %d systems labelled, %d left blank." % (p["labelled"], p["unlabelled"]), "- Precision: of the systems we rated Critical or High, he agreed on %s" % pct(c["precision"]),
                                  "- Recall: of the systems he rated Critical or High, we rated them so for %s" % pct(c["recall"]),
                                  "- We said Critical or High, he did not: %s" % (", ".join(c["we_said_high_he_did_not"]) or "none"), "- He said Critical or High, we did not: %s" % (", ".join(c["he_said_high_we_did_not"]) or "none"), "",
                                  "Rating agreement: exact %s; within one step %s." % (pct(p["agreement"]["exact"]), pct(p["agreement"]["within_one_step"])), "", "Our rating (rows) by his rating (columns):", "",
                                  "| ours \\ his | " + " | ".join(RATINGS) + " |", "|---|" + "---|" * len(RATINGS)]
    for o in reversed(RATINGS): L.append("| %s | " % o + " | ".join(str(p["confusion_ours_by_his"][o][h]) for h in RATINGS) + " |")
    o = p["order"]; L += ["", "## His order of the top ten against ours", ""]
    L.append("- He ranked %d. Top-%d overlap: %s. Exact positions: %d. Kendall tau-b: %s." % (o["he_ranked"], o["k"], pct(o["top_k_overlap"]), o["exact_positions"], "n/a" if o["kendall_tau_b"] is None else "%.2f" % o["kendall_tau_b"]) if o else "- He gave no order.")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------------------------------------------ blind bundle and merge
# What goes to the reviewer is BLIND: the raised stories and the not-raised sample are shuffled into one sheet with neutral ids, so they cannot tell which the feed raised; the systems come without our rating,
# rank or reasons, in alphabetical order, so their ratings are their own. The key that maps ids back is ours (key.json) and is never put in the bundle. Showing our answer beside the space for theirs would anchor them.
HEADLINE_COLS = ["id", "source", "source_kind", "date", "title", "url", "leo_label", "leo_note"]
SYSTEM_COLS = ["id", "system"] + FACT_COLS + ["leo_rating", "leo_rank", "leo_note"]


def bundle(dirpath, to, seed=1):
    """Writes the blind bundle into `to` and our private key into dirpath/key.json. Returns what was written."""
    raised = read_csv(os.path.join(dirpath, "feed-raised.csv")); unraised = read_csv(os.path.join(dirpath, "feed-not-raised.csv")); systems = read_csv(os.path.join(dirpath, "priorities.csv"))
    items = [("raised", r["candidate_id"], {"source": r["source"], "source_kind": r["source_kind"], "date": r["first_seen"], "title": r["title"], "url": r["url"]}) for r in raised]
    items += [("not_raised", r["item_id"], {"source": r["source"], "source_kind": r["source_kind"], "date": (r["published_at"] or "")[:10], "title": r["title"], "url": r["url"]}) for r in unraised]
    random.Random(seed).shuffle(items)
    key = {"headlines": {}, "systems": {}}; hrows = []
    for i, (origin, ref, row) in enumerate(items, 1):
        hid = "H%02d" % i; key["headlines"][hid] = {"origin": origin, "ref": ref}; hrows.append(dict(row, id=hid))
    srows = []
    for i, r in enumerate(sorted(systems, key=lambda x: x["system"].lower()), 1):
        sid = "S%02d" % i; key["systems"][sid] = {"system": r["system"], "our_rank": int(r["our_rank"]), "our_rating": r["our_rating"]}; srows.append(dict({c: r.get(c, "") for c in FACT_COLS}, id=sid, system=r["system"]))
    os.makedirs(to, exist_ok=True)
    write_csv(os.path.join(to, "1-headlines.csv"), HEADLINE_COLS, hrows); write_csv(os.path.join(to, "2-systems.csv"), SYSTEM_COLS, srows)
    with open(os.path.join(dirpath, "key.json"), "w") as f: json.dump(key, f, indent=1)
    return {"headlines": len(hrows), "systems": len(srows)}


def merge(dirpath, returned_dir):
    """Puts the reviewer's returned sheets back into the three sheets `score` reads, using our key. Returns the problems found (an id the key does not know, an id missing from the return)."""
    with open(os.path.join(dirpath, "key.json")) as f: key = json.load(f)
    problems = []
    hret = {r["id"]: r for r in read_csv(os.path.join(returned_dir, "1-headlines.csv"))}; sret = {r["id"]: r for r in read_csv(os.path.join(returned_dir, "2-systems.csv"))}
    for rid in list(hret) + list(sret):
        if rid not in key["headlines"] and rid not in key["systems"]: problems.append("the returned sheet has an id we did not send: %s" % rid)
    for hid in key["headlines"]:
        if hid not in hret: problems.append("headline %s is missing from the returned sheet" % hid)
    for sid in key["systems"]:
        if sid not in sret: problems.append("system %s is missing from the returned sheet" % sid)
    raised = {r["candidate_id"]: r for r in read_csv(os.path.join(dirpath, "feed-raised.csv"))}; unraised = {r["item_id"]: r for r in read_csv(os.path.join(dirpath, "feed-not-raised.csv"))}
    for hid, k in key["headlines"].items():
        got = hret.get(hid)
        if not got: continue
        target = raised if k["origin"] == "raised" else unraised
        if k["ref"] in target: target[k["ref"]]["leo_label"] = got.get("leo_label", ""); target[k["ref"]]["leo_note"] = got.get("leo_note", "")
    prio = {r["system"]: r for r in read_csv(os.path.join(dirpath, "priorities.csv"))}
    for sid, k in key["systems"].items():
        got = sret.get(sid)
        if got and k["system"] in prio: prio[k["system"]]["leo_rating"] = got.get("leo_rating", ""); prio[k["system"]]["leo_rank"] = got.get("leo_rank", ""); prio[k["system"]]["leo_note"] = got.get("leo_note", "")
    write_csv(os.path.join(dirpath, "feed-raised.csv"), FEED_COLS, list(raised.values())); write_csv(os.path.join(dirpath, "feed-not-raised.csv"), UNRAISED_COLS, list(unraised.values()))
    write_csv(os.path.join(dirpath, "priorities.csv"), PRIO_COLS, sorted(prio.values(), key=lambda r: int(r["our_rank"])))
    return problems


# ------------------------------------------------------------------------------------------------------------------------------------ export (needs the Server)
def export(out, sample, seed):
    here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(here, "..", "payment-workflow"))
    os.environ.setdefault("ASK_URL", "http://localhost:8080"); os.environ.setdefault("RCA_TABLE_PREFIX", "pg."); os.environ.setdefault("RCA_WORKSPACE", "it-risk")
    import facts, priority_rules, assess_facts, exposure_facts, exposure_rules
    p = os.environ["RCA_TABLE_PREFIX"]; ws = os.environ["RCA_WORKSPACE"]
    q = lambda sql: facts.query(sql.replace("{p}", p), ws)
    cands = q("SELECT c.candidate_id, c.claim_type, c.first_seen, c.summary, i.title, i.url, s.name AS source, s.kind AS source_kind FROM {p}rca.candidates c JOIN {p}rca.feed_items i ON i.item_id = c.lead_item_id "
              "JOIN {p}rca.feed_sources s ON s.source_id = i.source_id WHERE c.candidate_id >= 1000 ORDER BY c.candidate_id")
    n = {int(r["candidate_id"]): int(r["n"]) for r in q("SELECT candidate_id, COUNT(*) AS n FROM {p}rca.candidate_feed_items GROUP BY candidate_id")}
    for c in cands: c["headlines"] = n.get(int(c["candidate_id"]), 1)
    pool = q("SELECT i.item_id, i.title, i.url, i.published_at, s.name AS source, s.kind AS source_kind FROM {p}rca.feed_items i JOIN {p}rca.feed_sources s ON s.source_id = i.source_id "
             "WHERE i.matched = FALSE AND s.kind IN ('reporting','official') ORDER BY i.item_id")
    keep = set(sample_ids([int(r["item_id"]) for r in pool], sample, seed)); picked = [r for r in pool if int(r["item_id"]) in keep]
    cols, rows = facts.query_table(assess_facts.SQL.format(p=p, where=""), ws); table = {"columns": cols, "rows": rows}
    level = None
    if exposure_facts.enabled():
        e = exposure_facts.gather(assess_facts.CASE)
        if e.get("assessed"): level = exposure_rules.rate(e["answers"])["level"]
    res = priority_rules.prioritise(table, level); ids = {r["system"]: r["system_id"] for r in (dict(zip(cols, x)) for x in rows)}
    byname = {r["system"]: r for r in (dict(zip(cols, x)) for x in rows)}
    prio = [dict({"our_rank": i + 1, "system_id": ids[r["system"]], "system": r["system"], "our_rating": r["rating"], "our_reason": r["reason"]}, **{c: byname[r["system"]].get(c) for c in FACT_COLS}) for i, r in enumerate(res["rows"])]
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "feed-raised.csv"), FEED_COLS, cands); write_csv(os.path.join(out, "feed-not-raised.csv"), UNRAISED_COLS, picked); write_csv(os.path.join(out, "priorities.csv"), PRIO_COLS, prio)
    man = {"created": datetime.date.today().isoformat(), "as_of": priority_rules.AS_OF, "seed": seed, "sample_size": len(picked), "raised_population": len(cands), "unraised_population": len(pool), "systems": len(prio), "exposure_level_applied": level}
    with open(os.path.join(out, "manifest.json"), "w") as f: json.dump(man, f, indent=1)
    return man


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--out", required=True); e.add_argument("--sample", type=int, default=40); e.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("score"); s.add_argument("--dir", required=True)
    b = sub.add_parser("bundle"); b.add_argument("--dir", required=True); b.add_argument("--to", required=True); b.add_argument("--seed", type=int, default=1)
    m = sub.add_parser("merge"); m.add_argument("--dir", required=True); m.add_argument("--returned", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "export": print(json.dumps(export(a.out, a.sample, a.seed), indent=1))
    elif a.cmd == "bundle": print(json.dumps(bundle(a.dir, a.to, a.seed), indent=1))
    elif a.cmd == "merge":
        probs = merge(a.dir, a.returned); print("\n".join(probs) if probs else "merged: every id came back"); print("now: pilot.py score --dir %s" % a.dir)
    else: print(report(score(a.dir)))


if __name__ == "__main__": main(sys.argv[1:])
