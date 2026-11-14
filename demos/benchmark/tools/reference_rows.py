"""Runs each benchmark question's reference SQL through the app's admin query API and writes the rows, for the judge.
  reference_rows.py <benchmark.json> <out.json> [base]      (local stacks run with OMNIGATE_INSECURE=true, so the admin API is open)"""
import json, sys, urllib.request
bf, out = sys.argv[1:3]; base = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8080"
res = []
for e in json.load(open(bf)):
    r = urllib.request.Request(base + "/api/query", data=json.dumps({"sql": e["referenceSql"]}).encode(), headers={"Content-Type": "application/json", "X-Requested-With": "t"})
    try: j = json.load(urllib.request.urlopen(r, timeout=120))
    except Exception as ex: j = {"success": False, "error": str(ex)[:200]}
    res.append({"question": e["question"], "columns": j.get("columns"), "rows": j.get("rows") or [], "error": None if j.get("success") else j.get("error")})
json.dump(res, open(out, "w")); print("reference rows:", sum(1 for x in res if not x["error"]), "of", len(res), "ran")
