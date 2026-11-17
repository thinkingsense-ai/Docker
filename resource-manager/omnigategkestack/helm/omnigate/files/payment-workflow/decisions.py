"""The decision record: an append-only, hash-chained JSON-lines file (control 10). Each line holds the inputs, the rules result, the recommendation, who approved what, the action and its outcome.
The chain (each line carries the hash of the one before) makes an edit or a deleted line detectable with `python decisions.py verify`. A real deployment exports this to the customer's own log store."""
import hashlib, json, os, sys
PATH = os.environ.get("DECISIONS_FILE", "/data/decisions.jsonl")
def _h(prev, body): return hashlib.sha256((prev + json.dumps(body, sort_keys=True, default=str)).encode()).hexdigest()

def read():
    if not os.path.exists(PATH): return []
    return [json.loads(l) for l in open(PATH) if l.strip()]

def append(body):
    """Idempotent on body['decision_id']: a retried activity does not write the same decision twice."""
    rows = read()
    for r in rows:
        if r["body"].get("decision_id") == body.get("decision_id"): return r
    prev = rows[-1]["hash"] if rows else "genesis"
    rec = {"prev": prev, "body": body, "hash": _h(prev, body)}
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "a") as f: f.write(json.dumps(rec, default=str) + "\n")
    return rec

def verify():
    prev = "genesis"
    for n, r in enumerate(read(), 1):
        if r["prev"] != prev or r["hash"] != _h(prev, r["body"]): return "broken at record %d" % n
        prev = r["hash"]
    return "ok"

if __name__ == "__main__" and sys.argv[1:] == ["verify"]: print(verify())
