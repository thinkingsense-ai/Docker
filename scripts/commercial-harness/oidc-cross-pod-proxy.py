#!/usr/bin/env python3
"""A tiny local reverse proxy that makes the OIDC cross-replica test deterministic.

Why it exists: `kubectl port-forward` to a Service pins you to ONE pod, and the load balancer spreads
connections unpredictably (a browser's keep-alive connection can carry both the login start and the
callback to the same pod). Either way a single browser session can pass the test without ever crossing
replicas. This proxy sends the login START to one pod and the provider's CALLBACK to a different pod,
so a login only succeeds if any replica can finish a login another replica started
(thinkingsense-ai/Server#12, fixed in v0.10.4).

The browser talks to http://localhost:<listen> the whole time, so the Host header, the cookies and the
redirect URI the app builds are all `localhost:<listen>`, which is what the identity provider has
registered. Every routing decision is printed.

  oidc-cross-pod-proxy.py --listen 8080 --login 127.0.0.1:18081 --callback 127.0.0.1:18082
"""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGIN_PATHS = ("/auth/oidc/login", "/app/oidc/login")
CALLBACK_PATHS = ("/auth/oidc/callback", "/app/oidc/callback")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
              "transfer-encoding", "upgrade"}


def make_handler(login_upstream, callback_upstream):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def route(self):
            path = self.path.split("?", 1)[0]
            if path in CALLBACK_PATHS:
                return "callback", callback_upstream
            if path in LOGIN_PATHS:
                return "login", login_upstream
            return "other", login_upstream

        def handle_any(self):
            kind, upstream = self.route()
            if kind != "other":
                print(f"{self.command} {self.path.split('?', 1)[0]:<24} -> {kind} pod {upstream}", flush=True)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            host, port = upstream.split(":")
            conn = http.client.HTTPConnection(host, int(port), timeout=60)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True
            conn.close()

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = handle_any

    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=8080)
    ap.add_argument("--login", default="127.0.0.1:18081", help="host:port of the pod that starts logins")
    ap.add_argument("--callback", default="127.0.0.1:18082", help="host:port of the pod that finishes them")
    a = ap.parse_args()
    print(f"proxy on http://localhost:{a.listen}  login -> {a.login}  callback -> {a.callback}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.listen), make_handler(a.login, a.callback)).serve_forever()
