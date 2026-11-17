"""Document adapter service: GET /adapter, GET /health, POST /ingest (raw body, X-Filename). pypdf for PDF, standard library otherwise. Nothing is stored."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import adapter, docs


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/adapter": return self.send(200, adapter.MANIFEST)
        if self.path == "/health": return self.send(200, {"ok": True})
        self.send(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/ingest": return self.send(404, {"error": "Not found."})
        name = self.headers.get("X-Filename", "")
        if not adapter.accepts(name, self.headers.get("Content-Type")): return self.send(415, {"error": "Not a document type this adapter reads (pdf, docx, md, txt)."})
        n = int(self.headers.get("Content-Length") or 0)
        if n > adapter.MAX_BYTES: return self.send(413, {"error": "File too large (25 MB max)."})
        data = self.rfile.read(n)
        try: self.send(200, adapter.record(data, name))
        except docs.DocError as e: self.send(422, {"error": str(e)})
        except Exception: self.send(422, {"error": "That file could not be read as a document."})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8092), H).serve_forever()
