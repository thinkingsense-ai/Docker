"""python3 agency/chart/tests/test_bootstrap.py   (from the repository root; needs helm, skipped without it). Renders the bootstrap Job's ConfigMap from the AKS chart and runs its
script against a stub Server: Workspaces are loaded only when the Server has none, grants go only to logins the Server knows, and a refused admin login changes nothing."""
import http.server, json, os, re, shutil, subprocess, sys, tempfile, threading, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D
CHART = os.path.join(ROOT, D.CHARTS["azure"]); HAVE = shutil.which("helm") is not None

def render(*sets):
    a = ["helm", "template", "rel", CHART, "--set", D.USERS, "--set", "agency.enabled=true", "--show-only", "templates/agency-bootstrap.yaml"] + [x for s in sets for x in ("--set", s)]
    return subprocess.run(a, capture_output=True, text=True)

def files(out):                    # the ConfigMap's keys -> text (each value is a block indented by four spaces)
    m = re.search(r"^data:\n(.*?)^---", out[out.index("kind: ConfigMap"):], re.S | re.M)
    res, key = {}, None
    for line in m.group(1).split("\n"):
        k = re.match(r"^  (\S+): \|$", line)
        if k: key = k.group(1); res[key] = []
        elif key is not None: res[key].append(line[4:] if line.startswith("    ") else line)
    return {k: "\n".join(v) for k, v in res.items()}

class Stub(http.server.BaseHTTPRequestHandler):
    log, groups, users, login_ok = [], [], ["alice", "bob"], True
    def _send(self, code, body=""):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body.encode())
    def _body(self): return self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
    def do_GET(self):
        Stub.log.append(("GET", self.path))
        if self.path == "/api/deployment-readiness": return self._send(200, "{}")
        if self.path == "/api/groups": return self._send(200, json.dumps({"groups": Stub.groups}))
        if self.path == "/api/app-user-access": return self._send(200, json.dumps({"users": [{"username": u} for u in Stub.users]}))
        self._send(404)
    def do_POST(self):
        b = self._body(); Stub.log.append(("POST", self.path, b))
        if self.path == "/admin/login": return self._send(200 if Stub.login_ok else 401)
        self._send(200, "{}")
    def do_PUT(self):
        b = self._body(); Stub.log.append(("PUT", self.path, b)); self._send(200, "{}")
    def log_message(self, *a): pass

@unittest.skipUnless(HAVE, "helm is not installed")
class Bootstrap(unittest.TestCase):
    def run_script(self, grants=None, groups=(), token="T", login_ok=True):
        out = render("demoDatasets={agency-risk}").stdout
        f = files(out)
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        open(os.path.join(d, "groups.yaml"), "w").write(f["groups.yaml"]); open(os.path.join(d, "grants.json"), "w").write(json.dumps(grants or []))
        open(os.path.join(d, "bootstrap.py"), "w").write(f["bootstrap.py"])
        Stub.log, Stub.groups, Stub.login_ok = [], list(groups), login_ok
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub); threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(srv.shutdown)
        env = dict(os.environ, APP_URL="http://127.0.0.1:%d" % srv.server_port, BOOTSTRAP_DIR=d, ADMIN_TOKEN=token, ADMIN_USER="admin", ADMIN_PASSWORD="x", WAIT_TRIES="2", WAIT_SECONDS="0.1")
        r = subprocess.run([sys.executable, os.path.join(d, "bootstrap.py")], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr); return r.stdout
    def test_workspaces_loaded_when_none_exist_and_grants_only_for_known_logins(self):
        g = [{"username": "alice", "canUploadFiles": True, "canStartWorkflows": True}, {"username": "nobody", "canApprove": True}]
        out = self.run_script(grants=g)
        puts = [e for e in Stub.log if e[0] == "PUT"]; self.assertEqual(len(puts), 1)
        yaml_text = json.loads(puts[0][2])["yaml"]; self.assertIn("id: all-data", yaml_text); self.assertIn("id: it-risk", yaml_text); self.assertIn('["mdb","pg"]', yaml_text)
        posts = [json.loads(e[2]) for e in Stub.log if e[0] == "POST" and e[1] == "/api/app-user-access/update"]
        self.assertEqual([p["username"] for p in posts], ["alice"]); self.assertTrue(posts[0]["canUploadFiles"]); self.assertFalse(posts[0]["canApprove"])
        self.assertIn("nobody: no such login, skipped", out)
    def test_existing_workspaces_are_never_overwritten(self):
        out = self.run_script(groups=[{"id": "ours-already"}])
        self.assertEqual([e for e in Stub.log if e[0] == "PUT"], []); self.assertIn("already has 1 Workspace", out)
    def test_a_refused_admin_login_changes_nothing(self):
        out = self.run_script(token="", login_ok=False)
        self.assertEqual([e for e in Stub.log if e[0] in ("PUT",) or (e[0] == "POST" and e[1] != "/admin/login")], []); self.assertIn("admin login refused", out)
    def test_no_job_without_agency_or_for_a_single_data_set(self):
        self.assertNotEqual(render("demoDatasets={agency-risk}", "agency.bootstrap.enabled=false").returncode, 0)    # nothing rendered: helm cannot find the template
        self.assertNotEqual(render("demoDataset=treasury").returncode, 0)

if __name__ == "__main__": unittest.main()
