"""Builds benchmark-<pack>.json from a pack's approved questions: adds tags (derived from the reference SQL), the business rules the
answer depends on (drafted by a model from the reference SQL, to be reviewed by a person), and clarified wording where the original
question is ambiguous about what it asks for."""
import json, re, sys, anthropic
client = anthropic.Anthropic()
import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..") + "/"
ASK = {  # original question (prefix) -> clarified wording; the reference SQL is unchanged
 "Which material is used by the most parts?": "Which five materials are used by the most parts, and how many parts does each have?",
 "How much headroom does each covenant have": "How much headroom does each covenant have, as a percentage of its threshold, tightest first?",
 "How accurate were the weekly cash forecasts": "How accurate were the weekly cash forecasts for each entity over the last 12 weeks? Give each entity's average absolute error as a percentage of the forecast.",
 "How many open accounts are fed by": "How many accounts that are not closed are fed by each method (API, file, portal)?",
 "Which bank transactions in the last 14 days": "For each account, how many bank transactions in the last 14 days have no matching ledger entry, and what is their gross amount?",
}
DEFECTS = {
 "How many open accounts are fed by": "Pack wording says 'open' but the reference counts every account that is not Closed (Frozen included); the knowledge file says only Open accounts count as usable cash.",
 "How accurate were the weekly cash forecasts": "Wording says 'last 12 weeks' but the reference averages every forecast row; correct only if the data holds exactly 12 weeks.",
 "Which material is used by the most parts?": "Reference returns the top 5 materials, not the single most-used one.",
}
SYS = ("You read an approved SQL query for a business question and list the business rules and definitions the answer depends on, in plain words, "
       "independent of SQL syntax: how a quantity is defined (for example 'cash = latest balance per open account, converted to USD at the account currency's rate'), "
       "which statuses or states are included, thresholds, units, grouping level, relative time windows. One short string per rule, 1 to 6 rules, no restating of the question. "
       "Reply with only a JSON array of strings.")
def tags(sql, pack):
    s = sql.upper(); t = []
    tabs = set(re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_]\w*\.[A-Za-z_]\w*)", sql, re.I))
    n = len(tabs); t.append("tables:%d" % n)
    if n >= 4: t.append("many-tables")
    if "JOIN" in s: t.append("join")
    if any(x in s for x in ("GROUP BY", "COUNT(", "SUM(", "AVG(")): t.append("aggregate")
    if "CURRENT_DATE" in s or "CURRENT_TIMESTAMP" in s: t.append("relative-date")
    if "WITH " in s or s.count("SELECT") > 1: t.append("subquery-or-cte")
    if "DISTINCT ON" in s: t.append("distinct-on")
    if "ERP." in s and "TREASURY." in s: t.append("cross-source")
    if "CASE " in s: t.append("case")
    return t
for pack in sys.argv[1:]:
    qs = json.load(open(f"{D}{pack}-pack/demo-questions-{pack}.json")); qs = qs if isinstance(qs, list) else qs["questions"]
    out = []
    for i, q in enumerate(qs, 1):
        r = client.messages.create(model="claude-sonnet-5-5", max_tokens=1500, system=SYS, output_config={"effort": "low"},
            messages=[{"role": "user", "content": f"Question: {q['question']}\n\nApproved SQL:\n{q['referenceSql']}"}])
        txt = "".join(b.text for b in r.content if b.type == "text")
        try: rules = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
        except Exception: rules = []
        ask = next((v for k, v in ASK.items() if q["question"].startswith(k)), None)
        defect = next((v for k, v in DEFECTS.items() if q["question"].startswith(k)), None)
        e = {"id": f"{pack}-{i:02d}", "pack": pack, "question": q["question"], "referenceSql": q["referenceSql"], "tags": tags(q["referenceSql"], pack), "rules": rules}
        if ask: e["ask"] = ask
        if defect: e["referenceNote"] = defect
        out.append(e)
    json.dump(out, open(D + f"benchmark/benchmark-{pack}.json", "w"), indent=1)
    print(pack, len(out), "questions;", sum(1 for e in out if "ask" in e), "reworded;", sum(len(e["rules"]) for e in out), "rules")
