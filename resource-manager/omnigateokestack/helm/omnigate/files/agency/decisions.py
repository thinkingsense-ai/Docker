"""Reads the Server's hash-chained decision record (a shared file) and verifies the chain. The scheme was read from the v0.10.19 behaviour and is the same one
demos/payment-workflow/tests/server-workflow-api.py recomputes: sha256 over prevHash, ts, runId, type and actor (each followed by \\x01), then the sorted details as k=v\\x02."""
import hashlib, json

def entry_hash(e):
    d = e.get("details") or {}
    c = "".join((x or "") + "\x01" for x in (e.get("prevHash"), e.get("ts"), e.get("runId"), e.get("type"), e.get("actor"))) + "".join("%s=%s\x02" % (k, d[k]) for k in sorted(d))
    return hashlib.sha256(c.encode()).hexdigest()

def read(path):
    with open(path) as f: return [json.loads(l) for l in f if l.strip()]

def verify(entries):
    prev = ""
    for i, e in enumerate(entries, 1):
        if e.get("seq") != i or e.get("prevHash") != prev or entry_hash(e) != e.get("hash"): return False, i
        prev = e["hash"]
    return True, None
