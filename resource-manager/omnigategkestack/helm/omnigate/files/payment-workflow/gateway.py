"""Workflow engine gateway: the HTTP contract the Server's `OMNIGATE_WORKFLOW_ENGINE=http://gateway:8094` adapter speaks (docs/workflows-api.md in the Server repo, "Engine gateway contract"),
in front of the payment-exception Temporal workflow. It adds no business logic: the Server has already checked grants, initiator, repeat approvals and the payload hash, and the
workflow re-checks the rules; the gateway starts runs, reads their state, and delivers signals, refusing a bad one synchronously (a Temporal signal is fire-and-forget).

  POST /runs               {definition, key, initiator, queryId, idempotencyKey, requiredApprovals} -> {run, created}
  GET  /runs/{id}          -> {run} | 404
  GET  /runs?stage=awaiting_approval -> {runs: [...]}
  POST /runs/{id}/signal   {type: approve|reject, user, payloadHash, reason} -> {run} | 400/403/404/409 {code, error}
  GET  /health             (no token)

Every other route needs `Authorization: Bearer $GATEWAY_TOKEN`, and the service refuses to start without a token: it can approve payments' fate for anyone who can reach it. Keep it on a private network.
Environment: GATEWAY_TOKEN (required), GATEWAY_PORT (8094), TEMPORAL_ADDRESS."""
import asyncio, datetime, json, os, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gateway_map as M

SETTLE_SECONDS = float(os.environ.get("GATEWAY_SETTLE_SECONDS", "8"))
MAX_BODY = 100_000


class TemporalEngine:
    """The only part that imports the Temporal SDK. Runs on its own event loop thread, like the approval inbox."""
    def __init__(self):
        import temporal_wait
        from workflows import PaymentException
        self.W = PaymentException
        self.loop = asyncio.new_event_loop(); threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.client = self._run(temporal_wait.connect())

    def _run(self, coro): return asyncio.run_coroutine_threadsafe(coro, self.loop).result(120)

    async def _state(self, rid):
        from temporalio.service import RPCError, RPCStatusCode
        h = self.client.get_workflow_handle(rid)
        try: d = await h.describe()
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND: return None
            raise
        try: st = await h.query(self.W.status)
        except Exception: st = {"stage": "starting"}                                 # the first workflow task has not run yet
        created = d.start_time.isoformat() if d.start_time else None
        updated = (d.close_time or datetime.datetime.now(datetime.timezone.utc)).isoformat()
        return st, created, updated

    def state(self, rid): return self._run(self._state(rid))

    def start(self, spec):
        from temporalio.exceptions import WorkflowAlreadyStartedError
        async def go():
            try:
                await self.client.start_workflow(self.W.run, args=[int(spec["id"].split("-")[1]), "treasury", {"initiator": spec["initiator"], "queryId": spec["queryId"]}], id=spec["id"], task_queue="payment-exceptions")
                created = True
            except WorkflowAlreadyStartedError: created = False
            return created, await self._state(spec["id"])
        created, s = self._run(go()); return created, s

    def awaiting(self):
        async def go():
            out = []
            async for e in self.client.list_workflows('WorkflowType="PaymentException" AND ExecutionStatus="Running"', limit=100):
                if M.RUN_ID.match(e.id):
                    s = await self._state(e.id)
                    if s and s[0].get("stage") == "awaiting_approval": out.append((e.id, s))
            return out
        return sorted(self._run(go()), key=lambda x: x[1][1] or "", reverse=True)

    def signal(self, rid, kind, user, payload_hash, reason):
        async def go():
            h = self.client.get_workflow_handle(rid)
            if kind == "approve": await h.signal(self.W.approve, args=[user, payload_hash])
            else: await h.signal(self.W.reject, args=[user, reason])
        self._run(go())


def make_handler(engine, token):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def send(self, code, obj):
            b = json.dumps(obj, default=str).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

        def fail(self, e): self.send(e.status, {"success": False, "code": e.code, "error": str(e)})

        def authed(self):
            if M.token_ok(self.headers.get("Authorization"), token): return True
            self.send(401, {"success": False, "code": "unauthorized", "error": "a bearer token is required"}); return False

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY: raise M.Refusal(400, "bad_request", "body too large")
            try: return json.loads(self.rfile.read(n) or b"{}")
            except ValueError: raise M.Refusal(400, "bad_request", "body is not JSON")

        def run_json(self, rid, requested=2):
            s = engine.state(rid)
            if s is None: raise M.Refusal(404, "unknown_run", "no run %r" % rid)
            st, created, updated = s
            return M.to_run(rid, st, requested, created, updated), st

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/health": return self.send(200, {"ok": True})
            if not self.authed(): return
            try:
                if u.path == "/runs":
                    if urllib.parse.parse_qs(u.query).get("stage") != ["awaiting_approval"]: raise M.Refusal(400, "bad_request", "only stage=awaiting_approval is supported")
                    return self.send(200, {"runs": [M.to_run(rid, st, 2, c, up) for rid, (st, c, up) in engine.awaiting()]})
                if u.path.startswith("/runs/") and "/" not in u.path[6:]:
                    rid = u.path[6:]
                    if not M.RUN_ID.match(rid): raise M.Refusal(404, "unknown_run", "no such run")
                    return self.send(200, {"run": self.run_json(rid)[0]})
                self.send(404, {"success": False, "code": "not_found", "error": "no such route"})
            except M.Refusal as e: self.fail(e)
            except Exception as e: self.send(502, {"success": False, "code": "engine_unavailable", "error": "the workflow engine failed: %s" % str(e)[:160]})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if not self.authed(): return
            try:
                if u.path == "/runs":
                    spec = M.check_start(self.body())
                    created, s = engine.start(spec)
                    st, c, up = s
                    return self.send(201 if created else 200, {"created": created, "run": M.to_run(spec["id"], st, spec["requiredApprovals"], c, up)})
                if u.path.startswith("/runs/") and u.path.endswith("/signal") and u.path.count("/") == 3:
                    rid = u.path.split("/")[2]
                    if not M.RUN_ID.match(rid): raise M.Refusal(404, "unknown_run", "no such run")
                    sig = self.body()
                    s = engine.state(rid)
                    if s is None: raise M.Refusal(404, "unknown_run", "no run %r" % rid)
                    M.precheck(s[0], sig)
                    before = (len(s[0].get("approvals", [])), len(s[0].get("ignored", [])), s[0].get("stage"))
                    engine.signal(rid, sig["type"], sig["user"].strip(), sig.get("payloadHash"), (sig.get("reason") or "").strip() or None)
                    deadline = time.time() + SETTLE_SECONDS
                    while True:
                        st, c, up = engine.state(rid)
                        if len(st.get("ignored", [])) > before[1]: raise M.Refusal(403, "engine_refused", st["ignored"][-1].get("why", "the workflow ignored the signal"))
                        if len(st.get("approvals", [])) > before[0] or st.get("stage") != before[2] or st.get("rejection"): break
                        if time.time() > deadline: raise M.Refusal(502, "engine_unavailable", "the workflow did not confirm the signal (is the worker running?)")
                        time.sleep(0.25)
                    return self.send(200, {"run": M.to_run(rid, st, 2, c, up)})
                self.send(404, {"success": False, "code": "not_found", "error": "no such route"})
            except M.Refusal as e: self.fail(e)
            except Exception as e: self.send(502, {"success": False, "code": "engine_unavailable", "error": "the workflow engine failed: %s" % str(e)[:160]})
    return H


def main():
    token = os.environ.get("GATEWAY_TOKEN", "")
    if len(token) < 16: sys.exit("GATEWAY_TOKEN must be set (at least 16 characters): the gateway can start and decide runs for anyone who reaches it.")
    port = int(os.environ.get("GATEWAY_PORT", "8094"))
    engine = TemporalEngine()
    print("workflow gateway on :%d" % port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(engine, token)).serve_forever()


if __name__ == "__main__": main()
