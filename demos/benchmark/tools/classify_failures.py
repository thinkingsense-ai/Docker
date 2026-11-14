"""classify_failures.py <benchmark.json> <dir> <tag>: for questions never judged right in any run of a variant, asks a model to name the cause
(missing rule, wrong table, no SQL, ...) from the reference SQL, the rules, the final SQL and the judge's note. Needs ANTHROPIC_API_KEY."""
import json, sys, glob, os, collections, anthropic
bench, d, tag = sys.argv[1:4]; client = anthropic.Anthropic()
TAX = ["wrong_table_or_join", "table_not_offered_to_model", "missing_business_rule", "wrong_measure_or_column", "date_window_or_relative_time",
       "aggregation_grain_or_duplicates", "output_shape_or_topn", "cross_source_join", "no_sql_or_refusal", "other"]
SYS = ("You diagnose why a model-written SQL query gave a wrong answer to a business question, comparing it with the approved reference SQL. Reply with one JSON object only: "
       "{\"cause\":\"<one of " + ",".join(TAX) + ">\",\"note\":\"<one short sentence naming the specific mistake>\"}.")
ref = {e["question"]: e for e in json.load(open(bench))}
runs = [(json.load(open(f)), {x["question"]: x for x in json.load(open(f.replace(tag + "_r", "j_" + tag + "_r")))}) for f in sorted(glob.glob(os.path.join(d, tag + "_r[0-9].json")))]
out = []
for q in ref:
    if any(J[q]["verdict"] == "correct" for _, J in runs): continue
    R, J = runs[0]; r = next(x for x in R if x["question"] == q); sql = (r.get("sqls") or [""])[-1]
    msg = (f"Question asked: {r['asked']}\n\nREFERENCE SQL:\n{ref[q]['referenceSql']}\n\nRULES:\n- " + "\n- ".join(ref[q]["rules"]) +
           f"\n\nCANDIDATE SQL:\n{sql[:2500] or '(none produced)'}\nCandidate error: {r.get('error') or 'none'}\nJudge note: {J[q].get('reason')}")
    resp = client.messages.create(model="claude-sonnet-5-5", max_tokens=1500, system=SYS, output_config={"effort": "low"}, messages=[{"role": "user", "content": msg}])
    t = "".join(b.text for b in resp.content if b.type == "text")
    try: v = json.loads(t[t.index("{"):t.rindex("}") + 1])
    except Exception: v = {"cause": "other", "note": "parse"}
    out.append({"question": q, **v}); print(f"{v['cause']:32} {q[:60]} | {v['note'][:140]}")
print(dict(collections.Counter(o["cause"] for o in out)))
