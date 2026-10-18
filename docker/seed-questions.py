"""Approves a few trusted questions for the supply-chain demo so the Ask app's first screen offers questions this data can answer.

Run once by the `seed-questions` service in docker-compose.yml after OmniGate is up. Safe to re-run (skips questions already in the
bank) and best effort: it always exits 0, and if anything goes wrong the Ask app simply shows its generic example questions.

The quick-start admin console is open (no login). If you turn admin authentication on, set ADMIN_USER and ADMIN_PASSWORD (or
ADMIN_TOKEN) in your .env so this can still sign in.
"""
import http.cookiejar, json, os, sys, time, urllib.error, urllib.parse, urllib.request

base = os.environ.get("OMNIGATE_URL", "http://omnigate:8080")
token = os.environ.get("ADMIN_TOKEN", "")
user, password = os.environ.get("ADMIN_USER", ""), os.environ.get("ADMIN_PASSWORD", "")


def log(m):
    print("seed-questions:", m, flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect)


def call(path, body=None, form=None):
    data, headers = None, {}
    if body is not None:
        data, headers = json.dumps(body).encode(), {"Content-Type": "application/json"}
    if form is not None:
        data, headers = urllib.parse.urlencode(form).encode(), {"Content-Type": "application/x-www-form-urlencoded"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with op.open(urllib.request.Request(base + path, data=data, headers=headers), timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ""


try:
    for _ in range(120):
        try:
            if call("/api/deployment-readiness")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(5)
    if not token and user and password:
        code, _ = call("/admin/login", form={"username": user, "password": password})
        if code not in (200, 302, 303):
            log("admin login refused (%s); leaving the question bank alone" % code)
            sys.exit(0)
    code, text = call("/api/question-bank")
    if code != 200:
        log("cannot read the question bank (%s); leaving it alone. If you set admin logins, put ADMIN_USER and ADMIN_PASSWORD in .env" % code)
        sys.exit(0)
    have = {e["question"] for e in json.loads(text).get("entries", [])}
    done = 0
    for q in json.load(open("/seed/demo-questions.json")):
        if q["question"] in have:
            continue
        code, text = call("/api/question-bank", body=q)
        entry = json.loads(text)["entry"]
        code, _ = call("/api/question-bank/status", body={"id": entry["id"], "status": "approved"})
        done += code == 200
    log("approved %d new trusted question(s)" % done)
except Exception as e:
    log("skipped: %r" % (e,))
sys.exit(0)
