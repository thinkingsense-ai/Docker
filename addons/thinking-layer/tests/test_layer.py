"""python3 -m unittest discover -s addons/thinking-layer/tests   (from the repository root). A fake OmniGate Server stands in; nothing here is a measurement of the real one."""
import http.client, json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import adapters, app, decisions, tools, uploads
from upstream import Upstream

class Fake:
    namespaces = [{"id": "treasury", "name": "Treasury"}]; packs = [{"id": "bom"}]; ask_posts = []; ns_posts = []; ask_status = 200; can_upload = True

class FakeServer(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o, extra=()):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        for k, v in extra: self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def authed(self): return "omnigate_app_session=srv-cookie" in (self.headers.get("Cookie") or "")
    def csrf_ok(self): return not self.headers.get("Cookie") or bool(self.headers.get("X-Requested-With"))
    def do_GET(self):
        p = self.path
        if p == "/app/public-config": return self._j(200, {"llmConfigured": True})
        if not self.authed(): return self._j(401, {"error": "not logged in"})
        if p == "/app/whoami": return self._j(200, {"username": "alice", "canSeeSql": True, "canUploadFiles": Fake.can_upload})
        if p == "/app/namespaces": return self._j(200, {"success": True, "namespaces": Fake.namespaces})
        if p.startswith("/app/starter-questions"): return self._j(200, {"success": True, "packs": Fake.packs, "items": [{"question": "q?", "origin": "approved"}], "asked": p})
        if p == "/app/conversations": return self._j(200, {"conversations": [{"id": "c1", "title": "T", "updatedAtMillis": 1}]})
        if p.startswith("/app/conversations/get"): return self._j(200, {"success": True, "id": "c1", "turns": [], "asked": p})
        if p == "/app/workflows/definitions": return self._j(404, {})
        if p == "/app/workflows/runs/run-1": return self._j(200, {"id": "run-1"})
        return self._j(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); b = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/app/login":
            if b.get("username") == "alice" and b.get("password") == "pw": return self._j(200, {"success": True}, [("Set-Cookie", "omnigate_app_session=srv-cookie; Path=/; HttpOnly")])
            return self._j(200, {"success": False, "error": "bad credentials"})
        if not self.csrf_ok(): return self._j(403, {"error": "cross-site request refused"})
        if not self.authed(): return self._j(401, {})
        if self.path == "/app/logout": return self._j(200, {"success": True})
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
    ingests = []; fail = None
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/adapter": return self._j(200, {"id": "fake-audio", "title": "Fake", "kind": "audio", "accepts": {"extensions": [".wav"], "mime": ["audio/wav"]}, "maxBytes": 1000, "nonCommercial": True})
        self._j(404, {})
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)); FakeAdapter.ingests.append((self.headers.get("X-Filename"), len(body)))
        if FakeAdapter.fail: return self._j(FakeAdapter.fail, {"error": "bad audio"})
        self._j(200, {"result": {"top": "Cardinalis cardinalis"}, "notes": ["n"], "licence": "NC", "askPrompts": ["How many recordings of Cardinalis cardinalis?"]})

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
        Fake.can_upload = True; FakeAdapter.ingests = []; FakeAdapter.fail = None
        app.ADAPTERS = adapters.Registry("http://127.0.0.1:%d" % self.adapter.server_port); app.UPLOADS = uploads.Store(1.0)
        app.SESSIONS.clear(); os.environ.pop("AGENCY_SCOPE_HINT", None); os.environ.pop("AGENCY_DECISION_FILE", None)
        self.c = Client(self.layer.server_port)
    def signin(self):
        s, raw, r = self.c.call("POST", "/login", {"username": "alice", "password": "pw"}); self.assertEqual(s, 200, raw); return r
    def J(self, raw): return json.loads(raw)

    def test_tools_are_generated_from_the_contract_and_never_include_approval(self):
        names = [t["name"] for t in tools.tool_list()]
        self.assertEqual(names, ["list_packs", "ask", "get_decisions", "status", "list_adapters", "list_uploads"])
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
        self.signin(); d = self.J(self.c.call("GET", "/status")[1])
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
