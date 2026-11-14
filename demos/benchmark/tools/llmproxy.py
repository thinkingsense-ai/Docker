"""Logging pass-through proxy for the Anthropic Messages API. The app is pointed at it with OMNIGATE_LLM_ENDPOINT; every request body
(system prompt, messages) and reply is appended to a JSONL file. Headers (the API key) are forwarded but never logged.
  python3 llmproxy.py 9099 calls.jsonl"""
import json, sys, time, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PORT = int(sys.argv[1]); OUT = sys.argv[2]; LOCK = threading.Lock(); UP = "https://api.anthropic.com"
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        hdr = {k: v for k, v in self.headers.items() if k.lower() in ("x-api-key", "anthropic-version", "content-type", "anthropic-beta")}
        req = urllib.request.Request(UP + self.path, data=body, headers=hdr, method="POST")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as r: code, data = r.status, r.read()
        except urllib.error.HTTPError as e: code, data = e.code, e.read()
        except Exception as e: code, data = 502, json.dumps({"error": str(e)}).encode()
        try: rq = json.loads(body)
        except Exception: rq = {"raw": body[:2000].decode("utf8", "replace")}
        try: rs = json.loads(data)
        except Exception: rs = {"raw": data[:2000].decode("utf8", "replace")}
        with LOCK, open(OUT, "a") as f:
            f.write(json.dumps({"t": time.time(), "secs": round(time.time() - t0, 2), "status": code, "request": rq, "response": rs}) + "\n")
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *a): pass
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
