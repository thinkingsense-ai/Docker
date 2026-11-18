"""python3 -m unittest discover -s addons/thinking-layer/tests   (from the repository root). A fake OmniGate Server stands in; nothing here is a measurement of the real one."""
import http.client, json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import adapters, app, decisions, tools, uploads
from upstream import Upstream

class Fake:
    simple_posts = []; simple_refuse = None
    namespaces = [{"id": "treasury", "name": "Treasury"}]; packs = [{"id": "bom"}]; ask_posts = []; ns_posts = []; ask_status = 200; can_upload = True; user_ns = {}; wf_off = False; wf_refuse = None; wf_posts = []; decisions_route = False; edition = None; starters_need_default = False; starter_calls = 0

class FakeServer(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o, extra=()):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        for k, v in extra: self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    COOKIES = {"srv-cookie": "alice", "srv-bob": "bob", "srv-carol": "carol"}
    def user(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "omnigate_app_session": return self.COOKIES.get(v)
    def authed(self): return self.user() is not None
    def csrf_ok(self): return not self.headers.get("Cookie") or bool(self.headers.get("X-Requested-With"))
    def do_GET(self):
        p = self.path
        if p == "/app/public-config": return self._j(200, {"llmConfigured": True})
        if not self.authed(): return self._j(401, {"error": "not logged in"})
        if p == "/app/whoami": return self._j(200, dict({"username": self.user(), "canSeeSql": True, "canUploadFiles": Fake.can_upload}, **({"edition": Fake.edition, "features": {"workflows": not Fake.wf_off}} if Fake.edition else {})))
        if p == "/app/namespaces": return self._j(200, {"success": True, "namespaces": Fake.user_ns.get(self.user(), Fake.namespaces)})
        if p.startswith("/app/starter-questions"):
            Fake.starter_calls += 1; gone = Fake.starters_need_default and Fake.ns_posts and Fake.ns_posts[-1] is not None        # app 0.10.21: nothing once a Workspace is selected
            return self._j(200, {"success": True, "packs": Fake.packs, "items": [] if gone else [{"question": "q?", "origin": "approved"}], "asked": p})
        if p == "/app/conversations": return self._j(200, {"conversations": [{"id": "c1", "title": "T", "updatedAtMillis": 1}]})
        if p.startswith("/app/conversations/get"): return self._j(200, {"success": True, "id": "c1", "turns": [], "asked": p})
        if p.startswith("/app/workflows/") and Fake.wf_off: return self._j(404, {})
        if p == "/app/workflows/definitions": return self._j(200, {"definitions": [{"id": "payment-exception", "title": "Payment exception", "keyField": "payment_id", "requiredApprovals": 2}]})
        if p == "/app/workflows/queue": return self._j(200, {"runs": [{"id": "run-1", "stage": "awaiting_approval"}], "count": 1})
        if p == "/app/workflows/runs/run-1": return self._j(200, {"run": {"id": "run-1", "stage": "awaiting_approval", "payloadHash": "ab" * 32, "you": {"canApprove": True, "reason": None}}})
        if p.startswith("/app/workflows/runs/") and p.endswith("/decisions") and Fake.decisions_route:
            rid = p.split("/")[4]
            if rid != "run-1": return self._j(404, {"success": False, "error": "No such run", "code": "unknown_run"})
            return self._j(200, Fake.decisions_body)
        if p.startswith("/app/workflows/runs/") and p.endswith("/decisions"): return self._j(404, {})           # an older Server: no such route
        if p.startswith("/app/workflows/runs/"): return self._j(404, {"success": False, "error": "No such run", "code": "unknown_run"})
        return self._j(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); b = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/app/login":
            ck = {"alice": "srv-cookie", "bob": "srv-bob", "carol": "srv-carol"}.get(b.get("username"))
            if ck and b.get("password") == "pw": return self._j(200, {"success": True}, [("Set-Cookie", "omnigate_app_session=%s; Path=/; HttpOnly" % ck)])
            return self._j(200, {"success": False, "error": "bad credentials"})
        if not self.csrf_ok(): return self._j(403, {"error": "cross-site request refused"})
        if not self.authed(): return self._j(401, {})
        if self.path == "/app/logout": return self._j(200, {"success": True})
        if self.path.startswith("/app/workflows/"):
            if Fake.wf_off: return self._j(404, {})
            Fake.wf_posts.append((self.path, b, self.user()))
            if Fake.wf_refuse: st, code, extra = Fake.wf_refuse; return self._j(st, dict({"success": False, "error": "refused: " + code, "code": code}, **extra))
            return self._j(201 if self.path.endswith("/start") else 200, {"created": True, "run": {"id": "run-1", "stage": "facts"}})
        if self.path in ("/app/feedback", "/app/help-request", "/app/questions/save-as-reusable"):
            Fake.simple_posts.append((self.path, b, self.user()))
            if Fake.simple_refuse: return self._j(200, {"success": False, "error": Fake.simple_refuse})
            return self._j(200, {"success": True, "alreadySaved": False} if "reusable" in self.path else {"success": True})
        if self.path == "/app/session/namespace": Fake.ns_posts.append(b["namespaceId"]); return self._j(200, {"success": True})
        if self.path == "/api/ask":
            if Fake.ask_status != 200: return self._j(Fake.ask_status, {})
            Fake.ask_posts.append(b); self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for e in ({"step": "understanding", "conversationId": "c1"}, {"step": "sql", "sql": "SELECT 1", "model": "m"}, {"step": "planned", "backends": ["pg"], "source": "question_bank"},
                      {"step": "check", "id": "write_safety", "status": "pass"}, {"step": "done", "answer": "one", "columns": ["x"], "rows": [["1"]], "sql": "SELECT 1", "conversationId": "c1"}):
                self.wfile.write(b"data: " + json.dumps(e).encode() + b"\n\n"); self.wfile.flush()
            return
        self._j(404, {})

class FakeAdapter(BaseHTTPRequestHandler):
    ingests = []; fail = None; gps = False
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/adapter": return self._j(200, {"id": "fake-audio", "title": "Fake", "kind": "audio", "accepts": {"extensions": [".wav"], "mime": ["audio/wav"]}, "maxBytes": 1000, "nonCommercial": True})
        self._j(404, {})
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)); FakeAdapter.ingests.append((self.headers.get("X-Filename"), len(body)))
        if FakeAdapter.fail: return self._j(FakeAdapter.fail, {"error": "bad audio"})
        self._j(200, {"result": {"top": "Cardinalis cardinalis", **({"gps": {"lat": 1, "lon": 2}} if FakeAdapter.gps else {})}, "notes": ["n"] + (["The file carries a GPS location (1, 2)."] if FakeAdapter.gps else []), "licence": "NC", "askPrompts": ["How many recordings of Cardinalis cardinalis?"]})

def serve(handler):
    s = ThreadingHTTPServer(("127.0.0.1", 0), handler); threading.Thread(target=s.serve_forever, daemon=True).start(); return s

class Client:
    def __init__(self, port): self.port, self.cookie = port, None
    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); h = dict(headers or {})
        if method in ("POST", "DELETE"): h.setdefault("X-Requested-With", "test")
        if self.cookie: h["Cookie"] = self.cookie
        if body is not None: h["Content-Type"] = "application/json"
        if isinstance(body, bytes): h["Content-Type"] = (headers or {}).get("Content-Type", "audio/wav")
        c.request(method, path, body if isinstance(body, bytes) else (json.dumps(body) if body is not None else None), h); r = c.getresponse(); raw = r.read().decode()
        sc = r.getheader("Set-Cookie")
        if sc and sc.startswith("agency_session=") and "Max-Age=0" not in sc: self.cookie = sc.split(";")[0]
        return r.status, raw, r

class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = serve(FakeServer); cls.adapter = serve(FakeAdapter); cls.layer = serve(app.H); app.SERVER = Upstream("http://127.0.0.1:%d" % cls.fake.server_port)
    @classmethod
    def tearDownClass(cls): cls.fake.shutdown(); cls.adapter.shutdown(); cls.layer.shutdown()
    def setUp(self):
        Fake.namespaces = [{"id": "treasury", "name": "Treasury"}]; Fake.packs = [{"id": "bom"}]; Fake.ask_posts = []; Fake.ns_posts = []; Fake.ask_status = 200
        Fake.can_upload = True; Fake.user_ns = {}; Fake.wf_off = False; Fake.wf_refuse = None; Fake.wf_posts = []; Fake.decisions_route = False; Fake.edition = None; Fake.starters_need_default = False; Fake.starter_calls = 0; os.environ.pop("AGENCY_UPLOAD_SHARING", None); os.environ.pop("AGENCY_UPLOAD_ADMINS", None); FakeAdapter.ingests = []; FakeAdapter.fail = None
        app.ADAPTERS = adapters.Registry("http://127.0.0.1:%d" % self.adapter.server_port); app.UPLOADS = uploads.Store(1.0)
        app.SESSIONS.clear(); os.environ.pop("AGENCY_SCOPE_HINT", None); os.environ.pop("AGENCY_DECISION_FILE", None)
        self.c = Client(self.layer.server_port)
    def signin(self):
        s, raw, r = self.c.call("POST", "/login", {"username": "alice", "password": "pw"}); self.assertEqual(s, 200, raw); return r
    def J(self, raw): return json.loads(raw)

    def test_tools_are_generated_from_the_contract_and_never_include_approval(self):
        names = [t["name"] for t in tools.tool_list()]
        self.assertEqual(names, ["list_packs", "ask", "get_decisions", "status", "list_adapters", "list_uploads", "list_workflow_definitions", "list_workflows", "get_workflow_run"])
        self.assertFalse([n for n in names if "approve" in n or "reject" in n])
        s, raw, _ = self.c.call("GET", "/tools"); self.assertEqual([t["name"] for t in self.J(raw)["tools"]], names)

    def test_packs_without_sign_in_have_unknown_load_state(self):
        s, raw, _ = self.c.call("GET", "/packs"); d = self.J(raw)
        self.assertEqual(s, 200); self.assertEqual(len(d["packs"]), 7); self.assertTrue(all(p["loaded"] is None for p in d["packs"]))

    def test_bad_login_is_refused_and_good_login_hides_the_server_cookie(self):
        s, raw, _ = self.c.call("POST", "/login", {"username": "alice", "password": "no"}); self.assertEqual(s, 401)
        r = self.signin(); sc = r.getheader("Set-Cookie")
        self.assertIn("HttpOnly", sc); self.assertIn("SameSite=Strict", sc); self.assertNotIn("srv-cookie", sc)

    def test_packs_show_workspace_category_and_unknown(self):
        self.signin(); d = {p["id"]: p["loaded"] for p in self.J(self.c.call("GET", "/packs")[1])["packs"]}
        self.assertEqual((d["treasury"], d["bom"], d["it-risk"]), ("workspace", "category", None))

    def test_ask_in_a_pack_with_a_workspace(self):
        self.signin(); s, raw, _ = self.c.call("POST", "/ask", {"question": "cash?", "workspaceId": "treasury"}); d = self.J(raw)
        self.assertEqual(s, 200, raw); self.assertEqual(Fake.ns_posts, ["treasury"]); self.assertEqual(d["answer"], "one")
        e = d["evidence"]; self.assertEqual((e["workspace"], e["pack"], e["scopeEnforcedBy"], e["origin"]), ("treasury", "treasury", "server-backends", "question_bank"))
        self.assertEqual(e["sources"], [{"id": "pg"}]); self.assertEqual(e["sql"], "SELECT 1"); self.assertEqual(e["checks"], [{"id": "write_safety", "status": "pass"}])
        self.assertTrue(any("schemas" in w for w in e["warnings"]))
        self.assertEqual(Fake.ask_posts[0]["question"], "cash?")

    def test_the_workspace_is_only_set_when_it_changes(self):
        self.signin()
        for _ in range(2): self.c.call("POST", "/ask", {"question": "q", "workspaceId": "treasury"})
        self.c.call("POST", "/ask", {"question": "q"})
        self.assertEqual(Fake.ns_posts, ["treasury", None])

    def test_all_data_and_a_pack_without_a_workspace(self):
        self.signin(); e = self.J(self.c.call("POST", "/ask", {"question": "q"})[1])["evidence"]; self.assertEqual((e["workspace"], e["scopeEnforcedBy"]), ("all", "none"))
        e = self.J(self.c.call("POST", "/ask", {"question": "q", "workspaceId": "bom"})[1])["evidence"]
        self.assertEqual(e["scopeEnforcedBy"], "none"); self.assertTrue(any("No Workspace is configured" in w for w in e["warnings"])); self.assertEqual(Fake.ask_posts[-1]["question"], "q")

    def test_scope_hint_is_opt_in_and_says_so(self):
        os.environ["AGENCY_SCOPE_HINT"] = "on"; self.signin()
        e = self.J(self.c.call("POST", "/ask", {"question": "q", "workspaceId": "bom"})[1])["evidence"]
        self.assertEqual(e["scopeEnforcedBy"], "agency-hint"); self.assertIn("pg.bom", Fake.ask_posts[-1]["question"])

    def test_a_cookie_post_without_the_csrf_header_is_refused(self):
        self.signin(); s, raw, _ = self.c.call("POST", "/ask", {"question": "q"}, {"X-Requested-With": ""})
        self.assertEqual((s, self.J(raw)["error"]["code"]), (403, "cross_site_refused"))

    def test_ask_input_errors(self):
        s, raw, _ = self.c.call("POST", "/ask", {"question": "q"}); self.assertEqual(s, 401)
        self.signin()
        self.assertEqual(self.c.call("POST", "/ask", {"question": " "})[0], 400)
        self.assertEqual(self.c.call("POST", "/ask", {"question": "q", "workspaceId": "nope"})[0], 404)
        self.assertEqual(self.c.call("POST", "/ask", {"question": "x" * 4001})[0], 400)

    def test_streaming_relays_events_and_puts_evidence_before_done(self):
        self.signin(); s, raw, _ = self.c.call("POST", "/ask", {"question": "q", "workspaceId": "treasury"}, {"Accept": "text/event-stream"})
        steps = [json.loads(l[6:])["step"] for l in raw.split("\n") if l.startswith("data: ")]
        self.assertEqual(steps, ["understanding", "sql", "planned", "check", "evidence", "done"])

    def test_a_server_401_ends_the_layer_session(self):
        self.signin(); Fake.ask_status = 401
        s, raw, _ = self.c.call("POST", "/ask", {"question": "q"}); self.assertEqual((s, self.J(raw)["error"]["code"]), (401, "server_session_ended"))
        self.assertEqual(self.c.call("GET", "/whoami")[0], 401)

    def test_status_reports_workflows_unavailable_on_the_free_edition(self):
        Fake.wf_off = True; self.signin(); d = self.J(self.c.call("GET", "/status")[1])
        self.assertTrue(d["server"]["reachable"]); self.assertFalse(d["workflows"]["available"]); self.assertIn("404", d["workflows"]["note"])

    def _decision_file(self, tamper=False):
        es, prev = [], ""
        for i, (run, typ) in enumerate([("run-1", "started"), ("run-2", "started"), ("run-1", "approved")], 1):
            e = {"seq": i, "prevHash": prev, "ts": "2026-11-17T00:00:0%dZ" % i, "runId": run, "type": typ, "actor": "alice", "details": {"b": "2", "a": "1"}}
            e["hash"] = decisions.entry_hash(e); prev = e["hash"]; es.append(e)
        if tamper: es[1]["details"]["a"] = "x"
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False); f.write("\n".join(json.dumps(e) for e in es)); f.close(); return f.name

    def test_decisions(self):
        self.signin(); self.assertEqual(self.c.call("GET", "/decisions?runId=run-1")[0], 501)
        os.environ["AGENCY_DECISION_FILE"] = self._decision_file()
        d = self.J(self.c.call("GET", "/decisions?runId=run-1")[1]); self.assertTrue(d["chainValid"]); self.assertEqual([e["seq"] for e in d["entries"]], [1, 3]); self.assertEqual(d["totalEntries"], 3)
        self.assertEqual(self.c.call("GET", "/decisions?runId=run-9")[0], 404)       # the Server does not show this user that run
        self.assertEqual(self.c.call("GET", "/decisions")[0], 400)
        os.environ["AGENCY_DECISION_FILE"] = self._decision_file(tamper=True)
        d = self.J(self.c.call("GET", "/decisions?runId=run-1")[1]); self.assertFalse(d["chainValid"]); self.assertEqual(d["firstBadSeq"], 2)

    def _server_entries(self, tamper=False):
        es = []; prev = ""
        for i, typ in enumerate(("start", "recommendation", "approval"), 1):
            e = {"seq": i * 2, "ts": "2026-11-18T00:00:0%dZ" % i, "runId": "run-1", "type": typ, "actor": "alice", "details": {"b": "2", "a": "1"}, "prevHash": prev}
            e["hash"] = decisions.entry_hash(e); prev = e["hash"]; es.append(e)
        if tamper: es[1]["details"]["a"] = "edited"
        Fake.decisions_body = {"runId": "run-1", "entries": es, "count": len(es), "chainValid": True, "chainBrokenAtSeq": None}

    def test_the_decision_record_comes_from_the_server_when_it_serves_it(self):
        Fake.decisions_route = True; self._server_entries(); self.signin()
        d = self.J(self.c.call("GET", "/decisions?runId=run-1")[1])
        self.assertEqual((d["source"], d["chainValid"], d["entriesVerified"], d["count"], d["totalEntries"]), ("server", True, True, 3, None))
        self.assertEqual(self.c.call("GET", "/decisions?runId=run-9")[0], 404); self.assertEqual(self.c.call("GET", "/decisions?runId=../x")[0], 404)
        self._server_entries(tamper=True); d = self.J(self.c.call("GET", "/decisions?runId=run-1")[1])
        self.assertFalse(d["entriesVerified"]); self.assertTrue(d["chainValid"])                                # the layer recomputed the hashes itself; the chain verdict stays the Server's

    def test_an_older_server_falls_back_to_the_shared_file_and_says_so(self):
        self.signin(); os.environ["AGENCY_DECISION_FILE"] = self._decision_file()
        d = self.J(self.c.call("GET", "/decisions?runId=run-1")[1]); self.assertEqual((d["source"], d["entriesVerified"], d["count"]), ("file", True, 2))
        del os.environ["AGENCY_DECISION_FILE"]; s, raw, _ = self.c.call("GET", "/decisions?runId=run-1"); self.assertEqual((s, self.J(raw)["error"]["code"]), (501, "decisions_unavailable")); self.assertIn("0.10.20", self.J(raw)["error"]["message"])

    def test_status_takes_the_edition_and_workflow_availability_from_whoami_when_the_server_reports_them(self):
        Fake.edition = "commercial"; self.signin(); d = self.J(self.c.call("GET", "/status")[1])
        self.assertEqual((d["edition"], d["workflows"]["available"], d["decisions"]), ("commercial", True, {"readable": True, "via": "server"}))
        Fake.edition = "free"; Fake.wf_off = True; d = self.J(self.c.call("GET", "/status")[1]); self.assertEqual((d["edition"], d["workflows"]["available"], d["decisions"]["readable"]), ("free", False, False))
        Fake.edition = None; Fake.wf_off = False; d = self.J(self.c.call("GET", "/status")[1]); self.assertNotIn("edition", d); self.assertTrue(d["workflows"]["available"])           # an older Server: probed

    def settle(self):
        import time as _t
        for _ in range(100):
            if all(s.starters for s in app.SESSIONS.values()): return
            _t.sleep(0.02)

    def test_starters_survive_the_server_going_empty_once_a_workspace_is_selected(self):
        Fake.starters_need_default = True; self.signin(); self.settle()
        s, raw, _ = self.c.call("GET", "/starters"); self.assertEqual(len(self.J(raw)["items"]), 1)
        self.c.call("POST", "/ask", {"question": "q", "workspaceId": None}); self.c.call("POST", "/ask", {"question": "q", "workspaceId": "treasury"}); self.assertEqual(Fake.ns_posts[-1], "treasury")      # a Workspace is now selected on the Server
        for path in ("/starters", "/starters?pack=bom"):
            d = self.J(self.c.call("GET", path)[1]); self.assertEqual((len(d["items"]), d.get("cached")), (1, True), path)                    # the Server would answer nothing; the layer kept the first answer

    def test_the_kept_starters_expire_and_stale_ones_still_beat_nothing(self):
        Fake.starters_need_default = True; self.signin(); self.settle(); self.c.call("POST", "/ask", {"question": "q", "workspaceId": "treasury"})
        for sess in app.SESSIONS.values(): sess.starters = {k: (v[0] - app.STARTER_TTL - 1, v[1]) for k, v in sess.starters.items()}
        d = self.J(self.c.call("GET", "/starters")[1]); self.assertEqual((len(d["items"]), d.get("stale")), (1, True))              # expired, the Server gives nothing, so the old answer is served and marked stale
        Fake.starters_need_default = False; d = self.J(self.c.call("GET", "/starters")[1]); self.assertFalse(d.get("stale")); self.assertEqual(len(d["items"]), 1)         # a live answer replaces it

    def test_kept_starters_are_per_person_and_an_unknown_pack_is_still_refused(self):
        self.signin(); self.settle(); other = self.who("bob"); import time as _t; _t.sleep(0.2)
        for k in (self.c, other): self.assertEqual(len(self.J(k.call("GET", "/starters")[1])["items"]), 1)
        sessions = list(app.SESSIONS.values()); self.assertEqual(len(sessions), 2); self.assertIsNot(sessions[0].starters, sessions[1].starters)
        self.assertEqual(self.c.call("GET", "/starters?pack=nope")[0], 404); self.assertEqual(Client(self.layer.server_port).call("GET", "/starters")[0], 401)

    def test_starters_conversations_pass_through_and_need_sign_in(self):
        for path in ("/starters", "/conversations", "/conversations/get?id=c1", "/preferences"): self.assertEqual(self.c.call("GET", path)[0], 401, path)
        self.signin()
        d = self.J(self.c.call("GET", "/starters?pack=treasury")[1]); self.assertEqual(d["items"][0]["origin"], "approved"); self.assertIn("pack=treasury", d["asked"])
        self.assertEqual(self.c.call("GET", "/starters?pack=nope")[0], 404)                  # only catalogue ids are forwarded
        self.assertEqual(self.J(self.c.call("GET", "/conversations")[1])["conversations"][0]["id"], "c1")
        d = self.J(self.c.call("GET", "/conversations/get?id=c%2F1%26x")[1]); self.assertIn("id=c%2F1%26x", d["asked"])     # the id is encoded, not spliced into the Server path

    def test_preferences_are_per_user_validated_and_persisted(self):
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False); f.close(); os.unlink(f.name)
        os.environ["AGENCY_PREFS_FILE"] = f.name; app.PREFS.clear(); self.addCleanup(os.environ.pop, "AGENCY_PREFS_FILE", None)
        self.signin(); self.assertEqual(self.J(self.c.call("GET", "/preferences")[1]), {})
        self.assertEqual(self.J(self.c.call("POST", "/preferences", {"pack": "treasury"})[1]), {"pack": "treasury"})
        self.assertEqual(json.load(open(f.name)), {"alice": {"pack": "treasury"}})
        self.assertEqual(self.c.call("POST", "/preferences", {"theme": "x"})[0], 400)        # unknown key
        self.assertEqual(self.c.call("POST", "/preferences", {"pack": "x" * 81})[0], 400)    # too long
        self.assertEqual(self.J(self.c.call("POST", "/preferences", {"pack": None})[1]), {})
        app.PREFS.clear(); app.load_prefs(); self.assertEqual(app.PREFS["alice"], {})

    def test_all_data_uses_the_all_data_workspace_when_it_exists(self):
        self.signin(); Fake.namespaces = [{"id": "treasury"}, {"id": "all-data"}]
        d = self.J(self.c.call("POST", "/ask", {"question": "q", "workspaceId": None})[1])
        self.assertEqual(Fake.ns_posts[-1], "all-data"); self.assertEqual(d["evidence"]["workspace"], "all-data"); self.assertEqual(d["evidence"]["scopeEnforcedBy"], "none")
        Fake.namespaces = [{"id": "treasury"}]; self.c.call("POST", "/ask", {"question": "q", "workspaceId": None}); self.assertIsNone(Fake.ns_posts[-1])   # no such Workspace: the default

    def up(self, name="clip.wav", body=b"RIFFxxxx", **kw): return self.c.call("POST", "/uploads?name=%s&workspaceId=sounds" % name, body, kw.get("headers"))

    def test_adapters_list_and_unreachable_adapter_is_disabled(self):
        self.assertEqual(self.c.call("GET", "/adapters")[0], 401); self.signin()
        d = self.J(self.c.call("GET", "/adapters")[1]); self.assertEqual(d["accept"], [".wav"]); self.assertTrue(d["adapters"][0]["nonCommercial"])
        app.ADAPTERS = adapters.Registry("http://127.0.0.1:1"); d = self.J(self.c.call("GET", "/adapters")[1])
        self.assertFalse(d["adapters"][0]["enabled"]); self.assertEqual(d["accept"], [])

    def test_upload_ingests_keeps_no_file_and_is_private_to_the_owner(self):
        self.assertEqual(self.up()[0], 401); self.signin()
        s, raw, _ = self.up(); r = self.J(raw); self.assertEqual(s, 200, raw)
        self.assertEqual((r["kind"], r["adapter"], r["workspaceId"], r["nonCommercial"]), ("audio", "fake-audio", "sounds", True)); self.assertNotIn("owner", r)
        self.assertEqual(FakeAdapter.ingests, [("clip.wav", 8)])
        self.assertEqual(self.J(self.c.call("GET", "/uploads")[1])["uploads"][0]["id"], r["id"]); self.assertEqual(self.c.call("GET", "/uploads/" + r["id"])[0], 200)
        self.assertNotIn(b"RIFF", json.dumps(app.UPLOADS.rows).encode())                 # only the derived record is held
        app.UPLOADS.rows[r["id"]]["owner"] = "bob"                                           # someone else's record looks like a missing one
        self.assertEqual(self.c.call("GET", "/uploads/" + r["id"])[0], 404); self.assertEqual(self.c.call("DELETE", "/uploads/" + r["id"])[0], 404)
        app.UPLOADS.rows[r["id"]]["owner"] = "alice"; self.assertEqual(self.c.call("DELETE", "/uploads/" + r["id"])[0], 200); self.assertEqual(self.c.call("GET", "/uploads/" + r["id"])[0], 404)

    def test_upload_refusals_happen_before_the_body_is_read(self):
        self.signin()
        s, raw, _ = self.up("doc.pdf", headers={"Content-Type": "application/pdf"}); self.assertEqual(s, 415); self.assertEqual(self.J(raw)["error"]["detail"]["accepted"], [".wav"])
        self.assertEqual(self.up(body=b"x" * 1001)[0], 413); self.assertEqual(FakeAdapter.ingests, [])
        Fake.can_upload = False; s, raw, _ = self.up(); self.assertEqual((s, self.J(raw)["error"]["code"]), (403, "missing_grant")); self.assertEqual(FakeAdapter.ingests, [])
        Fake.can_upload = True; FakeAdapter.fail = 422; s, raw, _ = self.up(); self.assertEqual((s, self.J(raw)["error"]["message"]), (422, "bad audio"))
        self.assertEqual(self.J(self.c.call("GET", "/uploads")[1])["uploads"], [])        # a refused file leaves no record

    def test_upload_limits_and_expiry(self):
        self.signin()
        for _ in range(uploads.MAX_PER_USER): self.assertEqual(self.up()[0], 200)
        self.assertEqual(self.up()[0], 429)
        for r in app.UPLOADS.rows.values(): r["expiresAtEpoch"] = 0
        self.assertEqual(self.J(self.c.call("GET", "/uploads")[1])["uploads"], [])

    def who(self, name):
        c = Client(self.layer.server_port); s, raw, _ = c.call("POST", "/login", {"username": name, "password": "pw"}); self.assertEqual(s, 200, raw); return c

    def gps_upload(self, c, wid="treasury"):
        FakeAdapter.gps = True; r = self.J(c.call("POST", "/uploads?name=clip.wav&workspaceId=%s" % wid, b"RIFFxxxx")[1]); FakeAdapter.gps = False; return r["id"]

    def test_sharing_is_off_by_default_and_records_stay_private(self):
        a, b = self.who("alice"), self.who("bob"); rid = self.gps_upload(a)
        s, raw, _ = a.call("POST", "/uploads/%s/share" % rid, {"shared": True}); self.assertEqual((s, self.J(raw)["error"]["code"]), (409, "sharing_off"))
        d = self.J(b.call("GET", "/uploads")[1]); self.assertEqual((d["sharing"], d["shared"], d["uploads"]), ("off", [], []))
        self.assertEqual(self.J(a.call("GET", "/adapters")[1])["sharing"], "off")

    def test_shared_record_is_read_only_redacted_and_limited_to_the_workspace(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; Fake.user_ns = {"alice": [{"id": "treasury"}], "bob": [{"id": "treasury"}], "carol": [{"id": "bom"}]}
        a, b, c = self.who("alice"), self.who("bob"), self.who("carol"); rid = self.gps_upload(a)
        self.assertEqual(self.J(b.call("GET", "/uploads")[1])["shared"], [])                         # private until shared
        s, raw, _ = a.call("POST", "/uploads/%s/share" % rid, {"shared": True}); r = self.J(raw); self.assertEqual(s, 200, raw)
        self.assertTrue(r["shared"] and r["mine"] and r["sharedBy"] == "alice" and r["sharedAt"]); self.assertIn("gps", r["result"])               # the owner still sees the location
        d = self.J(b.call("GET", "/uploads")[1]); self.assertEqual([x["id"] for x in d["shared"]], [rid]); v = d["shared"][0]
        self.assertEqual((v["mine"], v["sharedBy"], v["workspaceId"]), (False, "alice", "treasury")); self.assertNotIn("gps", v["result"]); self.assertFalse(any("GPS" in n for n in v["notes"]))
        self.assertEqual(self.c.call("GET", "/uploads")[0], 401); self.assertEqual(self.J(c.call("GET", "/uploads")[1])["shared"], [])        # carol cannot use Treasury
        self.assertEqual(c.call("GET", "/uploads/" + rid)[0], 404); self.assertEqual(b.call("GET", "/uploads/" + rid)[0], 200)
        self.assertEqual(b.call("DELETE", "/uploads/" + rid)[0], 404); self.assertEqual(b.call("POST", "/uploads/%s/share" % rid, {"shared": False})[0], 404)   # read-only to them
        a.call("POST", "/uploads/%s/share" % rid, {"shared": False}); self.assertEqual(self.J(b.call("GET", "/uploads")[1])["shared"], []); self.assertEqual(b.call("GET", "/uploads/" + rid)[0], 404)

    def test_losing_the_workspace_or_turning_sharing_off_hides_it_again(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; Fake.user_ns = {"alice": [{"id": "treasury"}], "bob": [{"id": "treasury"}]}
        a, b = self.who("alice"), self.who("bob"); rid = self.gps_upload(a); a.call("POST", "/uploads/%s/share" % rid, {"shared": True})
        Fake.user_ns["bob"] = [{"id": "bom"}]; self.assertEqual(self.J(b.call("GET", "/uploads")[1])["shared"], [])               # the Server's rule changed
        Fake.user_ns["bob"] = [{"id": "treasury"}]; self.assertEqual(len(self.J(b.call("GET", "/uploads")[1])["shared"]), 1)
        os.environ["AGENCY_UPLOAD_SHARING"] = "off"; self.assertEqual(self.J(b.call("GET", "/uploads")[1])["shared"], [])

    def test_sharing_never_widens_access(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; Fake.user_ns = {"alice": [{"id": "bom"}]}
        a = self.who("alice"); rid = self.gps_upload(a, "treasury")                                  # uploaded into a Workspace she cannot use
        s, raw, _ = a.call("POST", "/uploads/%s/share" % rid, {"shared": True}); self.assertEqual((s, self.J(raw)["error"]["code"]), (403, "workspace_not_yours"))
        rid2 = self.J(a.call("POST", "/uploads?name=x.wav", b"RIFFxxxx")[1])["id"]                    # no Workspace given and no all-data Workspace: nothing to share into
        s, raw, _ = a.call("POST", "/uploads/%s/share" % rid2, {"shared": True}); self.assertEqual((s, self.J(raw)["error"]["code"]), (400, "no_workspace"))
        self.assertEqual(a.call("POST", "/uploads/%s/share" % rid, {"shared": "yes"})[0], 400)
        Fake.can_upload = False; self.assertEqual(self.who("bob").call("POST", "/uploads?name=x.wav&workspaceId=treasury", b"RIFFxxxx")[0], 403)      # sharing does not grant uploads

    def test_upload_without_a_workspace_goes_to_all_data_when_there_is_one(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; Fake.user_ns = {"alice": [{"id": "all-data"}]}
        a = self.who("alice"); r = self.J(a.call("POST", "/uploads?name=x.wav", b"RIFFxxxx")[1]); self.assertEqual(r["workspaceId"], "all-data")

    def test_upload_admins_can_unshare_and_delete_shared_records_but_not_read_private_ones(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; os.environ["AGENCY_UPLOAD_ADMINS"] = "carol"; Fake.user_ns = {"alice": [{"id": "treasury"}], "carol": [{"id": "bom"}]}
        a, c = self.who("alice"), self.who("carol"); private, shared = self.gps_upload(a), self.gps_upload(a); a.call("POST", "/uploads/%s/share" % shared, {"shared": True})
        d = self.J(c.call("GET", "/uploads")[1]); self.assertEqual([x["id"] for x in d["shared"]], [shared]); self.assertEqual(c.call("GET", "/uploads/" + private)[0], 404)
        self.assertEqual(c.call("DELETE", "/uploads/" + private)[0], 404); self.assertEqual(c.call("POST", "/uploads/%s/share" % private, {"shared": False})[0], 404)
        self.assertEqual(c.call("POST", "/uploads/%s/share" % shared, {"shared": True})[0], 404)           # an admin cannot share on someone's behalf
        self.assertEqual(c.call("POST", "/uploads/%s/share" % shared, {"shared": False})[0], 200); self.assertFalse(self.J(a.call("GET", "/uploads/" + shared)[1])["shared"])
        a.call("POST", "/uploads/%s/share" % shared, {"shared": True}); self.assertEqual(c.call("DELETE", "/uploads/" + shared)[0], 200); self.assertEqual(a.call("GET", "/uploads/" + shared)[0], 404)

    def test_sharing_does_not_extend_expiry_and_expired_records_vanish(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; Fake.user_ns = {"alice": [{"id": "treasury"}], "bob": [{"id": "treasury"}]}
        a, b = self.who("alice"), self.who("bob"); rid = self.gps_upload(a); before = app.UPLOADS.rows[rid]["expiresAtEpoch"]
        a.call("POST", "/uploads/%s/share" % rid, {"shared": True}); self.assertEqual(app.UPLOADS.rows[rid]["expiresAtEpoch"], before)
        app.UPLOADS.rows[rid]["expiresAtEpoch"] = 0; self.assertEqual(self.J(b.call("GET", "/uploads")[1])["shared"], [])

    def test_feedback_help_and_reusable_are_validated_and_relayed_as_the_signed_in_user(self):
        Fake.simple_posts.clear(); Fake.simple_refuse = None
        self.assertEqual(self.c.call("POST", "/feedback", {"queryId": "q1", "vote": "UP"})[0], 401); self.signin()
        s, raw, _ = self.c.call("POST", "/feedback", {"queryId": "q1", "vote": "DOWN", "category": "WRONG_VALUE", "note": " off by ten ", "question": "How many?", "answer": "5", "user": "mallory", "userId": "x"}); self.assertEqual(s, 200, raw)
        self.assertEqual(Fake.simple_posts[-1], ("/app/feedback", {"queryId": "q1", "vote": "DOWN", "category": "WRONG_VALUE", "note": "off by ten", "question": "How many?", "answer": "5"}, "alice"))
        for b in ({}, {"queryId": "q1"}, {"queryId": "q1", "vote": "MAYBE"}, {"queryId": "q1", "vote": "UP", "category": "RUDE"}, {"queryId": "q1", "vote": "UP", "note": "x" * 2001}, {"queryId": ["q"], "vote": "UP"}):
            self.assertEqual(self.c.call("POST", "/feedback", b)[0], 400, b)
        self.assertEqual(self.c.call("POST", "/help", {"message": "  I need the Q3 table  ", "who": "x"})[0], 200); self.assertEqual(Fake.simple_posts[-1], ("/app/help-request", {"message": "I need the Q3 table"}, "alice"))
        for b in ({}, {"message": "  "}, {"message": "x" * 2001}): self.assertEqual(self.c.call("POST", "/help", b)[0], 400)
        s, raw, _ = self.c.call("POST", "/reusable", {"question": "Top suppliers?", "sql": "SELECT 1", "approved": True}); self.assertEqual(s, 200); self.assertEqual(self.J(raw), {"success": True, "alreadySaved": False})
        self.assertEqual(Fake.simple_posts[-1], ("/app/questions/save-as-reusable", {"question": "Top suppliers?", "sql": "SELECT 1"}, "alice"))
        self.assertEqual(self.c.call("POST", "/reusable", {"question": "q"})[0], 400)
        Fake.simple_refuse = "You are not allowed to save questions."; s, raw, _ = self.c.call("POST", "/reusable", {"question": "q", "sql": "s"}); self.assertEqual(s, 422); self.assertIn("not allowed", self.J(raw)["error"]["message"]); Fake.simple_refuse = None

    def test_workflow_routes_relay_as_the_signed_in_user_and_only_the_allowed_fields(self):
        self.assertEqual(self.c.call("GET", "/workflows/queue")[0], 401); self.signin()
        d = self.J(self.c.call("GET", "/workflows/definitions")[1]); self.assertEqual(d["definitions"][0]["keyField"], "payment_id")
        self.assertEqual(self.J(self.c.call("GET", "/workflows/queue")[1])["count"], 1)
        self.assertEqual(self.J(self.c.call("GET", "/workflows/run-1")[1])["run"]["stage"], "awaiting_approval")
        s, raw, _ = self.c.call("POST", "/workflows/start", {"definition": "payment-exception", "key": 35, "user": "mallory", "initiator": "x"}); self.assertEqual(s, 201, raw)
        self.assertEqual(Fake.wf_posts[-1], ("/app/workflows/start", {"definition": "payment-exception", "key": "35"}, "alice"))      # no field that names a user goes upstream
        self.c.call("POST", "/workflows/run-1/approve", {"payloadHash": "ab" * 32, "user": "mallory"}); self.assertEqual(Fake.wf_posts[-1], ("/app/workflows/runs/run-1/approve", {"payloadHash": "ab" * 32}, "alice"))
        self.c.call("POST", "/workflows/run-1/reject", {"reason": "  not verified  "}); self.assertEqual(Fake.wf_posts[-1], ("/app/workflows/runs/run-1/reject", {"reason": "not verified"}, "alice"))

    def test_workflow_input_is_checked_before_anything_is_sent(self):
        self.signin()
        for path, body in (("/workflows/start", {}), ("/workflows/start", {"definition": "d"}), ("/workflows/start", {"definition": "d", "key": ""}), ("/workflows/start", {"definition": ["d"], "key": "1"}),
                           ("/workflows/run-1/approve", {}), ("/workflows/run-1/approve", {"payloadHash": "not hex!"}), ("/workflows/run-1/approve", {"payloadHash": "ab"}),
                           ("/workflows/run-1/reject", {}), ("/workflows/run-1/reject", {"reason": "   "}), ("/workflows/run-1/reject", {"reason": "x" * 1001})):
            self.assertEqual(self.c.call("POST", path, body)[0], 400, (path, body))
        self.assertEqual(Fake.wf_posts, [])
        for bad in ("../x", "a/b", "run 1", "x" * 81): self.assertEqual(self.c.call("GET", "/workflows/" + bad.replace(" ", "%20"))[0], 404)
        self.assertEqual(self.c.call("POST", "/workflows/run-1/delete", {})[0], 404)

    def test_server_refusals_keep_their_codes_and_status(self):
        self.signin()
        for st, code, extra in ((403, "missing_grant", {"grant": "canApprove"}), (403, "initiator_cannot_approve", {}), (403, "non_human_identity", {}), (403, "already_approved", {}),
                                (409, "payload_hash_mismatch", {}), (409, "not_awaiting_approval", {}), (502, "engine_unavailable", {})):
            Fake.wf_refuse = (st, code, extra); s, raw, _ = self.c.call("POST", "/workflows/run-1/approve", {"payloadHash": "ab" * 32}); e = self.J(raw)["error"]
            self.assertEqual((s, e["code"]), (st, code)); self.assertIn(code, e["message"])
            if extra: self.assertEqual(e["detail"], extra)

    def test_workflows_off_is_a_clear_404_and_a_lost_server_session_signs_out(self):
        self.signin(); Fake.wf_off = True
        for m, p, b in (("GET", "/workflows/definitions", None), ("GET", "/workflows/queue", None), ("POST", "/workflows/start", {"definition": "d", "key": "1"})):
            s, raw, _ = self.c.call(m, p, b); self.assertEqual((s, self.J(raw)["error"]["code"]), (404, "workflows_off"))
        Fake.wf_off = False; app.SESSIONS[next(iter(app.SESSIONS))].cookie = "gone"
        self.assertEqual(self.c.call("GET", "/workflows/queue")[0], 401)

    def test_approving_and_starting_are_never_tools(self):
        ops = {o["name"]: o for o in tools.load_contract()["operations"]}
        for n in ("approve_workflow", "reject_workflow", "start_workflow"): self.assertTrue(ops[n]["implemented"] and not ops[n]["tool"], n)
        names = [t["name"] for t in tools.tool_list()]; self.assertFalse([n for n in names if "approve" in n or "reject" in n or "start" in n])

    def test_workflow_posts_need_the_csrf_header(self):
        self.signin(); c = http.client.HTTPConnection("127.0.0.1", self.layer.server_port)
        c.request("POST", "/workflows/run-1/approve", json.dumps({"payloadHash": "ab" * 32}), {"Cookie": self.c.cookie, "Content-Type": "application/json"}); self.assertEqual(c.getresponse().status, 403); self.assertEqual(Fake.wf_posts, [])

    def test_share_needs_the_csrf_header(self):
        os.environ["AGENCY_UPLOAD_SHARING"] = "workspace"; self.signin(); rid = self.J(self.up()[1])["id"]
        c = http.client.HTTPConnection("127.0.0.1", self.layer.server_port); c.request("POST", "/uploads/%s/share" % rid, b"{}", {"Cookie": self.c.cookie}); self.assertEqual(c.getresponse().status, 403)

    def test_delete_needs_the_csrf_header(self):
        self.signin(); rid = self.J(self.up()[1])["id"]
        c = http.client.HTTPConnection("127.0.0.1", self.layer.server_port); c.request("DELETE", "/uploads/" + rid, headers={"Cookie": self.c.cookie}); self.assertEqual(c.getresponse().status, 403)

    def test_static_ui_is_served_with_spa_fallback_and_no_path_escape(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/assets"); open(d + "/index.html", "w").write("<html>agency</html>"); open(d + "/assets/a.js", "w").write("x=1")
        with open(os.path.join(os.path.dirname(d), "secret.txt"), "w") as sf: sf.write("secret"); app.WEB_DIST = d; self.addCleanup(setattr, app, "WEB_DIST", "/nonexistent")
        s, raw, r = self.c.call("GET", "/"); self.assertEqual((s, raw), (200, "<html>agency</html>")); self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertEqual(self.c.call("GET", "/assets/a.js")[1], "x=1")
        self.assertEqual(self.c.call("GET", "/some/deep/link")[1], "<html>agency</html>")      # unknown path -> the page
        s, raw, _ = self.c.call("GET", "/..%2Fsecret.txt"); self.assertNotIn("secret", raw)
        s, raw, _ = self.c.call("GET", "/app/whoami"); self.assertEqual(s, 404)                 # never the page for Server-owned prefixes
        self.assertEqual(self.c.call("GET", "/health")[0], 200)                                 # API routes win over the page

if __name__ == "__main__": unittest.main()
