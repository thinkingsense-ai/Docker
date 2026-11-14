"""Benchmark runner: asks each question in a fresh session and records, per question, the final SQL, rows, every SQL step the app took,
and the range of calls in the llmproxy log that belong to it (so prompts can be analysed afterwards).
  bench_run.py <questions.json> <out.json> <calls.jsonl> [base] [user] [password]      (password may come from BENCH_PASSWORD)"""
import json, os, sys, time, ssl, http.cookiejar, urllib.request
qf, out, calls = sys.argv[1:4]
base = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:8080"
user = sys.argv[5] if len(sys.argv) > 5 else "demo"
pw = sys.argv[6] if len(sys.argv) > 6 else os.environ.get("BENCH_PASSWORD", "demo")
ctx = ssl._create_unverified_context()
def nlines():
    try: return sum(1 for _ in open(calls))
    except FileNotFoundError: return 0
def session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))
    def post(path, body, timeout=400):
        r = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Requested-With": "t"})
        return op.open(r, timeout=timeout)
    post("/app/login", {"username": user, "password": pw}).read()
    return post
qs = json.load(open(qf)); qs = qs if isinstance(qs, list) else qs["questions"]
res = []
for i, q in enumerate(qs):
    text = q.get("ask") or q["question"]
    post = session(); ev = []; t0 = time.time(); n0 = nlines()
    try:
        for line in post("/api/ask", {"question": text, "conversationId": None}):
            line = line.decode().strip()
            if line.startswith("data:"):
                try: ev.append(json.loads(line[5:]))
                except Exception: pass
    except Exception as e:
        ev.append({"step": "error", "error": str(e)[:300]})
    n1 = nlines()
    sqls = [e.get("sql") for e in ev if e.get("sql")]  # any event carrying SQL (the answer's SQL is not always in a "sql" step)
    steps = [e.get("step") for e in ev]
    done = [e for e in ev if e.get("step") == "done"]; d = done[-1] if done else {}
    err = [e.get("error") for e in ev if e.get("step") == "error"]
    res.append({"question": q["question"], "asked": text, "secs": round(time.time() - t0, 1), "calls": [n0, n1], "sqls": sqls, "steps": steps,
                "source": next((e.get("source") for e in ev if e.get("step") == "sql" and e.get("source")), None),
                "columns": d.get("columns"), "rows": d.get("rows"), "nrows": d.get("rowCount", len(d.get("rows") or [])), "answer": d.get("answer"),
                "error": err[0] if err else None, "sameAs": q.get("sameAs")})
    json.dump(res, open(out, "w"))
print("done", len(res))
