#!/usr/bin/env python3
"""Thinking layer, phase 2 skeleton (docs/agency-spec.md section 4): signs the user in to the OmniGate Server, lists packs, asks in a pack's Workspace and returns the
answer with an evidence block, reads the decision record, and lists the MCP tools generated from contract.json. Standard library only.

Environment: SERVER_URL (default http://omnigate:8080), PACKS_CATALOGUE, AGENCY_DECISION_FILE (the Server's OMNIGATE_WORKFLOW_DECISION_FILE, shared read-only),
AGENCY_SCOPE_HINT=on to add the pack's data sets to the question when no Workspace exists (off by default: its effect on accuracy is not measured),
AGENCY_SESSION_HOURS (default 8), AGENCY_WEB_DIST (the built Agency UI, served at / when the folder exists), AGENCY_PREFS_FILE (per-user preferences, kept in
memory when unset), PORT (default 8097).
The layer logs no question text and no file content."""
import json, mimetypes, os, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
import catalogue, decisions, tools
from evidence import Evidence
from upstream import Upstream, Unauthorized

VERSION = "0.1.0"
COOKIE = "agency_session"
SERVER = Upstream(os.environ.get("SERVER_URL", "http://omnigate:8080"))
SESSION_SECONDS = float(os.environ.get("AGENCY_SESSION_HOURS", "8")) * 3600
MAX_SESSIONS = 500
SESSIONS = {}; SESSIONS_LOCK = threading.Lock()
WEB_DIST = os.environ.get("AGENCY_WEB_DIST", "/app/web")
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
            if not WEB_DIST or not os.path.isdir(WEB_DIST) or u.path.startswith(("/api/", "/app/")): return self.err(404, "not_found", "No such route.")
            self.static(u.path)
        except ValueError as e: self.err(400, "bad_request", str(e))

    def do_POST(self):
        u = urlparse(self.path)
        if self.headers.get("Cookie") and not self.headers.get("X-Requested-With"):         # same guard as the Server's: a page on another origin cannot add this header
            return self.err(403, "cross_site_refused", "A state-changing request that carries a session cookie must also send the header X-Requested-With.")
        try:
            if u.path == "/login": return self.login()
            if u.path == "/logout": return self.logout()
            if u.path == "/ask": return self.ask()
            if u.path == "/preferences": return self.preferences(self.body())
            self.err(404, "not_found", "No such route.")
        except ValueError as e: self.err(400, "bad_request", str(e))

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
        self.passthrough("/app/starter-questions" + ("?pack=" + quote(pack, safe="") if pack else ""))

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
                code, _ = SERVER.json("GET", "/app/workflows/definitions", s.cookie)
                out["workflows"] = {"available": code == 200, "note": "" if code == 200 else "The workflow routes answer %d: the free edition, or workflows are off." % code}
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
                if pack:
                    _, a = SERVER.json("GET", "/app/namespaces", s.cookie)
                    if pack["id"] in {n["id"] for n in a.get("namespaces", [])}: target, scope = pack["id"], "server-backends"
                    elif os.environ.get("AGENCY_SCOPE_HINT") == "on": scope = "agency-hint"; question = question.strip() + hint_for(pack)
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

    # -- decisions -----------------------------------------------------------------------------------------------------------------------------------------
    def decisions(self, run_id):
        t, s = self.need_session()
        if not s: return
        path = os.environ.get("AGENCY_DECISION_FILE")
        if not path: return self.err(501, "decisions_unavailable", "Set AGENCY_DECISION_FILE to the Server's decision file, shared read-only. The Server has no business-user route for the record.")
        if not run_id: return self.err(400, "bad_request", "runId is required.")
        try: code, _ = SERVER.json("GET", "/app/workflows/runs/" + run_id.replace("/", ""), s.cookie)     # the Server decides whether this user may see the run
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code != 200: return self.err(403 if code in (401, 403) else 404, "run_not_visible", "That run is not visible to you.")
        try: es = decisions.read(path)
        except OSError: return self.err(502, "decisions_unreadable", "The decision file could not be read.")
        ok, bad = decisions.verify(es)
        self.send(200, {"runId": run_id, "chainValid": ok, "firstBadSeq": bad, "totalEntries": len(es), "entries": [e for e in es if e.get("runId") == run_id]})


def main():
    load_prefs(); port = int(os.environ.get("PORT", "8097")); ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__": main()
