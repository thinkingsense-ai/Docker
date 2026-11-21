"""Replaces approved questions in the Server's question bank whose SQL has changed since they were first seeded. The seeder (docker/seed-questions.py) skips a question whose TEXT is already in the bank, so a
changed reference SQL never reaches an existing stack: the screen then fails with an error such as "column s.tier does not exist". This compares every bank entry with agency/local/.runtime/demo-questions.json,
deletes the entries whose SQL differs, and (with --seed) re-runs the seed container so the current SQL is approved. Needs the admin API token (agency/local/.runtime/tokens.env). Local sandbox only.
  python3 agency/local/refresh-questions.py [--seed]   (AGENCY_PROJECT names the compose project, default agency-local; ASK_URL defaults to http://localhost:8080)"""
import json, os, subprocess, sys, urllib.request


def stale(bank, wanted):
    """Bank entries whose question is in `wanted` but whose reference SQL is not the current one. wanted: {question text: reference SQL}."""
    return [e for e in bank if e.get("question") in wanted and (e.get("referenceSql") or "").strip() != (wanted[e["question"]] or "").strip()]


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__)); rt = os.path.join(here, ".runtime")
    token = os.environ.get("AGENCY_ADMIN_API_TOKEN")
    if not token and os.path.exists(os.path.join(rt, "tokens.env")):
        for line in open(os.path.join(rt, "tokens.env")):
            k, _, v = line.strip().partition("=")
            if k == "AGENCY_ADMIN_API_TOKEN": token = v
    if not token: print("refresh-questions: no admin API token (agency/local/.runtime/tokens.env); skipped"); return 0
    base = os.environ.get("ASK_URL", "http://localhost:8080").rstrip("/"); H = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    with open(os.path.join(rt, "demo-questions.json")) as f: wanted = {q["question"]: q["referenceSql"] for q in json.load(f)}
    bank = json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/question-bank", headers=H), timeout=60))["entries"]
    old = stale(bank, wanted)
    for e in old:
        urllib.request.urlopen(urllib.request.Request(base + "/api/question-bank/delete", data=json.dumps({"id": e["id"]}).encode(), headers=H), timeout=60).read()
        print("refresh-questions: replaced", e["question"][:80])
    if not old: print("refresh-questions: every approved question is current"); return 0
    if "--seed" in argv: subprocess.run(["docker", "start", "-a", "%s-seed-questions-1" % os.environ.get("AGENCY_PROJECT", "agency-local")], check=False)
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
