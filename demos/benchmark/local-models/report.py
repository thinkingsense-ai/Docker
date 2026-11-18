"""Reads what run_local.sh / run_variant.sh left in a results directory.

  python3 report.py summary   DIR TAG                    # TAG like treasury_base_qwen3-4b-q4km-arm-cpu-16
  python3 report.py calibrate DIR LOCAL_TAG FRONTIER_TAG [--tolerance 1] [--per-run]

summary:   score per run, mean, answer time (median, p90), tokens per question, and what the meta file says about hardware and settings.
calibrate: for every escalation threshold t, how many questions the local model would keep (its recorded confidence >= t), how accurate those
           kept answers are, and the blended score if the rest went to the frontier model (that question's own measured frontier accuracy).
           It then names the LOWEST t whose blended score is within --tolerance questions of the frontier model alone. Needs a 'confidence'
           per question in the local runs (bench_run.py records it); without one it says so and stops.
Standard library only. The functions below are pure and tested."""
import glob, json, os, statistics, sys


def load_tag(directory, tag):
    """[(answers, judged)] per run, matched by run number. answers: list of dicts from bench_run.py; judged: list from judge.py."""
    runs = []
    for f in sorted(glob.glob(os.path.join(directory, f"{tag}_r*.json"))):
        n = f[len(os.path.join(directory, tag)) + 2:-5]
        jf = os.path.join(directory, f"j_{tag}_r{n}.json")
        if os.path.exists(jf): runs.append((json.load(open(f)), json.load(open(jf))))
    return runs


def usage(call):
    """(prompt_tokens, completion_tokens) from either an OpenAI-style or an Anthropic-style reply."""
    u = (call.get("response") or {}).get("usage") or {}
    return (u.get("prompt_tokens", u.get("input_tokens", 0)) or 0, u.get("completion_tokens", u.get("output_tokens", 0)) or 0)


def tokens_per_question(answers, calls):
    out = []
    for a in answers:
        lo, hi = a.get("calls") or [0, 0]; p = c = 0
        for call in calls[lo:hi]: x, y = usage(call); p += x; c += y
        out.append((p, c))
    return out


def percentile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def summarize(runs, calls=None):
    scores = [sum(1 for j in judged if j["verdict"] == "correct") for _, judged in runs]
    secs = [a["secs"] for answers, _ in runs for a in answers if a.get("secs") is not None]
    out = {"runs": len(runs), "questions": len(runs[0][1]) if runs else 0, "scores": scores, "mean": round(sum(scores) / len(scores), 2) if scores else None,
           "secs_median": round(statistics.median(secs), 1) if secs else None, "secs_p90": percentile(secs, 0.9)}
    if calls is not None and runs:
        tq = [t for answers, _ in runs for t in tokens_per_question(answers, calls)]
        out["prompt_tokens_median"] = statistics.median(p for p, _ in tq); out["completion_tokens_median"] = statistics.median(c for _, c in tq)
    return out


def rows_from(runs):
    """One row per (run, question): {question, conf, correct}. conf is None when the run did not record one."""
    rows = []
    for answers, judged in runs:
        by_q = {j["question"]: j["verdict"] == "correct" for j in judged}
        for a in answers:
            c = a.get("confidence")
            try: c = float(c) if c is not None else None
            except (TypeError, ValueError): c = None
            rows.append({"question": a["question"], "conf": c, "correct": by_q.get(a["question"], False)})
    return rows


def frontier_accuracy(frontier_runs):
    """question -> fraction of the frontier model's runs that got it right."""
    acc = {}
    for _, judged in frontier_runs:
        for j in judged: acc.setdefault(j["question"], []).append(j["verdict"] == "correct")
    return {q: sum(v) / len(v) for q, v in acc.items()}


def calibrate(local_rows, frontier_acc, n_runs=1, thresholds=range(0, 101, 5), tolerance=1.0):
    """Table of {t, kept_share, kept_accuracy, blended} per threshold, per-run questions averaged; and the lowest t that is good enough.
    blended is in QUESTIONS per run (so comparable with 'x of 24'); a row with no recorded confidence is treated as below every threshold above 0."""
    nq = len(frontier_acc)
    frontier_total = sum(frontier_acc.values()); table = []
    for t in thresholds:
        flags = [(r["conf"] if r["conf"] is not None else -1) >= t for r in local_rows]
        kept = [r for r, f in zip(local_rows, flags) if f]; rest = [r for r, f in zip(local_rows, flags) if not f]
        got = sum(1 for r in kept if r["correct"]) + sum(frontier_acc.get(r["question"], 0.0) for r in rest)
        table.append({"t": t, "kept_share": round(len(kept) / len(local_rows), 3) if local_rows else 0,
                      "kept_accuracy": round(sum(1 for r in kept if r["correct"]) / len(kept), 3) if kept else None,
                      "blended": round(got / n_runs, 2)})
    ok = [x for x in table if x["blended"] >= frontier_total - tolerance]
    return {"frontier_alone": round(frontier_total, 2), "questions": nq, "table": table, "lowest_good_t": ok[0]["t"] if ok else None,
            "answer": ok[0] if ok else None}


def main(argv):
    if len(argv) < 3 or argv[0] not in ("summary", "calibrate"): print(__doc__); return 1
    d = argv[1]
    if argv[0] == "summary":
        tag = argv[2]; runs = load_tag(d, tag)
        if not runs: print("no judged runs for", tag); return 1
        cf = os.path.join(d, f"calls_{tag}.jsonl")
        calls = [json.loads(x) for x in open(cf)] if os.path.exists(cf) else None
        print(json.dumps(summarize(runs, calls), indent=1))
        mf = os.path.join(d, "meta_" + tag.split("_base_")[-1] + ".json")
        if os.path.exists(mf):
            m = json.load(open(mf)); print("meta:", {k: m.get(k) for k in ("model", "shape", "oci_shape", "engine", "image_id", "healthy_after_s", "prompt_adapter")})
        return 0
    if len(argv) < 4: print(__doc__); return 1
    tol = float(argv[argv.index("--tolerance") + 1]) if "--tolerance" in argv else 1.0
    local, front = load_tag(d, argv[2]), load_tag(d, argv[3])
    rows = rows_from(local)
    if not any(r["conf"] is not None for r in rows):
        print("The local runs recorded no confidence (bench_run.py could not find a 'confidence' field in the answer events). Check the Server's event"
              " field name on a live run, then re-run; the summary command still works."); return 1
    res = calibrate(rows, frontier_accuracy(front), n_runs=len(local), tolerance=tol)
    print(f"frontier model alone: {res['frontier_alone']} of {res['questions']}")
    for x in res["table"]:
        print(f"  t={x['t']:3d}  kept locally {x['kept_share']*100:5.1f}%  kept accuracy {('%.1f%%' % (x['kept_accuracy']*100)) if x['kept_accuracy'] is not None else '  n/a'}  blended {x['blended']:5.2f}")
    print("lowest threshold within tolerance:", res["lowest_good_t"] if res["lowest_good_t"] is not None else "none: no threshold is good enough")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
