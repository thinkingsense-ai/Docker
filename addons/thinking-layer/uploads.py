"""Upload records (docs/agency-spec.md FR-17, FR-21): private to the uploader, expiring, in memory. The raw file is never kept: it goes to the adapter and is dropped; only the
derived record stays. Sharing within a Workspace (FR-17a, admin setting `uploadSharing`) is not built: every record is owner-only."""
import secrets, threading, time

MAX_PER_USER = 20


class Store:
    def __init__(self, hours=1.0):
        self.ttl = hours * 3600; self.rows = {}; self.lock = threading.Lock()

    def _purge(self):
        now = time.time()
        for k in [k for k, r in self.rows.items() if r["expiresAtEpoch"] <= now]: del self.rows[k]

    def add(self, owner, name, workspace, manifest, ingest):
        with self.lock:
            self._purge()
            if sum(1 for r in self.rows.values() if r["owner"] == owner) >= MAX_PER_USER: return None
            now = time.time(); rid = "up_" + secrets.token_urlsafe(9)
            self.rows[rid] = {"id": rid, "owner": owner, "name": name, "kind": manifest.get("kind"), "adapter": manifest.get("id"), "workspaceId": workspace,
                              "createdAtEpoch": now, "expiresAtEpoch": now + self.ttl, "nonCommercial": bool(manifest.get("nonCommercial")),
                              "licence": ingest.get("licence"), "notes": ingest.get("notes") or [], "askPrompts": ingest.get("askPrompts") or [], "result": ingest.get("result")}
            return self.view(self.rows[rid])

    @staticmethod
    def view(r): return {k: v for k, v in r.items() if k not in ("owner", "createdAtEpoch", "expiresAtEpoch")} | {"expiresAt": int(r["expiresAtEpoch"] * 1000)}

    def mine(self, owner):
        with self.lock: self._purge(); return [self.view(r) for r in self.rows.values() if r["owner"] == owner]

    def get(self, owner, rid):
        with self.lock:
            self._purge(); r = self.rows.get(rid)
            return self.view(r) if r and r["owner"] == owner else None          # someone else's record is indistinguishable from a missing one

    def delete(self, owner, rid):
        with self.lock:
            r = self.rows.get(rid)
            if r and r["owner"] == owner: del self.rows[rid]; return True
            return False
