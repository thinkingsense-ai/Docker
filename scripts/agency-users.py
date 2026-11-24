#!/usr/bin/env python3
"""Add business logins to a deployed stack and set what each may do: the way to get the second and third person a two-person approval needs (the deploy forms create one login).
Uses the admin API with the stack's admin API token (never printed). Standard library only.

  scripts/agency-users.py URL TOKEN list
  scripts/agency-users.py URL TOKEN add NAME [--start] [--approve] [--upload] [--sql] [--sources] [--insecure] [--out FILE]
  scripts/agency-users.py URL TOKEN grant NAME [--start] [--approve] [--upload] [--sql] [--sources] [--insecure]     (sets exactly the flags given; a flag left out is off)

URL is the Ask app's address (https://...). TOKEN is read from the environment variable named by --token-env if the argument is "-" (so it stays out of your shell history).
`add` makes a random password and appends it to FILE (default ~/.thinkingsense/agency-users.env, owner-only) instead of printing it.
  --start    may start workflows        --approve  may approve workflows (never the person who started the run)
  --upload   may upload files           --sql      may see the SQL behind an answer        --sources  may see the data sources used
A stack made from the AWS form uses a self-signed certificate: pass --insecure (or set VERIFY_CA to a CA file)."""
import json, os, secrets, ssl, sys, urllib.error, urllib.request

FLAGS = {"--start": "canStartWorkflows", "--approve": "canApprove", "--upload": "canUploadFiles", "--sql": "canSeeSql", "--sources": "canSeeSources"}

def main(argv):
    if len(argv) < 3: print(__doc__); return 2
    base, token, cmd = argv[0].rstrip("/"), argv[1], argv[2]
    rest = argv[3:]
    if token == "-": token = os.environ.get(os.environ.get("TOKEN_ENV", "ADMIN_API_TOKEN"), "")
    if not token: print("no admin API token (pass it, or '-' with ADMIN_API_TOKEN set)"); return 2
    ctx = ssl.create_default_context(cafile=os.environ["VERIFY_CA"]) if os.environ.get("VERIFY_CA") else ssl.create_default_context()
    if "--insecure" in rest: ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    out = os.path.expanduser("~/.thinkingsense/agency-users.env")
    if "--out" in rest: out = os.path.expanduser(rest[rest.index("--out") + 1])
    def call(path, body=None):
        req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None, {"Authorization": "Bearer " + token, "Content-Type": "application/json", "X-Requested-With": "agency-users"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r: return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e: return e.code, {"error": e.read().decode()[:200]}
        except urllib.error.URLError as e: return 0, {"error": str(e.reason)}
    def grants(name):
        g = {"username": name}
        for flag, key in FLAGS.items(): g[key] = flag in rest
        return g
    if cmd == "list":
        s, d = call("/api/app-user-access")
        if s != 200: print("failed:", s, d); return 1
        for u in d.get("users", []): print("%-20s %s" % (u["username"], ", ".join(k for k in FLAGS.values() if u.get(k)) or "(read only)"))
        return 0
    name = rest[0] if rest and not rest[0].startswith("--") else None
    if not name: print("a user name is required"); return 2
    if cmd == "add":
        pw = secrets.token_urlsafe(14); s, d = call("/api/app-users/add", {"username": name, "password": pw})
        if s != 200 or d.get("success") is False: print("add failed:", s, d); return 1
        os.makedirs(os.path.dirname(out), exist_ok=True); fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f: f.write("%s=%s\n" % (name, pw))
        print("added %s; password saved in %s" % (name, out))
    elif cmd != "grant": print(__doc__); return 2
    s, d = call("/api/app-user-access/update", grants(name))
    if s != 200 or d.get("success") is False: print("grant failed:", s, d); return 1
    print("%s may: %s" % (name, ", ".join(k for k in FLAGS.values() if grants(name)[k]) or "(read only)")); return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
