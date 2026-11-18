#!/usr/bin/env python3
"""Thinking layer, phase 2 skeleton (docs/agency-spec.md section 4): signs the user in to the OmniGate Server, lists packs, asks in a pack's Workspace and returns the
answer with an evidence block, reads the decision record, and lists the MCP tools generated from contract.json. Standard library only.

Environment: SERVER_URL (default http://omnigate:8080), PACKS_CATALOGUE, AGENCY_DECISION_FILE (only for a Server older than 0.10.20: its OMNIGATE_WORKFLOW_DECISION_FILE, shared read-only),
AGENCY_SCOPE_HINT=on to add the pack's data sets to the question when no Workspace exists (off by default: its effect on accuracy is not measured),
AGENCY_SESSION_HOURS (default 8), AGENCY_WEB_DIST (the built Agency UI, served at / when the folder exists), AGENCY_PREFS_FILE (per-user preferences, kept in
memory when unset), AGENCY_ADAPTERS (comma-separated adapter base URLs), AGENCY_UPLOAD_HOURS (record lifetime, default 1), AGENCY_UPLOAD_SHARING (off, the default, or workspace), AGENCY_UPLOAD_ADMINS (comma-separated Server usernames who may unshare or delete shared records), PORT (default 8097).
The layer logs no question text and no file content."""
import json, mimetypes, os, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
import adapters, catalogue, decisions, tools, uploads
from evidence import Evidence
from upstream import Upstream, Unauthorized

VERSION = "0.1.0"
COOKIE = "agency_session"
ALL_DATA = "all-data"
SERVER = Upstream(os.environ.get("SERVER_URL", "http://omnigate:8080"))
SESSION_SECONDS = float(os.environ.get("AGENCY_SESSION_HOURS", "8")) * 3600
MAX_SESSIONS = 500
SESSIONS = {}; SESSIONS_LOCK = threading.Lock()
WEB_DIST = os.environ.get("AGENCY_WEB_DIST", "/app/web")
ADAPTERS = adapters.Registry()
UPLOADS = uploads.Store(float(os.environ.get("AGENCY_UPLOAD_HOURS", "1")))
def sharing(): return "workspace" if os.environ.get("AGENCY_UPLOAD_SHARING", "off").strip().lower() == "workspace" else "off"
def upload_admin(user): return user in {u.strip() for u in os.environ.get("AGENCY_UPLOAD_ADMINS", "").split(",") if u.strip()}


PREFS = {}; PREFS_LOCK = threading.Lock(); PREF_KEYS = {"pack": 80}                         # the only preferences kept, with a length limit each


def load_prefs():
    path = os.environ.get("AGENCY_PREFS_FILE")
    if path and os.path.isfile(path):
        try: PREFS.update(json.load(open(path)))
        except (OSError, ValueError): pass


def save_prefs():
    path = os.environ.get("AGENCY_PREFS_FILE")
    if path:
        try: tmp = path + ".tmp"; json.dump(PREFS, open(tmp, "w")); os.replace(tmp, path)
        except OSError: pass


class Session:
    def __init__(self, username, cookie):
        self.username, self.cookie, self.workspace, self.last = username, cookie, "?", time.time()   # "?" = Server-side Workspace not known yet
        self.lock = threading.Lock()                                                               # one question at a time: the Workspace is session state on the Server
        self.starters = {}                                                                         # pack id ("" = all data) -> (time, the Server's answer), read before the first question


STARTER_TTL = 900


def prefetch_starters(s):
    """Once a Server session has a Workspace selected, /app/starter-questions answers with NOTHING (every Workspace, even all-data; app 0.10.21). Agency selects one on the first
    question, so a page reloaded after it would show no approved questions. The starters are read here, right after sign-in while the session has none, and kept."""
    for key in [""] + [p["id"] for p in catalogue.load()]:
        try: code, d = SERVER.json("GET", "/app/starter-questions" + ("?pack=" + quote(key, safe="") if key else ""), s.cookie)
        except (OSError, Unauthorized): return
        if code == 200 and isinstance(d, dict) and d.get("items"): s.starters[key] = (time.time(), d)


def new_session(username, cookie):
    with SESSIONS_LOCK:
        now = time.time()
        for t in [t for t, s in SESSIONS.items() if now - s.last > SESSION_SECONDS]: del SESSIONS[t]
        if len(SESSIONS) >= MAX_SESSIONS: raise RuntimeError("too many sessions")
        token = secrets.token_urlsafe(32); SESSIONS[token] = Session(username, cookie); return token


def hint_for(pack):
    sets = ", ".join("%s.%s" % (s["id"], x) for s in pack["sources"] for x in s["schemas"])
    return " (Use only these data sets: %s.)" % sets


class H(BaseHTTPRequestHandler):
    server_version = "thinking-layer/" + VERSION

    def log_message(self, *a): pass                                         # no request logging: paths can carry run ids, bodies carry questions

    # -- plumbing ------------------------------------------------------------------------------------------------------------------------------------------
    def send(self, code, obj, headers=()):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        for k, v in headers: self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def err(self, code, name, msg, **detail): self.send(code, {"error": {"code": name, "message": msg, "detail": detail}})

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000: raise ValueError("body too large")
        try: return json.loads(self.rfile.read(n) or b"{}")
        except ValueError: raise ValueError("body is not JSON")

    def session(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                s = SESSIONS.get(v)
                if s and time.time() - s.last <= SESSION_SECONDS: s.last = time.time(); return v, s
        return None, None

    def need_session(self):
        t, s = self.session()
        if not s: self.err(401, "not_signed_in", "Sign in first (POST /login)."); return None, None
        return t, s

    def lost(self, token):
        SESSIONS.pop(token, None); self.err(401, "server_session_ended", "The OmniGate session ended; sign in again.")

    # -- routes --------------------------------------------------------------------------------------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/health": return self.send(200, {"ok": True, "version": VERSION})
            if u.path == "/tools": return self.send(200, {"tools": tools.tool_list()})
            if u.path == "/status": return self.status()
            if u.path == "/packs": return self.packs()
            if u.path == "/whoami": return self.whoami()
            if u.path == "/decisions": return self.decisions((q.get("runId") or [""])[0])
            if u.path == "/starters": return self.starters((q.get("pack") or [""])[0])
            if u.path == "/conversations": return self.passthrough("/app/conversations")
            if u.path == "/conversations/get": return self.passthrough("/app/conversations/get?id=" + quote((q.get("id") or [""])[0], safe=""))
            if u.path == "/preferences": return self.preferences(None)
            if u.path == "/adapters": return self.list_adapters()
            if u.path == "/workflows/definitions": return self.wf("GET", "/app/workflows/definitions")
            if u.path == "/workflows/queue": return self.wf("GET", "/app/workflows/queue")
            if u.path.startswith("/workflows/"): return self.wf_run(u.path[11:], "GET")
            if u.path == "/uploads": return self.my_uploads(None)
            if u.path.startswith("/uploads/"): return self.my_uploads(u.path[9:])
            if not WEB_DIST or not os.path.isdir(WEB_DIST) or u.path.startswith(("/api/", "/app/")): return self.err(404, "not_found", "No such route.")
            self.static(u.path)
        except ValueError as e: self.err(400, "bad_request", str(e))

    def do_DELETE(self):
        u = urlparse(self.path)
        if self.headers.get("Cookie") and not self.headers.get("X-Requested-With"):
            return self.err(403, "cross_site_refused", "A state-changing request that carries a session cookie must also send the header X-Requested-With.")
        if not u.path.startswith("/uploads/"): return self.err(404, "not_found", "No such route.")
        t, s = self.need_session()
        if not s: return
        if UPLOADS.delete(s.username, u.path[9:], upload_admin(s.username)): return self.send(200, {"deleted": True})
        self.err(404, "upload_not_found", "No such upload.")

    def do_POST(self):
        u = urlparse(self.path)
        if self.headers.get("Cookie") and not self.headers.get("X-Requested-With"):         # same guard as the Server's: a page on another origin cannot add this header
            return self.err(403, "cross_site_refused", "A state-changing request that carries a session cookie must also send the header X-Requested-With.")
        try:
            if u.path == "/login": return self.login()
            if u.path == "/logout": return self.logout()
            if u.path == "/ask": return self.ask()
            if u.path == "/preferences": return self.preferences(self.body())
            if u.path == "/uploads": return self.upload(parse_qs(u.query))
            if u.path.startswith("/uploads/") and u.path.endswith("/share"): return self.share(u.path[9:-6], self.body())
            if u.path == "/workflows/start": return self.wf_start(self.body())
            if u.path.startswith("/workflows/") and u.path.endswith(("/approve", "/reject")): return self.wf_run(u.path[11:].rsplit("/", 1)[0], u.path.rsplit("/", 1)[1], self.body())
            self.err(404, "not_found", "No such route.")
        except ValueError as e: self.err(400, "bad_request", str(e))

    # -- adapters and uploads ------------------------------------------------------------------------------------------------------------------------------
    def list_adapters(self):
        t, s = self.need_session()
        if not s: return
        self.send(200, {"adapters": [{k: v for k, v in m.items()} for m in ADAPTERS.manifests()], "accept": ADAPTERS.accept_list(), "sharing": sharing()})

    def my_workspaces(self, t, s):
        """The Workspaces this user's OWN Server session lists: the Server's access rules, not the layer's, decide who may see a shared record."""
        _, a = SERVER.json("GET", "/app/namespaces", s.cookie)
        return {n["id"] for n in a.get("namespaces", [])}

    def my_uploads(self, rid):
        t, s = self.need_session()
        if not s: return
        admin, mode = upload_admin(s.username), sharing()
        try: have = self.my_workspaces(t, s) if mode == "workspace" else None
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if rid is None:
            out = {"uploads": UPLOADS.mine(s.username), "sharing": mode, "shared": UPLOADS.shared_with(s.username, have, admin) if have is not None else []}
            return self.send(200, out)
        r = UPLOADS.get(s.username, rid, have, admin and mode == "workspace")
        self.send(200, r) if r else self.err(404, "upload_not_found", "No such upload.")

    def share(self, rid, body):
        """Owner shares a record with the people who can use its Workspace, or takes it back. Never extends access: the owner must themselves have the Workspace."""
        t, s = self.need_session()
        if not s: return
        on = body.get("shared")
        if not isinstance(on, bool): return self.err(400, "bad_request", "shared must be true or false.")
        admin = upload_admin(s.username)
        if sharing() != "workspace" and on: return self.err(409, "sharing_off", "Sharing uploads is off on this deployment (AGENCY_UPLOAD_SHARING).")
        rec = UPLOADS.owned(s.username, rid)
        if on:
            if rec is None: return self.err(404, "upload_not_found", "No such upload.")
            if not rec["workspaceId"]: return self.err(400, "no_workspace", "This upload was not made inside a Workspace, so there is nobody to share it with.")
            try:
                if rec["workspaceId"] not in self.my_workspaces(t, s): return self.err(403, "workspace_not_yours", "You can only share into a Workspace you can use yourself.")
            except Unauthorized: return self.lost(t)
            except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        r = UPLOADS.set_shared(s.username, rid, on, admin)
        self.send(200, r) if r else self.err(404, "upload_not_found", "No such upload.")

    def upload(self, q):
        """Raw file body; query: name, workspaceId. Checks the type and size from the headers before reading a byte of the body."""
        t, s = self.need_session()
        if not s: return
        name = ((q.get("name") or [""])[0])[:200]; wid = (q.get("workspaceId") or [""])[0] or None; mime = self.headers.get("Content-Type")
        if not name: return self.err(400, "bad_request", "name is required.")
        manifest, url = ADAPTERS.find(name, mime)
        if not manifest: return self.err(415, "unsupported_type", "No enabled adapter reads this type.", accepted=ADAPTERS.accept_list())
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0: return self.err(400, "bad_request", "The file is empty.")
        if n > int(manifest.get("maxBytes") or 40_000_000): return self.err(413, "too_large", "That file is larger than this adapter accepts.", maxBytes=manifest.get("maxBytes"))
        try: code, w = SERVER.json("GET", "/app/whoami", s.cookie)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if not w.get("canUploadFiles"): return self.err(403, "missing_grant", "Your account has no permission to upload files (an admin grants it under Admin > users).")
        data = self.rfile.read(n)
        try: ing = ADAPTERS.ingest(url, name, mime, data)
        except adapters.AdapterError as e: return self.err(e.status, "adapter_refused" if e.status != 502 else "adapter_unavailable", e.message)
        finally: data = None                                                # the file is not kept
        if wid is None and sharing() == "workspace":                               # All data is a Workspace of its own when the stack has one (see ask())
            try: wid = ALL_DATA if ALL_DATA in self.my_workspaces(t, s) else None
            except (Unauthorized, OSError): wid = None
        rec = UPLOADS.add(s.username, name, wid, manifest, ing)
        if rec is None: return self.err(429, "too_many_uploads", "You have %d uploads; delete one first." % uploads.MAX_PER_USER)
        self.send(200, rec)

    def static(self, path):
        root = os.path.realpath(WEB_DIST); f = os.path.realpath(os.path.join(root, path.lstrip("/") or "index.html"))
        if not f.startswith(root + os.sep) or not os.path.isfile(f): f = os.path.join(root, "index.html")          # single-page app: unknown paths get the page
        try:
            with open(f, "rb") as fh: data = fh.read()
        except OSError: return self.err(404, "not_found", "No such file.")
        kind = mimetypes.guess_type(f)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if f.endswith(".html") else "public, max-age=31536000, immutable"); self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"); self.end_headers(); self.wfile.write(data)

    def passthrough(self, path):
        t, s = self.need_session()
        if not s: return
        try: code, data = SERVER.json("GET", path, s.cookie)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        self.send(code, data)

    def starters(self, pack):
        if pack and pack not in {p["id"] for p in catalogue.load()}: return self.err(404, "unknown_pack", "No such pack: %s" % pack)
        t, s = self.need_session()
        if not s: return
        key = pack or ""; cached = s.starters.get(key)
        if cached and time.time() - cached[0] < STARTER_TTL: return self.send(200, dict(cached[1], cached=True))
        try: code, d = SERVER.json("GET", "/app/starter-questions" + ("?pack=" + quote(pack, safe="") if pack else ""), s.cookie)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code == 200 and isinstance(d, dict) and d.get("items"): s.starters[key] = (time.time(), d); return self.send(200, d)
        if cached: return self.send(200, dict(cached[1], cached=True, stale=True))             # the Server answers nothing once a Workspace is selected: keep what it said before
        self.send(code, d)

    def preferences(self, body):
        t, s = self.need_session()
        if not s: return
        with PREFS_LOCK:
            mine = PREFS.setdefault(s.username, {})
            if body is not None:
                for k, v in body.items():
                    if k not in PREF_KEYS: return self.err(400, "bad_request", "Unknown preference: %s" % k)
                    if v is None: mine.pop(k, None)
                    elif isinstance(v, str) and len(v) <= PREF_KEYS[k]: mine[k] = v
                    else: return self.err(400, "bad_request", "Preference %s must be a string of at most %d characters." % (k, PREF_KEYS[k]))
                save_prefs()
            self.send(200, dict(mine))

    # -- sign-in -------------------------------------------------------------------------------------------------------------------------------------------
    def login(self):
        b = self.body(); u, p = b.get("username"), b.get("password")
        if not isinstance(u, str) or not isinstance(p, str) or not u: return self.err(400, "bad_request", "username and password are required.")
        try: ok, cookie, data = SERVER.login(u, p)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if not ok: return self.err(401, "login_refused", str(data.get("error") or "Sign-in was refused."))
        try: token = new_session(u, cookie)
        except RuntimeError: return self.err(503, "too_many_sessions", "Too many active sessions.")
        threading.Thread(target=prefetch_starters, args=(SESSIONS[token],), daemon=True).start()
        self.send(200, {"success": True, "username": u}, [("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d" % (COOKIE, token, int(SESSION_SECONDS)))])

    def logout(self):
        t, s = self.session()
        if s:
            try: SERVER.json("POST", "/app/logout", s.cookie)
            except (OSError, Unauthorized): pass
            SESSIONS.pop(t, None)
        self.send(200, {"success": True}, [("Set-Cookie", "%s=; Path=/; Max-Age=0" % COOKIE)])

    def whoami(self):
        t, s = self.need_session()
        if not s: return
        try: code, data = SERVER.json("GET", "/app/whoami", s.cookie)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        self.send(200, dict(data, layerUser=s.username))

    # -- status and packs ----------------------------------------------------------------------------------------------------------------------------------
    def status(self):
        out = {"layer": {"version": VERSION}, "server": {"url": SERVER.base, "reachable": False},
               "decisions": {"readable": bool(os.environ.get("AGENCY_DECISION_FILE"))}, "scopeHint": os.environ.get("AGENCY_SCOPE_HINT") == "on"}
        try:
            code, cfg = SERVER.json("GET", "/app/public-config"); out["server"].update(reachable=code == 200, llmConfigured=cfg.get("llmConfigured"))
        except (OSError, Unauthorized): pass
        t, s = self.session()
        if s:
            try:
                code, w = SERVER.json("GET", "/app/whoami", s.cookie)
                feats = w.get("features") if code == 200 and isinstance(w, dict) else None
                if code == 200 and isinstance(w, dict) and w.get("edition"): out["edition"] = w["edition"]           # app 0.10.20 and later (Server#113)
                if isinstance(feats, dict) and "workflows" in feats:             # the Server says so: no probing for a 404
                    out["workflows"] = {"available": bool(feats["workflows"]), "note": "" if feats["workflows"] else "Workflows are off: they need the commercial edition and an enabled workflow engine."}
                    out["decisions"] = {"readable": bool(feats["workflows"]), "via": "server" if feats["workflows"] else None}
                else:                                                            # an older Server: probe, as before
                    code, _ = SERVER.json("GET", "/app/workflows/definitions", s.cookie)
                    out["workflows"] = {"available": code == 200, "note": "" if code == 200 else "The workflow routes answer %d: the free edition, or workflows are off." % code}
                    if out["decisions"]["readable"]: out["decisions"]["via"] = "file"
            except (OSError, Unauthorized): pass
        self.send(200, out)

    def packs(self):
        ps = catalogue.load(); t, s = self.session(); ws, cats, note = set(), set(), "Sign in to see which packs are loaded."
        if s:
            try:
                _, a = SERVER.json("GET", "/app/namespaces", s.cookie); ws = {n["id"] for n in a.get("namespaces", [])}
                _, b = SERVER.json("GET", "/app/starter-questions", s.cookie); cats = {p["id"] for p in b.get("packs", [])}; note = None
            except Unauthorized: return self.lost(t)
            except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        self.send(200, {"packs": catalogue.with_loaded(ps, ws, cats) if s else [dict(p, loaded=None, loadedReason=note) for p in ps], "note": note})

    # -- ask -----------------------------------------------------------------------------------------------------------------------------------------------
    def ask(self):
        t, s = self.need_session()
        if not s: return
        b = self.body(); question = b.get("question"); wid = b.get("workspaceId")
        if not isinstance(question, str) or not question.strip(): return self.err(400, "bad_request", "question is required.")
        if len(question) > 4000: return self.err(400, "bad_request", "question is too long (4000 characters).")
        pack = next((p for p in catalogue.load() if p["id"] == wid), None) if wid else None
        if wid and not pack: return self.err(404, "unknown_pack", "No such pack: %s" % wid, packs=[p["id"] for p in catalogue.load()])
        stream = "text/event-stream" in (self.headers.get("Accept") or "")
        started = time.time()
        with s.lock:
            try:
                target, scope = None, "none"
                _, a = SERVER.json("GET", "/app/namespaces", s.cookie); have = {n["id"] for n in a.get("namespaces", [])}
                if pack:
                    if pack["id"] in have: target, scope = pack["id"], "server-backends"
                    elif os.environ.get("AGENCY_SCOPE_HINT") == "on": scope = "agency-hint"; question = question.strip() + hint_for(pack)
                elif ALL_DATA in have: target = ALL_DATA              # once packs are Workspaces the Server's Default one is empty; All data is its own Workspace
                if s.workspace != target:                                    # None selects the default ("all data") Workspace, as the Ask app's "All groups" does
                    code, r = SERVER.json("POST", "/app/session/namespace", s.cookie, {"namespaceId": target})
                    if code != 200 or not r.get("success"): return self.err(409, "workspace_refused", str(r.get("error") or "The Server refused the Workspace."), workspaceId=target)
                    s.workspace = target
                ev = Evidence(target, pack, scope, started); events = SERVER.ask_events(s.cookie, {"question": question, "conversationId": b.get("conversationId")})
                if stream: return self.relay(events, ev)
                last = None
                for e in events:
                    ev.see(e)
                    if e.get("step") in ("done", "error", "stopped", "approval_needed"): last = e
                if last is None: return self.err(502, "no_answer", "The Server ended the stream without an answer.")
                if last["step"] != "done": return self.send(200, {"result": last, "evidence": ev.build(time.time())})
                out = {k: last.get(k) for k in ("answer", "columns", "rows", "sql", "conversationId", "suggestedQuestions", "truncated")}
                if ev.sql_hidden: out["sql"] = None
                self.send(200, dict(out, evidence=ev.build(time.time())))
            except Unauthorized: self.lost(t)
            except OSError: self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")

    def relay(self, events, ev):
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store"); self.send_header("Connection", "close"); self.end_headers()
        def out(o): self.wfile.write(b"data: " + json.dumps(o).encode() + b"\n\n"); self.wfile.flush()
        for e in events:
            ev.see(e)
            if e.get("step") == "done": out({"step": "evidence", "evidence": ev.build(time.time())})   # before the terminal frame, so done stays last
            out(e)

    # -- workflows (the Server's workflow API, v0.10.19: commercial edition, off unless the operator enabled an engine) --------------------------------------
    def wf(self, method, path, body=None):
        """Relay one workflow call as the signed-in user. The Server enforces every rule (grants, initiator, hash, duplicates); the layer only reshapes errors and never names a user."""
        t, s = self.need_session()
        if not s: return
        try: code, d = SERVER.json(method, path, s.cookie, body)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code < 400: return self.send(code, d)
        if not isinstance(d, dict) or not d.get("code"):
            if code == 404: return self.err(404, "workflows_off", "Workflows are off on this Server: they need the commercial edition and an operator-enabled workflow engine.")
            return self.err(code, "server_error", "The Server refused the request (HTTP %d)." % code)
        detail = {k: d[k] for k in ("grant",) if k in d}
        self.err(code, d["code"], str(d.get("error") or d["code"]), **detail)

    RUN_ID = __import__("re").compile(r"^[A-Za-z0-9_-]{1,80}$")

    def wf_run(self, rid, action, body=None):
        if not self.RUN_ID.match(rid): return self.err(404, "unknown_run", "No such run.")
        if action == "GET": return self.wf("GET", "/app/workflows/runs/" + rid)
        if action == "approve":
            h = (body or {}).get("payloadHash")
            if not isinstance(h, str) or not 8 <= len(h) <= 128 or not all(c in "0123456789abcdefABCDEF" for c in h): return self.err(400, "bad_request", "payloadHash must be the run's hash (hex).")
            return self.wf("POST", "/app/workflows/runs/%s/approve" % rid, {"payloadHash": h})
        if action == "reject":
            r = (body or {}).get("reason")
            if not isinstance(r, str) or not r.strip() or len(r) > 1000: return self.err(400, "bad_request", "reason is required (up to 1000 characters).")
            return self.wf("POST", "/app/workflows/runs/%s/reject" % rid, {"reason": r.strip()})
        self.err(404, "not_found", "No such route.")

    def wf_start(self, body):
        d, k = (body or {}).get("definition"), (body or {}).get("key")
        if isinstance(k, (int, float)) and not isinstance(k, bool): k = str(k)
        if not isinstance(d, str) or not d.strip() or len(d) > 100 or not isinstance(k, str) or not k.strip() or len(k) > 200: return self.err(400, "bad_request", "definition and key are required.")
        self.wf("POST", "/app/workflows/start", {"definition": d.strip(), "key": k.strip()})

    # -- decisions -----------------------------------------------------------------------------------------------------------------------------------------
    def decisions(self, run_id):
        """The decision record of one run. App 0.10.20 and later answer it themselves (GET /app/workflows/runs/{id}/decisions, Server#112) with the same access as reading the run; the layer
        also recomputes every returned entry's hash. An older Server has no such route: then the shared decision file (AGENCY_DECISION_FILE) is read, as before."""
        t, s = self.need_session()
        if not s: return
        if not run_id: return self.err(400, "bad_request", "runId is required.")
        if not self.RUN_ID.match(run_id): return self.err(404, "run_not_visible", "That run is not visible to you.")
        try: code, d = SERVER.json("GET", "/app/workflows/runs/%s/decisions" % run_id, s.cookie)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code == 200 and isinstance(d, dict) and isinstance(d.get("entries"), list):
            es = d["entries"]
            return self.send(200, {"runId": run_id, "source": "server", "chainValid": bool(d.get("chainValid")), "firstBadSeq": d.get("chainBrokenAtSeq"), "totalEntries": None, "count": len(es),
                                   "entriesVerified": all(decisions.entry_hash(e) == e.get("hash") for e in es), "entries": es})
        if code in (401, 403) or (code == 404 and isinstance(d, dict) and d.get("code") == "unknown_run"): return self.err(403 if code in (401, 403) else 404, "run_not_visible", "That run is not visible to you.")
        path = os.environ.get("AGENCY_DECISION_FILE")                          # no such route (an older Server, or workflows off): the file, if one is shared
        if not path: return self.err(501, "decisions_unavailable", "This Server does not serve the decision record (it is older than 0.10.20): set AGENCY_DECISION_FILE to its decision file, shared read-only.")
        try: code, _ = SERVER.json("GET", "/app/workflows/runs/" + run_id, s.cookie)     # the Server decides whether this user may see the run
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code != 200: return self.err(403 if code in (401, 403) else 404, "run_not_visible", "That run is not visible to you.")
        try: es = decisions.read(path)
        except OSError: return self.err(502, "decisions_unreadable", "The decision file could not be read.")
        ok, bad = decisions.verify(es); mine = [e for e in es if e.get("runId") == run_id]
        self.send(200, {"runId": run_id, "source": "file", "chainValid": ok, "firstBadSeq": bad, "totalEntries": len(es), "count": len(mine), "entriesVerified": all(decisions.entry_hash(e) == e.get("hash") for e in mine), "entries": mine})


def main():
    load_prefs(); port = int(os.environ.get("PORT", "8097")); ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__": main()
