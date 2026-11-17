"""A stand-in for the customer's ERP write API (Fusion REST, SAP OData or the ServiceNow Table API in real life). It only records what it is asked and honours the Idempotency-Key header
(a repeated key returns the first answer and writes nothing: control 7). GET /calls lists every call."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
CALLS, SEEN = [], {}
class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._send(200, CALLS) if self.path == "/calls" else self._send(404, {"error": "not found"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"); key = self.headers.get("Idempotency-Key", "")
        if key in SEEN: return self._send(200, dict(SEEN[key], replayed=True))
        resp = {"ok": True, "path": self.path, "erp_reference": "ERP-%04d" % (len(CALLS) + 1), "applied": body}
        CALLS.append({"path": self.path, "idempotency_key": key, "body": body}); SEEN[key] = resp; self._send(200, resp)
    def log_message(self, *a): pass
if __name__ == "__main__": ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8086), H).serve_forever()
