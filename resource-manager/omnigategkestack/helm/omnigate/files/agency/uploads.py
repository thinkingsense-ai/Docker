"""Upload records (docs/agency-spec.md FR-17, FR-21): private to the uploader, expiring, in memory. The raw file is never kept: it goes to the adapter and is dropped; only the
derived record stays. Records are owner-only until the owner shares one (FR-17a, operator setting AGENCY_UPLOAD_SHARING=workspace): the layer then shows it, read-only
and redacted (no GPS position), to other signed-in users whose OWN session lists that Workspace, so the Server's access rules decide who sees it and sharing never widens them.
Sharing does not extend the expiry. Upload admins (AGENCY_UPLOAD_ADMINS) may unshare or delete shared records, never read private ones."""
import secrets, threading, time

MAX_PER_USER = 20


class Store:
    def __init__(self, hours=1.0):
        self.ttl = hours * 3600; self.rows = {}; self.lock = threading.Lock()

    def _purge(self):
        now = time.time()
        for k in [k for k, r in self.rows.items() if r["expiresAtEpoch"] <= now]: del self.rows[k]

    def add(self, owner, name, workspace, manifest, ingest, server=None):
        with self.lock:
            self._purge()
            if sum(1 for r in self.rows.values() if r["owner"] == owner) >= MAX_PER_USER: return None
            now = time.time(); rid = "up_" + secrets.token_urlsafe(9)
            self.rows[rid] = {"id": rid, "owner": owner, "name": name, "kind": manifest.get("kind"), "adapter": manifest.get("id"), "workspaceId": workspace,
                              "createdAtEpoch": now, "expiresAtEpoch": now + self.ttl, "nonCommercial": bool(manifest.get("nonCommercial")),
                              "sharedBy": None, "sharedAtEpoch": None, "licence": ingest.get("licence"), "notes": ingest.get("notes") or [], "askPrompts": ingest.get("askPrompts") or [], "result": ingest.get("result"),
                              "server": server}                           # {uploadId, conversationId, untilEpoch}: the Server's own conversation-scoped copy, if one was made
            return self.view(self.rows[rid])

    @staticmethod
    def view(r, viewer=None):
        out = {k: v for k, v in r.items() if k not in ("owner", "createdAtEpoch", "expiresAtEpoch", "sharedBy", "sharedAtEpoch", "server")}
        srv = r.get("server"); out["askable"] = bool(srv and srv["untilEpoch"] > time.time() and not srv.get("gone") and (viewer is None or r["owner"] == viewer))
        if srv and out["askable"]: out["askableUntil"] = int(srv["untilEpoch"] * 1000)
        if not out["askable"]: out["askPrompts"] = []
        out.update(expiresAt=int(r["expiresAtEpoch"] * 1000), shared=bool(r["sharedBy"]), sharedAt=int(r["sharedAtEpoch"] * 1000) if r["sharedAtEpoch"] else None,
                   mine=viewer is None or r["owner"] == viewer)
        if r["sharedBy"]: out["sharedBy"] = r["sharedBy"]
        if not out["mine"]:                                                      # what others see: no location, and no note about it
            res = dict(out["result"]) if isinstance(out.get("result"), dict) else out.get("result")
            if isinstance(res, dict): res.pop("gps", None)
            out["result"] = res; out["notes"] = [n for n in out["notes"] if "GPS" not in n]
        return out

    def mine(self, owner):
        with self.lock: self._purge(); return [self.view(r, owner) for r in self.rows.values() if r["owner"] == owner]

    def shared_with(self, viewer, workspaces, admin=False):
        """Shared records of other users in a Workspace the viewer's own session lists (an upload admin sees every shared record)."""
        with self.lock:
            self._purge()
            return [self.view(r, viewer) for r in self.rows.values() if r["owner"] != viewer and r["sharedBy"] and (admin or r["workspaceId"] in workspaces)]

    def get(self, viewer, rid, workspaces=None, admin=False):
        with self.lock:
            self._purge(); r = self.rows.get(rid)
            if not r: return None
            if r["owner"] == viewer: return self.view(r, viewer)
            if r["sharedBy"] and (admin or (workspaces is not None and r["workspaceId"] in workspaces)): return self.view(r, viewer)
            return None                                                            # someone else's private record is indistinguishable from a missing one

    def owned(self, owner, rid):
        with self.lock:
            self._purge(); r = self.rows.get(rid)
            return dict(r) if r and r["owner"] == owner else None

    def ask_target(self, owner, rid, session=None):
        """(Server uploadId, conversationId) when this person's own record still has a live copy on the Server, else None. `session` is (Server cookie, Workspace switches so far):
        the Server forgets an uploaded file when the session's Workspace is changed (found live, app 0.10.21), so a copy made before a switch, or in another session, is gone."""
        with self.lock:
            self._purge(); r = self.rows.get(rid); srv = r and r["owner"] == owner and r.get("server")
            if not srv or srv["untilEpoch"] <= time.time() or (session is not None and tuple(srv.get("session") or ()) != tuple(session)): return None
            return srv["uploadId"], srv["conversationId"]

    def forget_server_copies(self, owner, cookie):
        """The session's Workspace changed: the Server no longer holds this person's files from that session."""
        with self.lock:
            for r in self.rows.values():
                if r["owner"] == owner and r.get("server") and r["server"].get("session", (None,))[0] == cookie: r["server"]["gone"] = True

    def set_shared(self, who, rid, on, admin=False):
        """Owner shares or unshares; an admin may only unshare a shared record. Returns the viewer's view or None."""
        with self.lock:
            self._purge(); r = self.rows.get(rid)
            if not r: return None
            if r["owner"] == who:
                r["sharedBy"], r["sharedAtEpoch"] = (who, time.time()) if on else (None, None); return self.view(r, who)
            if admin and not on and r["sharedBy"]:
                r["sharedBy"], r["sharedAtEpoch"] = None, None; return self.view(r, who)
            return None

    def delete(self, who, rid, admin=False):
        with self.lock:
            r = self.rows.get(rid)
            if r and (r["owner"] == who or (admin and r["sharedBy"])): del self.rows[rid]; return True
            return False
