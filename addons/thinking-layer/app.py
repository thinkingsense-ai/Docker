#!/usr/bin/env python3
"""Thinking layer, phase 2 skeleton (docs/agency-spec.md section 4): signs the user in to the OmniGate Server, lists packs, asks in a pack's Workspace and returns the
answer with an evidence block, reads the decision record, and lists the MCP tools generated from contract.json. Standard library only.

Environment: SERVER_URL (default http://omnigate:8080), PACKS_CATALOGUE, AGENCY_DECISION_FILE (only for a Server older than 0.10.20: its OMNIGATE_WORKFLOW_DECISION_FILE, shared read-only),
AGENCY_SCOPE_HINT=on to add the pack's data sets to the question when no Workspace exists (off by default: its effect on accuracy is not measured),
AGENCY_SESSION_HOURS (default 8), AGENCY_WEB_DIST (the built Agency UI, served at / when the folder exists), AGENCY_PREFS_FILE (per-user preferences, kept in
memory when unset), AGENCY_ADAPTERS (comma-separated adapter base URLs), AGENCY_UPLOAD_HOURS (record lifetime, default 1), AGENCY_UPLOAD_SHARING (off, the default, or workspace), AGENCY_UPLOAD_ADMINS (comma-separated Server usernames who may unshare or delete shared records), AGENCY_ADMIN_URL (the admin console, shown as a quiet Manage link) and AGENCY_ADMIN_USERS (optional: only these usernames see it), AGENCY_PUBLIC_URL (where browsers reach the layer; turns on single sign-on, and PUBLIC_URL/app/oidc/callback must be registered with the identity provider), PORT (default 8097).
The layer logs no question text and no file content."""
import json, mimetypes, os, re, secrets, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
import adapters, audit, catalogue, decisions, tools, uploads
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
        self.epoch = 0; self.starters = {}                                                                         # pack id ("" = all data) -> (time, the Server's answer), read before the first question


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


PUBLIC = os.environ.get("AGENCY_PUBLIC_URL", "").strip().rstrip("/")                    # where browsers reach the layer: single sign-on needs it (the provider's redirect address)
SSO_PENDING = {}; SSO_TTL = 600                                                          # browser binding id -> (the Server's state cookie, the state, expiry)
SSO_COOKIE = "agency_sso"
SSO_MESSAGES = {"failed": "Single sign-on did not complete. Try again.", "unknown": "Your identity provider signed you in, but there is no OmniGate account for you. Ask an administrator."}


def sso_enabled(): return bool(PUBLIC) and urlparse(PUBLIC).scheme in ("http", "https") and bool(urlparse(PUBLIC).netloc)


def admin_link(user):
    """The 'Manage' link: AGENCY_ADMIN_URL (http or https), shown only to AGENCY_ADMIN_USERS when that is set. A convenience, not a control: the admin console has its own sign-in and roles."""
    url = os.environ.get("AGENCY_ADMIN_URL", "").strip(); p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc: return None
    only = {u.strip() for u in os.environ.get("AGENCY_ADMIN_USERS", "").split(",") if u.strip()}
    return url if not only or user in only else None


def tour_readonly():
    """AGENCY_DEMO_TOUR=readonly: the click-through of the screens that only READ (no demo person is signed in, no password is held here, no workflow run is started). Safe on a shared stack."""
    return os.environ.get("AGENCY_DEMO_TOUR") == "readonly"


def tour_personas():
    """The demo people the tour may sign in as: AGENCY_DEMO_PERSONAS="alice:pw,bob:pw", honoured only when AGENCY_DEMO_TOUR=on. Local demo sandbox only."""
    if os.environ.get("AGENCY_DEMO_TOUR") != "on": return {}
    out = {}
    for part in os.environ.get("AGENCY_DEMO_PERSONAS", "").split(","):
        n, _, pw = part.strip().partition(":")
        if n and pw: out[n] = pw
    return out


def audit_enabled(): return bool(os.environ.get("AGENCY_AUDIT_FILE", "").strip())


def audit_allowed(user):
    """May this signed-in person read the workflow decision record? Only the users listed in AGENCY_AUDIT_USERS, and only when AGENCY_AUDIT_FILE is set. A convenience, NOT a Server-enforced control:
    the Server has no read-only audit grant yet (design note S1), so the layer keeps its own list and says so."""
    only = {u.strip() for u in os.environ.get("AGENCY_AUDIT_USERS", "").split(",") if u.strip()}
    return audit_enabled() and user in only


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

    def send_text(self, code, text, ctype, filename):
        b = text.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename); self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
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
            if u.path == "/tour": return self.tour_info()
            if u.path == "/sso/config": return self.sso_config()
            if u.path == "/sso/login": return self.sso_login()
            if u.path == "/app/oidc/callback": return self.sso_callback(u.query)
            if u.path == "/packs": return self.packs()
            if u.path == "/whoami": return self.whoami()
            if u.path == "/decisions": return self.decisions((q.get("runId") or [""])[0])
            if u.path == "/audit/records": return self.audit_records(q, False)
            if u.path == "/audit/export": return self.audit_records(q, True)
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
            if u.path == "/tour/signin": return self.tour_signin(self.body())
            if u.path == "/ask": return self.ask()
            if u.path == "/preferences": return self.preferences(self.body())
            if u.path == "/uploads": return self.upload(parse_qs(u.query))
            if u.path.startswith("/uploads/") and u.path.endswith("/share"): return self.share(u.path[9:-6], self.body())
            if u.path == "/workflows/start": return self.wf_start(self.body())
            if u.path == "/feedback": return self.feedback(self.body())
            if u.path == "/cancel": return self.cancel(self.body())
            if u.path == "/help": return self.help_request(self.body())
            if u.path == "/reusable": return self.reusable(self.body())
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
        except adapters.AdapterError as e: data = None; return self.err(e.status, "adapter_refused" if e.status != 502 else "adapter_unavailable", e.message)
        server = None
        if manifest.get("kind") == "table" and os.environ.get("AGENCY_TABLE_TO_SERVER", "on") != "off": server, ing = self.push_table(s, name, data, ing)
        data = None                                                         # the file is not kept
        if wid is None and sharing() == "workspace":                               # All data is a Workspace of its own when the stack has one (see ask())
            try: wid = ALL_DATA if ALL_DATA in self.my_workspaces(t, s) else None
            except (Unauthorized, OSError): wid = None
        rec = UPLOADS.add(s.username, name, wid, manifest, ing, server)
        if rec is None: return self.err(429, "too_many_uploads", "You have %d uploads; delete one first." % uploads.MAX_PER_USER)
        self.send(200, rec)

    SERVER_TABLE_EXT = (".csv", ".xlsx")                    # what the Server's own scratch upload reads (up to 5,000 rows, kept 30 minutes, one conversation)

    def push_table(self, s, name, data, ing):
        """Give the Server a conversation-scoped copy of a table (POST /app/uploads) so the person can ask about it. The Server reads comma CSV and XLSX, holds at most 5,000 rows for
        30 minutes and shows the file to that one conversation only; it is never a registered data source. A refusal leaves the adapter's profile in place and says so."""
        ing = dict(ing); notes = [n for n in (ing.get("notes") or []) if "not in any Server data source" not in n]
        why = None
        if not name.lower().endswith(self.SERVER_TABLE_EXT): why = "Only CSV and Excel (.xlsx) files can be asked about; this one is described only."
        else:
            try:
                code, r = SERVER.json("POST", "/app/uploads", s.cookie, {"conversationId": None, "filename": name, "fileBase64": __import__("base64").b64encode(data).decode()})
                if code == 200 and isinstance(r, dict) and r.get("success") and r.get("uploadId") and r.get("conversationId"):
                    ing["notes"] = notes + ["Loaded for questions in this conversation only: %d rows%s, kept by the Server for 30 minutes, and visible to no one else." % (r.get("rowCount") or 0, " (the file was longer; the Server loads at most 5,000)" if r.get("truncated") else "")]
                    ing["askPrompts"] = ["What columns does %s have?" % name, "Summarise %s" % name, "What is the total of each numeric column in %s?" % name]
                    return {"uploadId": r["uploadId"], "conversationId": r["conversationId"], "untilEpoch": time.time() + 29 * 60, "session": (s.cookie, s.epoch)}, ing
                why = str(r.get("error") or "The Server did not accept the file for questions.") if isinstance(r, dict) else "The Server did not accept the file for questions."
            except (OSError, Unauthorized, ValueError): why = "The Server could not be reached to load the file for questions."
        ing["notes"] = notes + [why + " It is described only."]; ing["askPrompts"] = []
        return None, ing

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
        self.sign_in(u, p)

    # -- demo tour: switch between the demo people without typing a password. Only when AGENCY_DEMO_TOUR=on; the passwords stay here and are never sent to the browser. ---
    def tour_info(self):
        ps = tour_personas(); self.send(200, {"enabled": bool(ps) or tour_readonly(), "personas": list(ps), "readOnly": tour_readonly()})

    def tour_signin(self, body):
        ps = tour_personas(); name = body.get("persona")
        if not ps: return self.err(404, "not_found", "The demo tour is not switched on (AGENCY_DEMO_TOUR=on).")
        if not isinstance(name, str) or name not in ps: return self.err(400, "unknown_persona", "Unknown demo person. Choose one of: %s." % ", ".join(ps))
        self.sign_in(name, ps[name], retire=self.session())      # the new session exists before the old one ends, so a request already in flight is not refused in between

    def sign_in(self, u, p, retire=None):
        try: ok, cookie, data = SERVER.login(u, p)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if not ok: return self.err(401, "login_refused", str(data.get("error") or "Sign-in was refused."))
        try: token = new_session(u, cookie)
        except RuntimeError: return self.err(503, "too_many_sessions", "Too many active sessions.")
        threading.Thread(target=prefetch_starters, args=(SESSIONS[token],), daemon=True).start()
        if retire and retire[1]:
            try: SERVER.json("POST", "/app/logout", retire[1].cookie)
            except (OSError, Unauthorized): pass
            SESSIONS.pop(retire[0], None)
        self.send(200, {"success": True, "username": u}, [("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d%s" % (COOKIE, token, int(SESSION_SECONDS), SECURE))])

    # -- single sign-on: the Server's own OIDC redirect, relayed. The Server sets its session cookie on whoever finishes the callback, so the layer finishes it (the provider returns
    # to AGENCY_PUBLIC_URL + /app/oidc/callback, which must be registered with the provider) and keeps that cookie, as it does after a password sign-in. ------------------------
    def sso_config(self):
        if not sso_enabled(): return self.send(200, {"enabled": False})
        try: code, d = SERVER.json("GET", "/app/auth-config")
        except (OSError, Unauthorized): return self.send(200, {"enabled": False})
        on = code == 200 and bool(d.get("ssoEnabled"))
        self.send(200, {"enabled": on, "label": d.get("ssoLabel") or "single sign-on"} if on else {"enabled": False})

    def redirect(self, where, cookies=()):
        self.send_response(302); self.send_header("Location", where); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", "0")
        for c in cookies: self.send_header("Set-Cookie", c)
        self.end_headers()

    def sso_login(self):
        if not sso_enabled(): return self.err(404, "not_found", "Single sign-on is not set up for Agency (AGENCY_PUBLIC_URL).")
        pu = urlparse(PUBLIC)
        try: code, where, ck = SERVER.sso_start(pu.netloc, pu.scheme)
        except OSError: return self.redirect("/?sso=failed")
        state = (parse_qs(urlparse(where or "").query).get("state") or [""])[0]
        if code not in (301, 302, 303, 307) or not where or "omnigate_app_oidc_state" not in ck or not state: return self.redirect("/?sso=failed")
        bind = secrets.token_urlsafe(24); now = time.time()
        with SESSIONS_LOCK:
            for k in [k for k, v in SSO_PENDING.items() if v[2] < now]: del SSO_PENDING[k]
            if len(SSO_PENDING) >= MAX_SESSIONS: return self.redirect("/?sso=failed")
            SSO_PENDING[bind] = (ck["omnigate_app_oidc_state"], state, now + SSO_TTL)
        # Lax, not Strict: the provider's answer arrives as a cross-site top-level navigation, which Strict would not carry.
        self.redirect(where, ["%s=%s; Path=/app/oidc; HttpOnly; SameSite=Lax; Max-Age=%d%s" % (SSO_COOKIE, bind, SSO_TTL, "; Secure" if PUBLIC.startswith("https") else "")])

    def sso_callback(self, query):
        gone = "%s=; Path=/app/oidc; Max-Age=0" % SSO_COOKIE
        if not sso_enabled(): return self.err(404, "not_found", "Single sign-on is not set up for Agency.")
        bind = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == SSO_COOKIE: bind = v
        with SESSIONS_LOCK: pend = SSO_PENDING.pop(bind, None)
        if not pend or pend[2] < time.time() or (parse_qs(query).get("state") or [""])[0] != pend[1]: return self.redirect("/?sso=failed", [gone])   # not the browser that began it, or too late
        pu = urlparse(PUBLIC)
        try: code, where, ck = SERVER.sso_finish(pu.netloc, pu.scheme, query, pend[0])
        except OSError: return self.redirect("/?sso=failed", [gone])
        cookie = ck.get("omnigate_app_session")
        if not cookie or code not in (301, 302, 303, 307):
            return self.redirect("/?sso=" + ("unknown" if "sso=unknown" in (where or "") else "failed"), [gone])
        try: c, who = SERVER.json("GET", "/app/whoami", cookie); name = (who.get("userId") or who.get("username")) if c == 200 else None
        except (OSError, Unauthorized): name = None
        if not name: return self.redirect("/?sso=failed", [gone])
        try: token = new_session(name, cookie)
        except RuntimeError: return self.redirect("/?sso=failed", [gone])
        threading.Thread(target=prefetch_starters, args=(SESSIONS[token],), daemon=True).start()
        self.redirect("/", [gone, "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d%s" % (COOKIE, token, int(SESSION_SECONDS), SECURE)])

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
        out["tour"] = {"enabled": bool(tour_personas()) or tour_readonly(), "readOnly": tour_readonly()}
        t, s = self.session()
        out["audit"] = {"enabled": audit_enabled(), "allowed": bool(s and audit_allowed(s.username))}
        if s:
            url = admin_link(s.username)
            if url: out["adminUrl"] = url
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
                body = {"question": question, "conversationId": b.get("conversationId")}
                tgt = None
                if b.get("uploadId") not in (None, ""):                              # a table the person uploaded: the Server's own copy and the conversation it belongs to
                    tgt = UPLOADS.ask_target(s.username, b["uploadId"], (s.cookie, s.epoch)) if isinstance(b["uploadId"], str) else None
                    if not tgt: return self.err(404, "upload_expired", "That uploaded table is no longer available to ask about (it lasts 30 minutes, and ends when you ask about a different domain). Upload it again.")
                    body["uploadId"], body["conversationId"] = tgt
                if s.workspace != target and not tgt:                        # (an upload question stays where the upload was made: switching would drop the file) None selects the default ("all data") Workspace, as the Ask app's "All groups" does
                    code, r = SERVER.json("POST", "/app/session/namespace", s.cookie, {"namespaceId": target})
                    if code != 200 or not r.get("success"): return self.err(409, "workspace_refused", str(r.get("error") or "The Server refused the Workspace."), workspaceId=target)
                    s.workspace = target; s.epoch += 1; UPLOADS.forget_server_copies(s.username, s.cookie)
                if tgt: target, scope = (s.workspace if s.workspace != "?" else None), "none"      # the file's own conversation; no Workspace claim is made for it
                ev = Evidence(target, pack, scope, started); events = SERVER.ask_events(s.cookie, body)
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
    def wf(self, method, path, body=None, off="Workflows are off on this Server: they need the commercial edition and an operator-enabled workflow engine."):
        """Relay one workflow call as the signed-in user. The Server enforces every rule (grants, initiator, hash, duplicates); the layer only reshapes errors and never names a user."""
        t, s = self.need_session()
        if not s: return
        try: code, d = SERVER.json(method, path, s.cookie, body)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code < 400: return self.send(code, d)
        if not isinstance(d, dict) or not d.get("code"):
            if code == 404: return self.err(404, "workflows_off", off)
            return self.err(code, "server_error", "The Server refused the request (HTTP %d)." % code)
        detail = {k: d[k] for k in ("grant",) if k in d}
        self.err(code, d["code"], str(d.get("error") or d["code"]), **detail)

    # -- feedback, help, reusable questions: the Server's own routes, as the signed-in user. The Server records who; the layer only validates the shape. ----
    CATEGORIES = ("WRONG_VALUE", "WRONG_DEFINITION", "MISSING_SOURCE", "OTHER")

    def _text(self, b, key, limit, required=False):
        v = (b or {}).get(key)
        if v is None or v == "":
            if required: raise ValueError("%s is required." % key)
            return None
        if not isinstance(v, str) or len(v) > limit: raise ValueError("%s must be text of up to %d characters." % (key, limit))
        v = v.strip()
        if not v and required: raise ValueError("%s is required." % key)
        return v or None

    def _post_simple(self, path, body, bad):
        """Relay a POST whose Server answer is {success, error?}: a refusal inside a 200 is surfaced as an error, not hidden."""
        t, s = self.need_session()
        if not s: return
        try: code, d = SERVER.json("POST", path, s.cookie, body)
        except Unauthorized: return self.lost(t)
        except OSError: return self.err(502, "server_unreachable", "The OmniGate Server could not be reached.")
        if code == 404: return self.err(404, "not_available", "This Server does not offer that.")
        if code >= 400 or not isinstance(d, dict): return self.err(code if code >= 400 else 502, "server_error", (d.get("error") if isinstance(d, dict) and isinstance(d.get("error"), str) else "The Server refused the request (HTTP %d)." % code))
        if d.get("success") is False: return self.err(422, "refused", str(d.get("error") or "The Server did not accept it."))
        self.send(200, {k: d[k] for k in ("success", "alreadySaved", "cancelled") if k in d})

    QUERY_ID = re.compile(r"^[A-Za-z0-9-]{8,80}$")

    def cancel(self, body):
        """Stops a running question on the Server (POST /api/ask/cancel, as the signed-in person: the Server only cancels what that user is running). It flags the question and interrupts its running
        SQL; a model call already in flight is only noticed at the next step (Server#143). The browser's own abort does not do this, which is why a Cancel used to leave the work running."""
        try: qid = self._text(body, "queryId", 80, True)
        except ValueError as e: return self.err(400, "bad_request", str(e))
        if not self.QUERY_ID.match(qid): return self.err(400, "bad_request", "queryId is not a query id.")
        self._post_simple("/api/ask/cancel", {"queryId": qid}, None)

    def feedback(self, body):
        try:
            qid = self._text(body, "queryId", 200, True); vote = (body or {}).get("vote")
            if vote not in ("UP", "DOWN"): raise ValueError("vote must be UP or DOWN.")
            out = {"queryId": qid, "vote": vote}
            cat = (body or {}).get("category")
            if cat not in (None, ""):
                if cat not in self.CATEGORIES: raise ValueError("category must be one of %s." % ", ".join(self.CATEGORIES))
                out["category"] = cat
            for k, n in (("note", 2000), ("question", 4000), ("answer", 8000)):
                v = self._text(body, k, n)
                if v: out[k] = v
        except ValueError as e: return self.err(400, "bad_request", str(e))
        self._post_simple("/app/feedback", out, None)

    def help_request(self, body):
        try: m = self._text(body, "message", 2000, True)
        except ValueError as e: return self.err(400, "bad_request", str(e))
        self._post_simple("/app/help-request", {"message": m}, None)

    def reusable(self, body):
        try: q = self._text(body, "question", 4000, True); sql = self._text(body, "sql", 20000, True)
        except ValueError as e: return self.err(400, "bad_request", str(e))
        self._post_simple("/app/questions/save-as-reusable", {"question": q, "sql": sql}, None)

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


    # -- audit ---------------------------------------------------------------------------------------------------------------------------------------------
    DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def audit_records(self, q, download):
        """The workflow decision record with filters, or its export. Not an MCP tool on purpose: the record holds the facts each decision was made on. Every read is logged (user, route, filters) to the layer's output."""
        t, s = self.need_session()
        if not s: return
        if not audit_enabled(): return self.err(404, "audit_off", "The audit view is not set up on this deployment (AGENCY_AUDIT_FILE is unset).")
        if not audit_allowed(s.username): return self.err(403, "not_an_auditor", "Your account is not on this deployment's audit list.")
        f = {k: (q.get(k) or [""])[0].strip() for k in ("definition", "actor", "outcome", "control", "run", "since", "until")}
        if any(len(v) > 100 for v in f.values()): return self.err(400, "bad_request", "A filter is too long.")
        if f["outcome"] and f["outcome"] not in audit.OUTCOMES: return self.err(400, "bad_request", "outcome must be one of: %s." % ", ".join(audit.OUTCOMES))
        for k in ("since", "until"):
            if f[k] and not self.DATE.match(f[k]): return self.err(400, "bad_request", "%s must be a date, YYYY-MM-DD." % k)
        f = {k: v or None for k, v in f.items()}
        sys.stderr.write("AUDIT %s user=%s filters=%s\n" % ("export" if download else "view", s.username, json.dumps({k: v for k, v in f.items() if v}))); sys.stderr.flush()
        path = os.environ["AGENCY_AUDIT_FILE"].strip()
        if not os.path.exists(path):          # not damaged, and not a verified empty chain either (a deleted file must not read as "all clear"): the file has not been created yet, or is gone
            if download: return self.err(404, "no_record_yet", "There is no decision record file yet: no run has finished since it was created (or it was removed).")
            return self.send(200, {"missing": True, "chainValid": None, "firstBadEntry": None, "head": None, "total": 0, "rows": [], "definitions": [], "controls": []})
        try:
            if download: return self.send_text(200, audit.export(path, **f), "application/x-ndjson; charset=utf-8", "decision-record.jsonl")
            return self.send(200, audit.view(path, **f))
        except (OSError, ValueError, KeyError, TypeError): return self.err(502, "audit_unreadable", "The decision record could not be read or is not in the expected form.")


def main():
    load_prefs(); port = int(os.environ.get("PORT", "8097")); make_server(port).serve_forever()



TLS_CERT, TLS_KEY = os.environ.get("AGENCY_TLS_CERT", "").strip(), os.environ.get("AGENCY_TLS_KEY", "").strip()
SECURE = "; Secure" if TLS_CERT and TLS_KEY else ""                  # a session cookie travels over HTTPS only when the layer itself serves HTTPS


def make_server(port):
    """The HTTP server; with AGENCY_TLS_CERT and AGENCY_TLS_KEY set it serves HTTPS (TLS 1.2 or later). Each connection is wrapped without handshaking, so the handshake runs in that connection's
    own thread: a client that stalls in it cannot block the accept loop."""
    if not (TLS_CERT and TLS_KEY): return ThreadingHTTPServer(("0.0.0.0", port), H)
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2; ctx.load_cert_chain(TLS_CERT, TLS_KEY)

    class TlsServer(ThreadingHTTPServer):
        def get_request(self):
            sock, addr = super().get_request(); sock.settimeout(30)
            return ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr
    return TlsServer(("0.0.0.0", port), H)

if __name__ == "__main__": main()
