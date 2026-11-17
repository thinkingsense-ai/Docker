"""python3 -m unittest discover -s addons/thinking-layer/tests   (from the repository root). A fake OmniGate Server stands in; nothing here is a measurement of the real one."""
import http.client, json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import app, decisions, tools
from upstream import Upstream

class Fake:
    namespaces = [{"id": "treasury", "name": "Treasury"}]; packs = [{"id": "bom"}]; ask_posts = []; ns_posts = []; ask_status = 200

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
        if p == "/app/whoami": return self._j(200, {"username": "alice", "canSeeSql": True})
        if p == "/app/namespaces": return self._j(200, {"success": True, "namespaces": Fake.namespaces})
        if p == "/app/starter-questions": return self._j(200, {"success": True, "packs": Fake.packs})
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

def serve(handler):
    s = ThreadingHTTPServer(("127.0.0.1", 0), handler); threading.Thread(target=s.serve_forever, daemon=True).start(); return s

class Client:
    def __init__(self, port): self.port, self.cookie = port, None
    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); h = dict(headers or {})
        if method == "POST": h.setdefault("X-Requested-With", "test")
        if self.cookie: h["Cookie"] = self.cookie
        if body is not None: h["Content-Type"] = "application/json"
        c.request(method, path, json.dumps(body) if body is not None else None, h); r = c.getresponse(); raw = r.read().decode()
        sc = r.getheader("Set-Cookie")
        if sc and sc.startswith("agency_session=") and "Max-Age=0" not in sc: self.cookie = sc.split(";")[0]
        return r.status, raw, r

class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = serve(FakeServer); cls.layer = serve(app.H); app.SERVER = Upstream("http://127.0.0.1:%d" % cls.fake.server_port)
    @classmethod
    def tearDownClass(cls): cls.fake.shutdown(); cls.layer.shutdown()
    def setUp(self):
        Fake.namespaces = [{"id": "treasury", "name": "Treasury"}]; Fake.packs = [{"id": "bom"}]; Fake.ask_posts = []; Fake.ns_posts = []; Fake.ask_status = 200
        app.SESSIONS.clear(); os.environ.pop("AGENCY_SCOPE_HINT", None); os.environ.pop("AGENCY_DECISION_FILE", None)
        self.c = Client(self.layer.server_port)
    def signin(self):
        s, raw, r = self.c.call("POST", "/login", {"username": "alice", "password": "pw"}); self.assertEqual(s, 200, raw); return r
    def J(self, raw): return json.loads(raw)

    def test_tools_are_generated_from_the_contract_and_never_include_approval(self):
        names = [t["name"] for t in tools.tool_list()]
        self.assertEqual(names, ["list_packs", "ask", "get_decisions", "status"])
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

if __name__ == "__main__": unittest.main()
