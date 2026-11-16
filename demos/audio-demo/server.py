#!/usr/bin/env python3
"""Audio demo: drop in a bird (or fish) sound, hear it, see what BirdNET and CLAP make of it, and join the answer to the curated record.
  python3 server.py [port]        http://localhost:8090      (stdlib HTTP, no web framework; models load on the first request or at start)
Needs the POC data (../multimodal-poc: fetch_data.py, embed_audio.py) and: torch transformers birdnet soundfile scipy numpy."""
import io, json, mimetypes, os, random, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import numpy as np, soundfile as sf
import engine
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(engine.POC, "cache"); ASK = os.environ.get("ASK_URL", "http://localhost:8080")
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json", extra=None):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.send_header("Accept-Ranges", "bytes")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def file(self, path, ctype):
        if not os.path.isfile(path): return self.send(404, {"error": "not found"})
        data = open(path, "rb").read(); rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):                     # browsers seek audio with Range requests
            a, _, b = rng[6:].partition("-"); a = int(a or 0); b = int(b) if b else len(data) - 1
            return self.send(206, data[a:b + 1], ctype, {"Content-Range": "bytes %d-%d/%d" % (a, b, len(data))})
        self.send(200, data, ctype)
    def do_GET(self):
        u = urlparse(self.path); p = u.path
        try:
            if p in ("/", "/index.html"): return self.send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html; charset=utf-8")
            if p == "/api/config": return self.send(200, {"ask_url": ASK})
            if p == "/api/samples": return self.send(200, engine.sample_list())
            if p.startswith("/api/truth/"): return self.send(200, engine.truth(p.rsplit("/", 1)[1]))
            if p.startswith("/audio/"):
                rid = os.path.basename(p); ext = ".wav" if rid.startswith("fs") else ".mp3"
                return self.file(os.path.join(CACHE, "audio", rid + ext), "audio/wav" if ext == ".wav" else "audio/mpeg")
            if p.startswith("/image/"): return self.file(os.path.join(CACHE, "image", os.path.basename(p) + ".png"), "image/png")
            self.send(404, {"error": "not found"})
        except Exception as e: self.send(500, {"error": str(e)})
    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/identify": return self.send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 40_000_000: return self.send(413, {"error": "File too large (40 MB max)."})
            x, sr = sf.read(io.BytesIO(self.rfile.read(n)), dtype="float32", always_2d=True)
            x = x.mean(1)[: sr * 60]                                  # first minute at most
            self.send(200, engine.identify(x, sr, exclude=(parse_qs(u.query).get("exclude") or [None])[0]))
        except Exception as e: self.send(400, {"error": "Could not read that audio (use wav, mp3, flac or ogg): %s" % str(e)[:120]})
def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    print("loading models...", flush=True); engine.state(); print("http://localhost:%d" % port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
if __name__ == "__main__": main()
