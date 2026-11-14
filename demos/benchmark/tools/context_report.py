"""context_report.py <benchmark.json> <knowledge.json> <run.json> <calls.jsonl>
Of the prompts the app sent the model for each question: were all tables the reference SQL needs offered, and did any table description appear?"""
import json, re, sys
bench, know, resf, callsf = sys.argv[1:5]
phr = [v[:45] for v in json.load(open(know))["entities"].values() if len(v) > 45]
ref = {e["question"]: e["referenceSql"] for e in json.load(open(bench))}
res = json.load(open(resf)); calls = [json.loads(l) for l in open(callsf)]
def text(c):
    s = c["request"].get("system"); s = s if isinstance(s, str) else json.dumps(s)
    m = c["request"]["messages"][-1]["content"]; m = m if isinstance(m, str) else json.dumps(m)
    return s + "\n" + m
need = lambda sql: set(re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_]\w*\.[A-Za-z_]\w*)", sql, re.I))
full = desc = 0; shown_n = need_n = 0; missing = []
for r in res:
    n0, n1 = r["calls"]; cs = calls[n0:n1]
    shown = set()
    for c in cs: shown |= set(re.findall(r"CREATE TABLE ([\w.]+)", text(c)))
    if any(p in "\n".join(text(c) for c in cs) for p in phr): desc += 1
    req = need(ref[r["question"]]); shown_n += len(shown); need_n += len(req)
    if req <= shown: full += 1
    else: missing.append((r["question"][:70], sorted(req - shown)))
n = len(res)
print(f"all tables the reference needs were offered for {full} of {n} questions; a table description appeared for {desc} of {n}")
print(f"tables offered per question {shown_n/n:.1f}, needed {need_n/n:.1f}")
for q, m in missing: print("  missing", m, "|", q)
