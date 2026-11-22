"""The OmniGate Server as seen from the layer: its business-user login, session cookie, Workspace selection and streaming /api/ask. The Server's cookie stays here, never in the browser."""
import json, urllib.request, urllib.error
COOKIE = "omnigate_app_session"

class Unauthorized(Exception): pass

class Upstream:
    def __init__(self, base, timeout=300): self.base, self.timeout = base.rstrip("/"), timeout

    def _open(self, method, path, cookie=None, body=None, accept=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "omnigate"}     # the Server refuses a cookie-carrying POST without it (its CSRF guard)
        if cookie: h["Cookie"] = "%s=%s" % (COOKIE, cookie)
        if accept: h["Accept"] = accept
        req = urllib.request.Request(self.base + path, None if body is None else json.dumps(body).encode(), h, method=method)
        try: return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e: return e

    def json(self, method, path, cookie=None, body=None):
        r = self._open(method, path, cookie, body)
        if r.status == 401: raise Unauthorized()
        try: return r.status, json.loads(r.read() or b"{}")
        except ValueError: return r.status, {}

    def login(self, username, password):
        r = self._open("POST", "/app/login", None, {"username": username, "password": password})
        data = json.loads(r.read() or b"{}"); cookie = None
        for c in r.headers.get_all("Set-Cookie") or []:
            if c.startswith(COOKIE + "="): cookie = c.split("=", 1)[1].split(";", 1)[0]
        return (bool(data.get("success")) and cookie is not None), cookie, data

    def _no_redirect(self, path, headers):
        """One GET that is NOT followed: the single sign-on steps answer with a redirect whose Location and Set-Cookie are exactly what the layer needs."""
        class Stop(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        req = urllib.request.Request(self.base + path, None, headers, method="GET")
        try: r = urllib.request.build_opener(Stop).open(req, timeout=30)
        except urllib.error.HTTPError as e: r = e
        return r.status, r.headers.get("Location"), {c.split("=", 1)[0]: c.split("=", 1)[1].split(";", 1)[0] for c in (r.headers.get_all("Set-Cookie") or []) if "=" in c}

    def sso_start(self, host, proto):
        """The Server's /app/oidc/login, asked as if the browser had come to `host`: its redirect_uri is built from the Host header, so the provider returns to the layer."""
        return self._no_redirect("/app/oidc/login", {"Host": host, "X-Forwarded-Proto": proto})

    def sso_finish(self, host, proto, query, state_cookie):
        return self._no_redirect("/app/oidc/callback?" + query, {"Host": host, "X-Forwarded-Proto": proto, "Cookie": "omnigate_app_oidc_state=" + state_cookie})

    def ask_events(self, cookie, body):
        """Yields each parsed SSE event of POST /api/ask."""
        r = self._open("POST", "/api/ask", cookie, body, "text/event-stream")
        if r.status == 401: raise Unauthorized()
        buf = ""
        while True:
            chunk = r.read1(4096) if hasattr(r, "read1") else r.read(4096)
            if chunk: buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                for line in frame.split("\n"):
                    if line.startswith("data: "):
                        try: yield json.loads(line[6:])
                        except ValueError: pass
            if not chunk: break
        for line in buf.split("\n"):
            if line.startswith("data: "):
                try: yield json.loads(line[6:])
                except ValueError: pass
