"""Adapter registry (docs/agency-spec.md section 4). Adapters are separate services named in AGENCY_ADAPTERS (comma-separated base URLs). Request bodies never
name an adapter URL, so a caller cannot make the layer fetch an address of their choosing. An adapter exposes GET /adapter (manifest) and POST /ingest (raw file body,
X-Filename header) and answers {result, notes, licence, askPrompts}."""
import json, os, time, urllib.request, urllib.error

MANIFEST_TTL = 30


class AdapterError(Exception):
    def __init__(self, status, message): super().__init__(message); self.status, self.message = status, message


class Registry:
    def __init__(self, urls=None, timeout=300):
        raw = os.environ.get("AGENCY_ADAPTERS", "") if urls is None else urls
        self.urls = [u.strip().rstrip("/") for u in (raw.split(",") if isinstance(raw, str) else raw) if u.strip()]
        self.timeout, self._cache = timeout, {}

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as r: return json.loads(r.read())

    def manifests(self):
        """[{...manifest, enabled, url-free}] for every configured adapter; an unreachable one is listed disabled with the reason."""
        out = []
        for u in self.urls:
            hit = self._cache.get(u)
            if hit and time.time() - hit[0] < MANIFEST_TTL: out.append(hit[1]); continue
            try: m = dict(self._get(u + "/adapter"), enabled=True)
            except (OSError, ValueError) as e: m = {"id": u.split("//")[-1], "title": u, "enabled": False, "reason": "Not reachable: %s" % type(e).__name__, "accepts": {"extensions": [], "mime": []}}
            self._cache[u] = (time.time(), m); out.append(m)
        return out

    def _url_for(self, manifest_id):
        for u in self.urls:
            hit = self._cache.get(u)
            if hit and hit[1].get("id") == manifest_id: return u
        return None

    def find(self, name, mime):
        """The enabled adapter that accepts this file, as (manifest, url), or (None, None)."""
        self.manifests()
        n = (name or "").lower(); mt = (mime or "").split(";")[0].strip().lower()
        for u in self.urls:
            m = self._cache[u][1]
            if m.get("enabled") and (any(n.endswith(e) for e in m["accepts"]["extensions"]) or mt in m["accepts"]["mime"]): return m, u
        return None, None

    def ingest(self, url, name, mime, data):
        req = urllib.request.Request(url + "/ingest", data, {"Content-Type": mime or "application/octet-stream", "X-Filename": name}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try: msg = json.loads(e.read()).get("error")
            except ValueError: msg = None
            raise AdapterError(e.code if e.code in (413, 415, 422) else 502, msg or "The adapter refused the file.")
        except (OSError, ValueError): raise AdapterError(502, "The adapter could not be reached.")

    def accept_list(self):
        exts = sorted({e for m in self.manifests() if m.get("enabled") for e in m["accepts"]["extensions"]}); return exts
