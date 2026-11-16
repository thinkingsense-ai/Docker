"""The approval inbox, http://localhost:8085. Lists the payments waiting for approval (read through thinking sense), starts a workflow per exception, shows each one's
recommendation, rules and evidence, takes approve / reject from a named person, and shows the decision record. Demo only: the person types their name; a real deployment
puts this behind the customer's single sign-on and ties the approver to the signed-in identity."""
import asyncio, json, os, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
import decisions, facts
from workflows import PaymentException

LOOP = asyncio.new_event_loop(); threading.Thread(target=LOOP.run_forever, daemon=True).start()
run = lambda coro: asyncio.run_coroutine_threadsafe(coro, LOOP).result(120)
CLIENT = run(Client.connect(os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")))
wid = lambda pid: "payment-%d" % int(pid)

# --- Ask bridge: the page's question box calls the app's real Ask API (/api/ask) from here, signed in as a demo user, and gets the answer and rows back.
# (The browser cannot call Ask directly: it is another origin, it sends a cross-site guard header, and it refuses to be framed.)
ASK_URL = facts.ASK_URL; ASK_USER = os.environ.get("ASK_USER", "demo"); ASK_PASSWORD = os.environ.get("ASK_PASSWORD", "demo")
ASK_PUBLIC_URL = os.environ.get("ASK_PUBLIC_URL", "http://localhost:8080").rstrip("/")
_cookie = {"v": None}
def _ask_login():
    req = urllib.request.Request(ASK_URL + "/app/login", json.dumps({"username": ASK_USER, "password": ASK_PASSWORD}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        _cookie["v"] = (r.headers.get("Set-Cookie") or "").split(";")[0]
def ask(question, conversation_id=None):
    for attempt in (1, 2):
        if not _cookie["v"]: _ask_login()
        body = {"question": question}
        if conversation_id: body["conversationId"] = conversation_id
        req = urllib.request.Request(ASK_URL + "/api/ask", json.dumps(body).encode(), {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "Cookie": _cookie["v"]})
        try:
            done = {}; cid = conversation_id
            with urllib.request.urlopen(req, timeout=180) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"): continue
                    try: d = json.loads(line[5:])
                    except ValueError: continue
                    cid = d.get("conversationId", cid)
                    if "error" in d and d.get("step") in (None, "error"): return {"error": str(d["error"])[:300], "conversationId": cid}
                    if d.get("step") == "done": done = d
            return {"answer": done.get("answer"), "columns": done.get("columns") or [], "rows": done.get("rows") or [], "conversationId": cid, "askUrl": ASK_PUBLIC_URL}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and attempt == 1: _cookie["v"] = None; continue      # session expired: sign in again once
            raise

async def _state(pid):
    h = CLIENT.get_workflow_handle(wid(pid))
    try: d = await h.describe()
    except Exception: return None
    s = {"workflow_status": d.status.name if d.status else None}
    try: s.update(await h.query(PaymentException.status))
    except Exception: pass
    return s

async def _states(ids): return await asyncio.gather(*[_state(i) for i in ids])

def pending():
    pays = facts.pending_payments(); states = run(_states([p["payment_id"] for p in pays]))
    for p, st in zip(pays, states):
        flags = []
        if p["invoice_status"] in ("Paid", "On hold"): flags.append("invoice is %s" % p["invoice_status"])
        if float(p["invoice_amount"]) != float(p["amount"]): flags.append("amount differs from invoice")
        if float(p["amount_usd"]) > float(p["dual_approval_above_usd"]): flags.append("needs two approvers")
        p["flags"] = flags; p["workflow"] = st
    return pays

async def _start(pid):
    try: await CLIENT.start_workflow(PaymentException.run, int(pid), id=wid(pid), task_queue="payment-exceptions"); return {"started": True}
    except WorkflowAlreadyStartedError: return {"started": False, "why": "already running or finished"}
async def _signal(pid, who, action, h, reason):
    hd = CLIENT.get_workflow_handle(wid(pid))
    if action == "approve": await hd.signal(PaymentException.approve, args=[who, h])
    else: await hd.signal(PaymentException.reject, args=[who, reason or "rejected"])

PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox.html")).read()
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        try:
            if self.path == "/": self._send(200, PAGE, "text/html")
            elif self.path == "/api/pending": self._send(200, pending())
            elif self.path == "/api/decisions": self._send(200, {"records": decisions.read(), "chain": decisions.verify()})
            else: self._send(404, {"error": "not found"})
        except Exception as e: self._send(500, {"error": str(e)[:300]})
    def do_POST(self):
        try:
            b = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/start": self._send(200, run(_start(b["payment_id"])))
            elif self.path == "/api/ask": self._send(200, ask(str(b.get("question", "")).strip()[:500], b.get("conversationId")))
            elif self.path == "/api/decide": run(_signal(b["payment_id"], str(b.get("approver", "")).strip(), b["action"], b.get("hash", ""), b.get("reason"))); self._send(200, {"sent": True})
            else: self._send(404, {"error": "not found"})
        except Exception as e: self._send(500, {"error": str(e)[:300]})
    def log_message(self, *a): pass
if __name__ == "__main__": print("inbox on :8085", flush=True); ThreadingHTTPServer(("0.0.0.0", 8085), H).serve_forever()
