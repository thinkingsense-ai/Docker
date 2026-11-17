#!/usr/bin/env python3
"""Black-box test of the Server's workflow API (app v0.10.19+, docs/workflows-api.md) against a running stack with the local engine and the payment-exception manifest.
Users alice (starts runs), bob and carol (approve), dave (no grants) and treasury-agent (a non-human identity) must exist with the password `pw`.
  BASE=http://localhost:8088 CONTAINER=wf1019-omnigate-1 python3 server-workflow-api.py
It also recomputes the hash chain of the decision record from the file itself (the scheme in WorkflowDecisionLog), instead of trusting the Server's own verifier."""
import hashlib, http.cookiejar, json, os, subprocess, sys, time, urllib.error, urllib.request
BASE = os.environ.get("BASE", "http://localhost:8088"); CONTAINER = os.environ.get("CONTAINER", "wf1019-omnigate-1"); DEC = os.environ.get("DECISIONS", "/var/lib/omnigate/data/wf-decisions.jsonl")
fail = 0
def check(name, cond, detail=""):
    global fail
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  -> " + str(detail)[:230]) if (detail and not cond) or detail == "show" else "")); fail += 0 if cond else 1
class U:
    def __init__(self, name):
        self.name = name; self.jar = http.cookiejar.CookieJar(); self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.call("POST", "/app/login", {"username": name, "password": "pw"})
    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data, {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, method=method)
        try:
            with self.op.open(req, timeout=30) as r: return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raw = e.read(); 
            try: return e.code, json.loads(raw or b"{}")
            except ValueError: return e.code, {"raw": raw[:80].decode("utf-8", "replace")}
def admin(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST"); return json.load(urllib.request.urlopen(req, timeout=30))
def wait_stage(u, rid, want, secs=30):
    for _ in range(secs * 2):
        s, b = u.call("GET", "/app/workflows/runs/" + rid)
        if s == 200 and b["run"]["stage"] in want: return b["run"]
        time.sleep(0.5)
    return b.get("run") if s == 200 else None

print("grants"); 
for n, g in {"alice": dict(canStartWorkflows=True), "bob": dict(canApprove=True), "carol": dict(canApprove=True), "treasury-agent": dict(canApprove=True), "dave": {}}.items():
    admin("/api/app-user-access/update", dict(username=n, canSeeSql=True, canSeeSources=True, canUploadFiles=False, canStartWorkflows=g.get("canStartWorkflows", False), canApprove=g.get("canApprove", False)))
alice, bob, carol, dave, agent = U("alice"), U("bob"), U("carol"), U("dave"), U("treasury-agent")
anon = U.__new__(U); anon.jar = http.cookiejar.CookieJar(); anon.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(anon.jar))

print("access")
s, b = anon.call("GET", "/app/workflows/definitions"); check("no session -> 401", s == 401, (s, b))
s, b = dave.call("GET", "/app/workflows/definitions"); check("a user without grants -> 403 missing_grant", s == 403 and b.get("code") == "missing_grant", (s, b))
s, b = alice.call("GET", "/app/workflows/definitions"); d = (b.get("definitions") or [{}])[0]; check("alice sees the payment-exception definition (key payment_id, 2 approvals)", s == 200 and d.get("id") == "payment-exception" and d.get("keyField") == "payment_id" and d.get("requiredApprovals") == 2, (s, b))
s, b = alice.call("GET", "/app/whoami"); check("whoami reports canStartWorkflows for alice", b.get("canStartWorkflows") is True and b.get("canApprove") is False, {k: b.get(k) for k in ("canStartWorkflows", "canApprove")})
s, b = bob.call("POST", "/app/workflows/start", {"definition": "payment-exception", "key": "35"}); check("an approver without canStartWorkflows cannot start -> 403 missing_grant", s == 403 and b.get("grant") == "canStartWorkflows", (s, b))

print("start and progress")
s, b = alice.call("POST", "/app/workflows/start", {"definition": "payment-exception", "key": "35"}); run = b.get("run", {}); rid = run.get("id")
check("alice starts a run for payment 35 -> 201", s == 201 and b.get("created") is True and run.get("stage") in ("facts", "rules", "recommendation", "awaiting_approval"), (s, b))
s2, b2 = alice.call("POST", "/app/workflows/start", {"definition": "payment-exception", "key": "35"}); check("a second start is idempotent (same run id, 200)", s2 == 200 and b2["run"]["id"] == rid, (s2, b2))
run = wait_stage(alice, rid, ["awaiting_approval"]); check("the run reaches awaiting_approval", run and run["stage"] == "awaiting_approval", run)
H = run["payloadHash"] if run else ""
check("recommendation, rules, evidence and a payload hash are present (recommendation source is a stub)", bool(run and run["recommendation"] and run["rules"] and H and run["recommendation"].get("source") == "stub"), run and run.get("recommendation"))
check("the card tells alice she cannot approve (she started it)", run and run["you"]["canApprove"] is False and run["you"]["reason"] == "missing_grant", run and run.get("you"))

print("approval rules (the Server must refuse before signalling the engine)")
s, b = alice.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); check("a user without canApprove -> 403 missing_grant", s == 403 and b.get("code") == "missing_grant", (s, b))
admin("/api/app-user-access/update", dict(username="alice", canSeeSql=True, canSeeSources=True, canUploadFiles=False, canStartWorkflows=True, canApprove=True))
s, b = alice.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); check("the initiator, even with canApprove -> 403 initiator_cannot_approve", s == 403 and b.get("code") == "initiator_cannot_approve", (s, b))
s, b = agent.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); check("a non-human identity (treasury-agent) -> 403 non_human_identity", s == 403 and b.get("code") == "non_human_identity", (s, b))
s, b = bob.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": "deadbeef"}); check("a stale or wrong payload hash -> 409 payload_hash_mismatch", s == 409 and b.get("code") == "payload_hash_mismatch", (s, b))
s, b = bob.call("GET", "/app/workflows/queue"); check("bob's queue lists the run waiting for him", s == 200 and b.get("count") == 1, (s, b))
s, b = bob.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); r = b.get("run", {}); check("bob approves: 1 of 2, still awaiting", s == 200 and len(r.get("approvals", [])) == 1 and r.get("stage") == "awaiting_approval", (s, b))
s, b = bob.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); check("bob a second time -> 403 already_approved", s == 403 and b.get("code") == "already_approved", (s, b))
s, b = bob.call("GET", "/app/workflows/queue"); check("the run leaves bob's queue once he has approved", s == 200 and b.get("count") == 0, (s, b))
s, b = carol.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); r = b.get("run", {}); check("carol approves: the second approval completes it", s == 200 and len(r.get("approvals", [])) == 2, (s, b))
r = wait_stage(alice, rid, ["written_back"]); wb = (r or {}).get("writeBack") or {}
check("write-back is a dry run naming the call (nothing is sent)", wb.get("mode") == "dry_run" and wb.get("call") == "POST /payments/35/hold", wb)
s, b = carol.call("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": H}); check("an approval after completion -> 409 not_awaiting_approval (or already_approved)", s in (409, 403), (s, b))

print("reject")
s, b = alice.call("POST", "/app/workflows/start", {"definition": "payment-exception", "key": "31"}); rid2 = b["run"]["id"]; r2 = wait_stage(alice, rid2, ["awaiting_approval"])
s, b = carol.call("POST", "/app/workflows/runs/%s/reject" % rid2, {"reason": "  "}); check("a reject without a reason -> 400", s == 400, (s, b))
s, b = carol.call("POST", "/app/workflows/runs/%s/reject" % rid2, {"reason": "invoice unverified"}); check("carol rejects with a reason -> rejected", s == 200 and b["run"]["stage"] == "rejected" and b["run"]["rejection"]["user"] == "carol", (s, b))

print("unknown ids")
s, b = alice.call("GET", "/app/workflows/runs/nope"); check("an unknown run -> 404 unknown_run", s == 404 and b.get("code") == "unknown_run", (s, b))
s, b = alice.call("POST", "/app/workflows/start", {"definition": "nope", "key": "1"}); check("an unknown definition -> 404 unknown_definition", s == 404 and b.get("code") == "unknown_definition", (s, b))

print("decision record (chain recomputed here from the file)")
raw = subprocess.run(["docker", "exec", CONTAINER, "cat", DEC], capture_output=True, text=True).stdout
ents = [json.loads(l) for l in raw.splitlines() if l.strip()]
def h(prev, ts, run, typ, actor, det):
    c = "".join((x or "") + "\x01" for x in (prev, ts, run, typ, actor)) + "".join("%s=%s\x02" % (k, det[k]) for k in sorted(det))
    return hashlib.sha256(c.encode()).hexdigest()
prev, ok = "", True
for i, e in enumerate(ents, 1):
    if e["seq"] != i or e["prevHash"] != prev or h(e["prevHash"], e["ts"], e["runId"], e["type"], e["actor"], e["details"]) != e["hash"]: ok = False; break
    prev = e["hash"]
types = [e["type"] for e in ents if e["runId"] == rid]
check("the chain verifies (%d entries)" % len(ents), ok and len(ents) > 8)
print("     run 1 events:", types)
refusals = [e for e in ents if "refus" in e["type"].lower() or "refus" in json.dumps(e["details"]).lower()]
check("the refusals above were written to the record", len(refusals) >= 4, "found %d" % len(refusals))
if ents:
    t = json.loads(json.dumps(ents[-1])); t["details"] = dict(t["details"], tampered="x")
    check("a tampered entry is detected by the same check", h(t["prevHash"], t["ts"], t["runId"], t["type"], t["actor"], t["details"]) != t["hash"])
print("\n" + ("ALL PASSED" if not fail else "%d FAILED" % fail)); sys.exit(1 if fail else 0)
