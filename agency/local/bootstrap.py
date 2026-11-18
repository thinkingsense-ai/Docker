#!/usr/bin/env python3
"""Makes the local Agency stack ready to use (idempotent; run by up.sh): loads the pack Workspaces into the Server and sets what each demo login may do.
  python3 agency/local/bootstrap.py [--server http://localhost:8080]
Needs the admin login of the all-packs stack (admin / Admin-SI-1). Standard library only."""
import http.cookiejar, json, os, sys, time, urllib.error, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER = (sys.argv[sys.argv.index("--server") + 1] if "--server" in sys.argv else "http://localhost:8080").rstrip("/")
ADMIN = ("admin", os.environ.get("ADMIN_PASSWORD", "Admin-SI-1"))
# login: (see SQL, see sources, upload files, start workflows, approve workflows)
GRANTS = {"curator": (True, True, True, True, False), "alice": (False, False, True, True, False), "bob": (False, False, True, False, True), "carol": (False, False, True, False, True), "public": (False, False, False, False, False)}
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None, form=None):
    data = urllib.parse.urlencode(form).encode() if form else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(SERVER + path, data, {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json", "X-Requested-With": "bootstrap"}, method=method)
    try:
        with op.open(req, timeout=60) as r: raw = r.read(); return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read(); return e.code, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode("utf-8", "replace")[:200])


def main():
    for _ in range(120):
        try:
            if urllib.request.urlopen(SERVER + "/app/public-config", timeout=3).status == 200: break
        except (OSError, urllib.error.URLError): time.sleep(3)
    else: sys.exit("the Server did not answer at %s" % SERVER)
    s, _ = call("POST", "/admin/login", form={"username": ADMIN[0], "password": ADMIN[1]})
    if s not in (200, 302): sys.exit("admin login failed (HTTP %s): is the admin password still the stack's default?" % s)
    s, r = call("PUT", "/api/config/groups", {"yaml": open(os.path.join(ROOT, "packs", "workspaces.yaml")).read()})
    print("workspaces:", "loaded" if isinstance(r, dict) and r.get("success") else "FAILED %s %s" % (s, str(r)[:200]))
    users = {u["username"] for u in (call("GET", "/api/app-user-access")[1] or {}).get("users", [])}
    for name, (sql, src, up, start, appr) in GRANTS.items():
        if name not in users: print("  %s: no such login on this Server, skipped" % name); continue
        s, r = call("POST", "/api/app-user-access/update", {"username": name, "canSeeSql": sql, "canSeeSources": src, "canUploadFiles": up, "canStartWorkflows": start, "canApprove": appr})
        print("  %-8s %s" % (name, "ok" if isinstance(r, dict) and r.get("success") else "FAILED %s %s" % (s, str(r)[:120])))


if __name__ == "__main__": main()
