"""judge.py <reference_rows.json> <run.json> <out.json>: grades each answer against the rows of the reference SQL (model judge; set JUDGE_MODEL, default claude-sonnet-5-5; claude-haiku-5-5 agreed with it on 56 of 60 answers)."""
import json, sys, anthropic
client = anthropic.Anthropic()
SYS = ("You grade a database answer against a reference. The reference rows come from the approved, checked SQL for the question. "
       "Reply with one JSON object only: {\"verdict\":\"correct\"|\"wrong\",\"reason\":\"<one short sentence>\"}. "
       "Call it correct if the candidate reports the same entities and the same figures as the reference: ignore row order, column order, extra columns, "
       "ids shown with or instead of names (when the rows clearly identify the same entities), column naming, and rounding or currency formatting differences. "
       "Call it wrong if it omits or adds entities, gives different figures, answers a different question, returns far more rows than the reference, returns nothing, or errors.")
def show(cols, rows, n=40):
    return json.dumps({"columns": cols, "rows": rows[:n], "total_rows": len(rows)}, default=str)[:6000]
def judge(question, ref, cand):
    msg = (f"Question: {question}\n\nREFERENCE: {show(ref.get('columns'), ref.get('rows') or [])}\n\n"
           f"CANDIDATE: {show(cand.get('columns'), cand.get('rows') or [])}\nCandidate error: {cand.get('error') or 'none'}")
    r = client.messages.create(model=__import__("os").environ.get("JUDGE_MODEL","claude-sonnet-5-5"), max_tokens=3000, system=SYS,
                               output_config={"effort": "low"}, messages=[{"role": "user", "content": msg}])
    t = "".join(b.text for b in r.content if b.type == "text")
    try: return json.loads(t[t.index("{"):t.rindex("}")+1])
    except Exception: return {"verdict": "wrong", "reason": "judge parse: " + t[:80]}
if __name__ == "__main__":
    ref = {r["question"]: r for r in json.load(open(sys.argv[1]))}
    cands = json.load(open(sys.argv[2])); out = []
    for c in cands:
        b = ref.get(c.get("sameAs") or c["question"])
        v = judge(c["question"], b, c) if b else {"verdict": "wrong", "reason": "no reference"}
        out.append({"question": c["question"], **v})
    json.dump(out, open(sys.argv[3], "w"), indent=1)
    print(sys.argv[2], sum(1 for o in out if o["verdict"] == "correct"), "of", len(out))
