"""python3 -m unittest discover -s demos/benchmark/local-models/tests   (no network, no cloud, no docker)"""
import hashlib, http.server, json, os, sys, tempfile, threading, unittest, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch, oci_node, report, serve

DATA = b"gguf-bytes-" * 5000
SHA = hashlib.sha256(DATA).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    seen = []
    def do_GET(self):
        Handler.seen.append(dict(self.headers))
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0]); body = DATA[start:]
            self.send_response(206); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(200); self.send_header("Content-Length", str(len(DATA))); self.end_headers(); self.wfile.write(DATA)
    def log_message(self, *a): pass


def entry(sha=SHA):
    return {"repo": "org/m", "revision": "a" * 40, "base": "org/base", "licence": "apache-2.0", "files": {"main": {"name": "m.gguf", "sha256": sha, "approx_gb": 0.01}}}


class Manifest(unittest.TestCase):
    def test_every_shipped_model_is_safe_to_download(self):
        for mid, e in fetch.load_models().items(): fetch.check_entry(mid, e)

    def test_every_shipped_model_has_a_known_licence_family(self):
        for mid, e in fetch.load_models().items(): self.assertEqual(e["licence"], "apache-2.0", mid)    # a change here must be a deliberate, reviewed one

    def test_refusals(self):
        for bad, why in ((dict(entry(), licence=""), "licence"), (dict(entry(), revision="main"), "revision"), (entry(sha="abc"), "SHA")):
            with self.assertRaises(fetch.FetchError, msg=why): fetch.check_entry("x", bad)
        e = entry(); e["files"]["main"]["name"] = "../evil"
        with self.assertRaises(fetch.FetchError): fetch.check_entry("x", e)


class Download(unittest.TestCase):
    def setUp(self):
        Handler.seen.clear()
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        os.environ["HF_ENDPOINT"] = f"http://127.0.0.1:{self.srv.server_port}"; self.dir = tempfile.mkdtemp()
    def tearDown(self): self.srv.shutdown(); os.environ.pop("HF_ENDPOINT", None)

    def test_good_download_is_verified_and_a_second_run_does_nothing(self):
        msgs = []; fetch.fetch("m", entry(), self.dir, log=msgs.append)
        self.assertEqual(open(os.path.join(self.dir, "m.gguf"), "rb").read(), DATA)
        n = len(Handler.seen); fetch.fetch("m", entry(), self.dir, log=msgs.append)
        self.assertEqual(len(Handler.seen), n); self.assertTrue(any("already present" in m for m in msgs))

    def test_wrong_hash_is_deleted_and_refused(self):
        with self.assertRaises(fetch.FetchError): fetch.fetch("m", entry(sha="0" * 64), self.dir, log=lambda m: None)
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_tampered_file_on_disk_is_replaced_not_reused(self):
        open(os.path.join(self.dir, "m.gguf"), "wb").write(b"tampered"); fetch.fetch("m", entry(), self.dir, log=lambda m: None)
        self.assertEqual(open(os.path.join(self.dir, "m.gguf"), "rb").read(), DATA)

    def test_resume_from_a_part_file(self):
        open(os.path.join(self.dir, "m.gguf.part"), "wb").write(DATA[:1000]); fetch.fetch("m", entry(), self.dir, log=lambda m: None)
        self.assertTrue(any(h.get("Range") == "bytes=1000-" for h in Handler.seen)); self.assertEqual(open(os.path.join(self.dir, "m.gguf"), "rb").read(), DATA)

    def test_vision_file_only_when_asked(self):
        e = entry(); e["files"]["mmproj"] = {"name": "p.gguf", "sha256": SHA}
        fetch.fetch("m", e, self.dir, log=lambda m: None); self.assertEqual(os.listdir(self.dir), ["m.gguf"])
        fetch.fetch("m", e, self.dir, want_mmproj=True, log=lambda m: None); self.assertIn("p.gguf", os.listdir(self.dir))

    def test_token_is_not_forwarded_to_another_host(self):
        h = fetch._KeepTokenOnlyOnHF(); req = urllib.request.Request("https://huggingface.co/x", headers={"Authorization": "Bearer t"})
        new = h.redirect_request(req, None, 302, "Found", {}, "https://cdn.example.com/y")
        self.assertIsNone(new.get_header("Authorization")); self.assertEqual(new.full_url, "https://cdn.example.com/y")


class Serve(unittest.TestCase):
    def setUp(self):
        self.models = fetch.load_models(); self.shapes = serve.load("shapes.json")
    def cmd(self, mid, sid, **kw):
        return serve.build_command(self.models[mid], self.shapes["shapes"][sid], self.shapes, 8091, "/m", **kw)

    def test_cpu_docker(self):
        c = self.cmd("qwen3-4b-q4km", "x86-cpu-16"); s = " ".join(c)
        self.assertEqual(c[:3], ["docker", "run", "-d"]); self.assertIn("ghcr.io/ggml-org/llama.cpp:server ", s + " "); self.assertNotIn("--gpus", c)
        self.assertEqual(c[c.index("-ngl") + 1], "0"); self.assertEqual(c[c.index("--flash-attn") + 1], "off"); self.assertIn("/models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf", c)

    def test_gpu_docker(self):
        c = self.cmd("gemma4-26b-a4b-q4", "a10-2")
        self.assertIn("--gpus", c); self.assertIn("server-cuda", " ".join(c)); self.assertEqual(c[c.index("-ngl") + 1], "99"); self.assertEqual(c[c.index("--flash-attn") + 1], "on")
        self.assertEqual(c[c.index("--split-mode") + 1], "layer")

    def test_vision_flag_only_where_a_projector_exists(self):
        self.assertIn("--mmproj", self.cmd("gemma4-e4b-q4", "a10-1", vision=True)); self.assertNotIn("--mmproj", self.cmd("gemma4-e4b-q4", "a10-1"))
        self.assertNotIn("--mmproj", self.cmd("qwen3-4b-q4km", "a10-1", vision=True))

    def test_native_uses_host_paths(self):
        c = self.cmd("qwen3-4b-q4km", "x86-cpu-16", engine="native"); self.assertEqual(c[0], "llama-server"); self.assertIn("/m/Qwen3-4B-Instruct-2507-Q4_K_M.gguf", c)

    def test_context_is_large_enough_for_the_app(self):
        for mid, e in self.models.items(): self.assertGreaterEqual(e["context"], 4096, mid)       # the app's catalog plus history exceeds the 2048 default


class Report(unittest.TestCase):
    def runs(self, spec):
        """spec: list of runs, each a list of (question, confidence, correct)."""
        return [([{"question": q, "confidence": c, "secs": 10.0, "calls": [0, 0]} for q, c, _ in run], [{"question": q, "verdict": "correct" if ok else "wrong"} for q, _, ok in run]) for run in spec]

    def test_summary(self):
        r = self.runs([[("a", 90, True), ("b", 50, False)], [("a", 90, True), ("b", 50, True)]]); s = report.summarize(r)
        self.assertEqual((s["runs"], s["scores"], s["mean"], s["secs_median"]), (2, [1, 2], 1.5, 10.0))

    def test_tokens_from_both_reply_styles(self):
        calls = [{"response": {"usage": {"prompt_tokens": 100, "completion_tokens": 7}}}, {"response": {"usage": {"input_tokens": 50, "output_tokens": 3}}}]
        self.assertEqual(report.tokens_per_question([{"calls": [0, 2]}], calls), [(150, 10)])

    def test_calibration_finds_the_lowest_good_threshold(self):
        # local is right when confident (>=70) and wrong when not; the frontier is right on everything
        spec = [[("q%d" % i, 90 if i < 6 else 30, i < 6) for i in range(10)]]
        res = report.calibrate(report.rows_from(self.runs(spec)), {"q%d" % i: 1.0 for i in range(10)}, n_runs=1, tolerance=0)
        self.assertEqual(res["frontier_alone"], 10.0); self.assertEqual(res["lowest_good_t"], 35)
        at = {x["t"]: x for x in res["table"]}; self.assertEqual(at[35]["kept_share"], 0.6); self.assertEqual(at[35]["kept_accuracy"], 1.0); self.assertEqual(at[35]["blended"], 10.0)
        self.assertLess(at[0]["blended"], 10.0)            # keeping everything locally loses the four wrong ones

    def test_no_threshold_is_good_enough_when_confidence_is_uninformative(self):
        spec = [[("q%d" % i, 90, i % 2 == 0) for i in range(10)]]
        res = report.calibrate(report.rows_from(self.runs(spec)), {"q%d" % i: 1.0 for i in range(10)}, n_runs=1, tolerance=0)
        self.assertEqual(res["lowest_good_t"], 95)         # only by escalating everything (nothing is >= 95): the honest answer, not a lucky one

    def test_missing_confidence_counts_as_low(self):
        rows = report.rows_from(self.runs([[("a", None, True)]])); self.assertIsNone(rows[0]["conf"])
        self.assertEqual(report.calibrate(rows, {"a": 1.0}, thresholds=[10])["table"][0]["kept_share"], 0.0)


class Proxy(unittest.TestCase):
    def test_health_probe_and_posts_pass_through_and_only_posts_are_logged(self):
        """The app probes a remote llama-server with GET /health at boot; a proxy that answers only POST makes it look absent (found live)."""
        import socket, subprocess, time
        class Up(http.server.BaseHTTPRequestHandler):
            def do_GET(self): self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
            def do_POST(self): self.rfile.read(int(self.headers.get("Content-Length", 0))); b = b'{"usage":{"prompt_tokens":1,"completion_tokens":2}}'; self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def log_message(self, *a): pass
        up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Up); threading.Thread(target=up.serve_forever, daemon=True).start()
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        out = os.path.join(tempfile.mkdtemp(), "calls.jsonl")
        p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "llmproxy.py"), str(port), out],
                             env={**os.environ, "LLM_UPSTREAM": f"http://127.0.0.1:{up.server_port}"})
        try:
            for _ in range(50):
                try: r = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2); break
                except Exception: time.sleep(0.2)
            self.assertEqual((r.status, r.read()), (200, b"ok"))
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", b'{"messages":[]}', {"Content-Type": "application/json"}), timeout=5).read()
            lines = open(out).read().strip().splitlines(); self.assertEqual(len(lines), 1); self.assertEqual(json.loads(lines[0])["response"]["usage"]["completion_tokens"], 2)
        finally: p.kill(); up.shutdown()


class Oci(unittest.TestCase):
    ENV = {"OCI_COMPARTMENT_ID": "c", "OCI_SUBNET_ID": "s", "OCI_IMAGE_ID": "i", "OCI_AD": "ad", "SSH_PUBKEY_FILE": "/k.pub"}

    def test_flex_shape_gets_a_shape_config_and_tags(self):
        c = oci_node.launch_command("x86-cpu-16", self.ENV, 4, now=1000)
        cfg = json.loads(c[c.index("--shape-config") + 1]); self.assertEqual((cfg["ocpus"], cfg["memoryInGBs"]), (16, 128))
        tags = json.loads(c[c.index("--freeform-tags") + 1]); self.assertEqual(tags, {"harness": "local-models", "expires": str(1000 + 4 * 3600)})

    def test_fixed_gpu_shape_has_no_shape_config(self):
        self.assertNotIn("--shape-config", oci_node.launch_command("a10-1", self.ENV, 2, now=1))

    def test_guards(self):
        for ttl in (0, 25, -1):
            with self.assertRaises(SystemExit): oci_node.launch_command("a10-1", self.ENV, ttl)
        with self.assertRaises(SystemExit): oci_node.launch_command("a10-1", {}, 4)
        with self.assertRaises(SystemExit): oci_node.launch_command("local-docker", self.ENV, 4)

    def test_reap_only_touches_expired_nodes_that_are_ours(self):
        inst = [{"id": "ours-old", "freeform-tags": {"harness": "local-models", "expires": "100"}, "lifecycle-state": "RUNNING"},
                {"id": "ours-new", "freeform-tags": {"harness": "local-models", "expires": "9999"}, "lifecycle-state": "RUNNING"},
                {"id": "ours-bad", "freeform-tags": {"harness": "local-models", "expires": "soon"}, "lifecycle-state": "RUNNING"},
                {"id": "ours-gone", "freeform-tags": {"harness": "local-models", "expires": "100"}, "lifecycle-state": "TERMINATED"},
                {"id": "other", "freeform-tags": {"harness": "something-else", "expires": "100"}, "lifecycle-state": "RUNNING"},
                {"id": "untagged", "lifecycle-state": "RUNNING"}]
        self.assertEqual([i["id"] for i in oci_node.expired(inst, now=500)], ["ours-old"])

class ExtraArgsTest(unittest.TestCase):
    def test_gemma_runs_with_reasoning_off(self):
        import json, os, serve
        models = json.load(open(os.path.join(os.path.dirname(serve.__file__), "models.json")))["models"]
        shape = json.load(open(os.path.join(os.path.dirname(serve.__file__), "shapes.json")))["shapes"]["x86-cpu-16"]
        for m in ("gemma4-e4b-q4", "gemma4-26b-a4b-q4"):
            a = serve.server_args(models[m], shape, 8091, "/models/x.gguf")
            self.assertEqual(a[a.index("--reasoning") + 1], "off")
        self.assertNotIn("--reasoning", serve.server_args(models["qwen3-4b-q4km"], shape, 8091, "/models/x.gguf"))


if __name__ == "__main__":
    unittest.main()
