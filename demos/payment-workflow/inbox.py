"""The approval inbox, http://localhost:8085. Lists the payments waiting for approval (read through thinking sense), starts a workflow per exception, shows each one's
recommendation, rules and evidence, takes approve / reject from a named person, and shows the decision record. Demo only: the person types their name; a real deployment
puts this behind the customer's single sign-on and ties the approver to the signed-in identity."""
import asyncio, json, os, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
import decisions, facts, sap_facts, sap_rules
from workflows import PaymentException

LOOP = asyncio.new_event_loop(); threading.Thread(target=LOOP.run_forever, daemon=True).start()
run = lambda coro: asyncio.run_coroutine_threadsafe(coro, LOOP).result(120)
CLIENT = run(Client.connect(os.environ.get("TEMPORAL_ADDRESS", "temporal:7233")))
wid = lambda pid, source="treasury": ("sap-invoice-%d" if source == "sap" else "payment-%d") % int(pid)

# --- Ask bridge: the page's question box calls the app's real Ask API (/api/ask) from here, signed in as a demo user, and gets the answer and rows back.
# (The browser cannot call Ask directly: it is another origin, it sends a cross-site guard header, and it refuses to be framed.)
ASK_URLS = {"treasury": facts.ASK_URL, "sap": os.environ.get("SAP_ASK_URL", "").rstrip("/")}     # the SAP tab asks the SAP spike app (../sap-spike), a separate app
ASK_USER = os.environ.get("ASK_USER", "demo"); ASK_PASSWORD = os.environ.get("ASK_PASSWORD", "demo")
ASK_PUBLIC_URL = os.environ.get("ASK_PUBLIC_URL", "http://localhost:8080").rstrip("/"); SAP_ASK_PUBLIC_URL = os.environ.get("SAP_ASK_PUBLIC_URL", "http://localhost:8087").rstrip("/")
_cookie = {}
def _ask_login(source):
    req = urllib.request.Request(ASK_URLS[source] + "/app/login", json.dumps({"username": ASK_USER, "password": ASK_PASSWORD}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        _cookie[source] = (r.headers.get("Set-Cookie") or "").split(";")[0]
def ask(question, conversation_id=None, source="treasury"):
    if not ASK_URLS.get(source): return {"error": "no Ask app is configured for %s (set SAP_ASK_URL)" % source}
    for attempt in (1, 2):
        if not _cookie.get(source): _ask_login(source)
        body = {"question": question}
        if conversation_id: body["conversationId"] = conversation_id
        req = urllib.request.Request(ASK_URLS[source] + "/api/ask", json.dumps(body).encode(), {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "Cookie": _cookie[source]})
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
            return {"answer": done.get("answer"), "columns": done.get("columns") or [], "rows": done.get("rows") or [], "conversationId": cid, "askUrl": SAP_ASK_PUBLIC_URL if source == "sap" else ASK_PUBLIC_URL}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and attempt == 1: _cookie[source] = None; continue      # session expired: sign in again once
            raise

async def _state(pid, source="treasury"):
    h = CLIENT.get_workflow_handle(wid(pid, source))
    try: d = await h.describe()
    except Exception: return None
    s = {"workflow_status": d.status.name if d.status else None}
    try: s.update(await h.query(PaymentException.status))
    except Exception: pass
    return s

async def _states(ids, source="treasury"): return await asyncio.gather(*[_state(i, source) for i in ids])

def pending(source="treasury"):
    if source == "sap": return sap_pending()
    pays = facts.pending_payments(); states = run(_states([p["payment_id"] for p in pays]))
    for p, st in zip(pays, states):
        flags = []
        if p["invoice_status"] in ("Paid", "On hold"): flags.append("invoice is %s" % p["invoice_status"])
        if float(p["invoice_amount"]) != float(p["amount"]): flags.append("amount differs from invoice")
        if float(p["amount_usd"]) > float(p["dual_approval_above_usd"]): flags.append("needs two approvers")
        p["flags"] = flags; p["workflow"] = st
    return pays

def sap_pending():
    """The payment-blocked supplier invoices in SAP's sandbox, in the same shape as a Treasury payment so the page can show both."""
    inv = sap_facts.pending_invoices(); states = run(_states([r["SupplierInvoice"] for r in inv], "sap")); by_supplier = {}
    for r in inv: by_supplier[r["InvoicingParty"]] = by_supplier.get(r["InvoicingParty"], 0) + 1
    out = []
    for r, st in zip(inv, states):
        usd = sap_rules.amount_usd({"invoice": r}); flags = ["payment block %s" % r["PaymentBlockingReason"]]
        if usd is not None and usd > sap_rules.Decimal(sap_rules.POLICY["dual_approval_above_usd"]): flags.append("needs two approvers")
        if by_supplier[r["InvoicingParty"]] >= 10: flags.append("%d blocked from this supplier" % by_supplier[r["InvoicingParty"]])
        out.append({"payment_id": r["SupplierInvoice"], "title": "SAP invoice %s" % r["SupplierInvoice"], "vendor": r["InvoicingParty"], "amount": r["InvoiceGrossAmount"], "currency": r["DocumentCurrency"],
                    "amount_usd": str(usd) if usd is not None else None, "invoice_no": r["SupplierInvoiceIDByInvcgParty"] if "SupplierInvoiceIDByInvcgParty" in r else r["SupplierInvoice"],
                    "invoice_status": "blocked (%s)" % r["PaymentBlockingReason"], "initiated_by": "(not in SAP's header)", "flags": flags, "workflow": st})
    return sorted(out, key=lambda x: -float(x["amount"]))

async def _start(pid, source="treasury"):
    try: await CLIENT.start_workflow(PaymentException.run, args=[int(pid), source], id=wid(pid, source), task_queue="payment-exceptions"); return {"started": True}
    except WorkflowAlreadyStartedError: return {"started": False, "why": "already running or finished"}
async def _signal(pid, who, action, h, reason, source="treasury"):
    hd = CLIENT.get_workflow_handle(wid(pid, source))
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
            elif self.path.split("?")[0] == "/api/pending": self._send(200, pending("sap" if "source=sap" in self.path else "treasury"))
            elif self.path == "/api/decisions": self._send(200, {"records": decisions.read(), "chain": decisions.verify()})
            else: self._send(404, {"error": "not found"})
        except Exception as e: self._send(500, {"error": str(e)[:300]})
    def do_POST(self):
        try:
            b = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/start": self._send(200, run(_start(b["payment_id"], b.get("source", "treasury"))))
            elif self.path == "/api/ask": self._send(200, ask(str(b.get("question", "")).strip()[:500], b.get("conversationId"), b.get("source", "treasury")))
            elif self.path == "/api/decide": run(_signal(b["payment_id"], str(b.get("approver", "")).strip(), b["action"], b.get("hash", ""), b.get("reason"), b.get("source", "treasury"))); self._send(200, {"sent": True})
            else: self._send(404, {"error": "not found"})
        except Exception as e: self._send(500, {"error": str(e)[:300]})
    def log_message(self, *a): pass
if __name__ == "__main__": print("inbox on :8085", flush=True); ThreadingHTTPServer(("0.0.0.0", 8085), H).serve_forever()
