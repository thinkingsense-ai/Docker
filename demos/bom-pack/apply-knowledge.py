"""Gives the BOM pack its business knowledge: a description for every table (including the rules a question depends on, such as
what 'approved' means and when a certificate is valid) and a few named measures. Run once by the `seed-knowledge` service after the app is
up; safe to re-run, best effort (it always exits 0)."""
import json, os, sys, time, urllib.error, urllib.request

base = os.environ.get("OMNIGATE_URL", "http://omnigate:8080")
know = json.load(open("/seed/bom-knowledge.json"))


def call(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", "X-Requested-With": "seed-knowledge"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


try:
    for _ in range(120):
        try:
            if call("/api/deployment-readiness")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(5)
    # the schema is read in the background after start; wait until the tables are there
    have = set()
    for _ in range(60):
        code, text = call("/api/ontology.json")
        if code == 200:
            have = {e["physicalId"] for e in json.loads(text).get("entities", [])}
            if set(know["entities"]) <= have:
                break
        time.sleep(5)
    done = sum(call("/api/ontology/entity-description", {"physicalId": k, "description": v})[0] == 200 for k, v in know["entities"].items() if k in have)
    print("seed-knowledge: described %d of %d tables" % (done, len(know["entities"])), flush=True)
    code, text = call("/api/config/metrics", {"yaml": know["metrics"]}, "PUT")
    print("seed-knowledge: measures %s" % ("saved" if code == 200 else "not saved (%s %s)" % (code, text)), flush=True)
    if know.get("demoUserCanSeeSql"):
        call("/api/app-user-access", {"username": "demo", "canSeeSql": True, "canSeeSources": True, "canUploadFiles": False})
except Exception as e:
    print("seed-knowledge: skipped: %r" % (e,), flush=True)
sys.exit(0)
