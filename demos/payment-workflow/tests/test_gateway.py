"""python3 -m unittest discover -s demos/payment-workflow/tests     No Temporal needed: the mapping is pure and the HTTP layer is driven with a fake engine."""
import http.client, json, os, sys, threading, unittest
from http.server import ThreadingHTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["GATEWAY_SETTLE_SECONDS"] = "0.6"
import gateway, gateway_map as M

TOKEN = "t" * 20
GATE = {"allowed_actions": ["hold", "escalate"], "approvals_required": 2, "blocks": ["the invoice is already marked Paid in the ERP: releasing again would be a duplicate payment"], "notes": ["above the 250000 USD dual-approval limit: two different approvers are required"],
        "excluded_approvers": ["a.tanaka", "ai", "claude", "policy-auto", "treasury-agent"]}
REC = {"recommendation": "hold", "confidence": 0.9, "reasons": ["Invoice is Paid", "amount differs"], "model": "rules-only"}
AWAIT = {"stage": "awaiting_approval", "initiator": "alice", "queryId": None, "payload_hash": "ab" * 32, "recommendation": REC, "gate": GATE, "approvals_required": 2, "approvals": [], "ignored": [],
         "facts_summary": {"vendor": "Acme", "invoice_no": "INV-9", "amount": "100.00", "currency": "EUR", "amount_usd": "108.00", "initiated_by": "a.tanaka"}}


class Fake:
    """An engine whose runs are plain dicts; a signal applies the same effect the workflow would."""
    def __init__(self): self.runs = {}; self.signals = []; self.mute = False
    def state(self, rid): return (self.runs[rid], "2026-11-17T10:00:00+00:00", "2026-11-17T10:01:00+00:00") if rid in self.runs else None
    def start(self, spec):
        created = spec["id"] not in self.runs
        if created: self.runs[spec["id"]] = {"stage": "facts", "initiator": spec["initiator"], "queryId": spec["queryId"], "approvals": [], "ignored": []}
        return created, self.state(spec["id"])
    def awaiting(self): return [(r, self.state(r)) for r, s in self.runs.items() if s.get("stage") == "awaiting_approval"]
    def signal(self, rid, kind, user, h, reason):
        self.signals.append((rid, kind, user, h, reason))
        if self.mute: return
        s = self.runs[rid]
        if kind == "approve":
            s["approvals"].append({"approver": user, "at": "t"})
            if len(s["approvals"]) >= s["approvals_required"]: s.update(stage="done", write_back={"mode": "dry-run", "would_send": {"method": "POST", "path": "/payments/35/hold"}})
        else: s.update(stage="rejected", rejection={"approver": user, "reason": reason, "at": "t"})


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Fake(); cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), gateway.make_handler(cls.engine, TOKEN)); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def setUp(self): self.engine.runs.clear(); self.engine.signals.clear(); self.engine.mute = False
    def call(self, method, path, body=None, token=TOKEN):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=10); h = {"Content-Type": "application/json"}
        if token: h["Authorization"] = "Bearer " + token
        c.request(method, path, json.dumps(body) if body is not None else None, h); r = c.getresponse(); raw = r.read(); return r.status, json.loads(raw or b"{}")
    def awaiting(self, key="35", **kw): self.engine.runs["payment-" + key] = dict(AWAIT, approvals=[], ignored=[], **kw)
    START = {"definition": "payment-exception", "key": "35", "initiator": "alice", "queryId": None, "idempotencyKey": "payment-exception|35", "requiredApprovals": 2}

    # --- mapping
    def test_run_shape_matches_the_servers_RunState(self):
        r = M.to_run("payment-35", AWAIT, 2, "c", "u")
        self.assertEqual((r["id"], r["definition"], r["key"], r["initiator"], r["stage"], r["requiredApprovals"], r["payloadHash"]), ("payment-35", "payment-exception", "35", "alice", "awaiting_approval", 2, "ab" * 32))
        self.assertEqual(r["recommendation"], {"action": "hold", "reason": "Invoice is Paid; amount differs", "source": "rules-only"})
        self.assertEqual([x["passed"] for x in r["rules"]], [False, True, True]); self.assertEqual(r["evidence"]["vendor"], "Acme"); self.assertTrue(all(isinstance(v, str) for v in r["evidence"].values()))
        for k in ("id", "definition", "key", "initiator", "queryId", "stage", "recommendation", "rules", "evidence", "approvals", "requiredApprovals", "payloadHash", "rejection", "writeBack", "createdAt", "updatedAt"): self.assertIn(k, r)
    def test_early_stages_hide_what_is_not_known_yet(self):
        r = M.to_run("payment-35", {"stage": "facts"}, 2); self.assertEqual((r["stage"], r["evidence"], r["rules"], r["payloadHash"], r["recommendation"]), ("facts", {}, [], None, None))
        self.assertEqual(M.to_run("payment-35", {"stage": "starting"})["stage"], "facts")
    def test_endings_the_server_has_no_stage_for_are_reported_honestly(self):
        e = M.to_run("payment-1", {"stage": "escalated", "recommendation": dict(REC, recommendation="escalate"), "gate": GATE}, 2, None, "u")
        self.assertEqual((e["stage"], e["rejection"]["user"]), ("rejected", "engine")); self.assertIn("escalate to a person", e["rejection"]["reason"])
        x = M.to_run("payment-1", {"stage": "expired", "gate": GATE}, 2, None, "u"); self.assertIn("deadline", x["rejection"]["reason"])
    def test_write_back_is_a_dry_run_naming_the_call(self):
        r = M.to_run("payment-35", dict(AWAIT, stage="done", write_back={"mode": "dry-run", "would_send": {"method": "POST", "path": "/payments/35/hold"}}), 2, None, "u")
        self.assertEqual((r["stage"], r["writeBack"]["mode"], r["writeBack"]["status"], r["writeBack"]["call"]), ("written_back", "dry_run", "simulated", "POST /payments/35/hold"))
        self.assertEqual(M.to_run("payment-35", dict(AWAIT, stage="done", write_back={"mode": "live", "sent": {"method": "POST", "path": "/p"}}), 2)["writeBack"]["status"], "sent")
        self.assertEqual(M.to_run("payment-35", dict(AWAIT, stage="writing_back"))["stage"], "approved")
    def test_a_run_started_in_the_inbox_has_no_initiator_and_says_so(self):
        self.assertEqual(M.to_run("payment-35", {"stage": "facts"})["initiator"], "(started in the approval inbox)")
    def test_keys_must_be_payment_ids_and_the_run_id_is_the_inbox_workflow_id(self):
        self.assertEqual(M.run_id(" 35 "), "payment-35")
        for bad in ("", "abc", "35; drop", "1" * 13, "-1", "3.5", None): self.assertRaises(M.Refusal, M.run_id, bad)
        self.assertFalse(M.RUN_ID.match("sap-invoice-5")); self.assertFalse(M.RUN_ID.match("payment-35/x")); self.assertTrue(M.RUN_ID.match("payment-35"))

    # --- the second line of defence
    def sig(self, **kw): return dict({"type": "approve", "user": "bob", "payloadHash": "ab" * 32}, **kw)
    def refusal(self, st, sig):
        with self.assertRaises(M.Refusal) as c: M.precheck(st, sig)
        return c.exception.status, c.exception.code
    def test_precheck_uses_the_servers_codes(self):
        M.precheck(AWAIT, self.sig())
        self.assertEqual(self.refusal(AWAIT, self.sig(user="alice")), (403, "initiator_cannot_approve"))
        self.assertEqual(self.refusal(AWAIT, self.sig(user="Treasury-Agent")), (403, "non_human_identity"))
        self.assertEqual(self.refusal(AWAIT, self.sig(user="a.tanaka")), (403, "not_an_approver"))             # initiated the payment itself
        self.assertEqual(self.refusal(dict(AWAIT, approvals=[{"approver": "Bob", "at": "t"}]), self.sig()), (403, "already_approved"))
        self.assertEqual(self.refusal(AWAIT, self.sig(payloadHash="00")), (409, "payload_hash_mismatch"))
        self.assertEqual(self.refusal(dict(AWAIT, stage="done"), self.sig()), (409, "not_awaiting_approval"))
        self.assertEqual(self.refusal(AWAIT, self.sig(type="delete")), (400, "bad_request")); self.assertEqual(self.refusal(AWAIT, self.sig(user=" ")), (400, "bad_request"))
    def test_the_initiator_may_withdraw_but_not_without_a_reason(self):
        M.precheck(AWAIT, {"type": "reject", "user": "alice", "reason": "withdrawn"})
        self.assertEqual(self.refusal(AWAIT, {"type": "reject", "user": "alice", "reason": " "}), (400, "bad_request"))
        self.assertEqual(self.refusal(AWAIT, {"type": "reject", "user": "ai", "reason": "x"}), (403, "non_human_identity"))

    # --- HTTP
    def test_every_route_but_health_needs_the_token(self):
        self.assertEqual(self.call("GET", "/health", token=None)[0], 200)
        for m, p, b in (("GET", "/runs?stage=awaiting_approval", None), ("GET", "/runs/payment-35", None), ("POST", "/runs", self.START), ("POST", "/runs/payment-35/signal", self.sig())):
            self.assertEqual(self.call(m, p, b, token=None)[0], 401); self.assertEqual(self.call(m, p, b, token="wrong" * 5)[0], 401)
        self.assertEqual(self.engine.runs, {}); self.assertEqual(self.engine.signals, [])
    def test_the_token_check_never_accepts_an_unset_token(self):
        self.assertFalse(M.token_ok("Bearer ", "")); self.assertFalse(M.token_ok(None, "x" * 20)); self.assertFalse(M.token_ok("Basic abc", "abc")); self.assertTrue(M.token_ok("Bearer " + TOKEN, TOKEN))
    def test_start_is_idempotent_and_201_only_when_created(self):
        s, d = self.call("POST", "/runs", self.START); self.assertEqual((s, d["created"], d["run"]["initiator"], d["run"]["id"]), (201, True, "alice", "payment-35"))
        s, d = self.call("POST", "/runs", dict(self.START, initiator="bob")); self.assertEqual((s, d["created"], d["run"]["initiator"]), (200, False, "alice"))         # the first starter stays the starter
    def test_start_refusals(self):
        for body, want in (({}, 404), (dict(self.START, definition="other"), 404), (dict(self.START, key="x"), 400), (dict(self.START, initiator=""), 400), ([], 400)):
            s, d = self.call("POST", "/runs", body); self.assertEqual(s, want, body); self.assertIn("code", d)
        self.assertEqual(self.engine.runs, {})
    def test_get_run_and_unknown_ids(self):
        self.awaiting(); s, d = self.call("GET", "/runs/payment-35"); self.assertEqual((s, d["run"]["stage"]), (200, "awaiting_approval"))
        self.assertEqual(self.call("GET", "/runs/payment-99")[1]["code"], "unknown_run")
        for bad in ("/runs/sap-invoice-5", "/runs/..%2f", "/runs/payment-35/extra"): self.assertIn(self.call("GET", bad)[0], (404,))
    def test_queue_lists_only_runs_awaiting_approval(self):
        self.awaiting("35"); self.awaiting("36"); self.engine.runs["payment-37"] = {"stage": "done", "approvals": [], "ignored": []}
        s, d = self.call("GET", "/runs?stage=awaiting_approval"); self.assertEqual((s, sorted(r["key"] for r in d["runs"])), (200, ["35", "36"]))
        self.assertEqual(self.call("GET", "/runs?stage=done")[0], 400); self.assertEqual(self.call("GET", "/runs")[0], 400)
    def test_two_approvals_complete_a_dual_run_with_a_dry_run(self):
        self.awaiting(); s, d = self.call("POST", "/runs/payment-35/signal", self.sig()); self.assertEqual((s, len(d["run"]["approvals"]), d["run"]["stage"]), (200, 1, "awaiting_approval"))
        s, d = self.call("POST", "/runs/payment-35/signal", self.sig(user="carol")); self.assertEqual((s, d["run"]["stage"], d["run"]["writeBack"]["status"]), (200, "written_back", "simulated"))
        self.assertEqual([x[2] for x in self.engine.signals], ["bob", "carol"])
    def test_a_refused_signal_never_reaches_the_workflow(self):
        self.awaiting()
        for sg, want in ((self.sig(user="alice"), "initiator_cannot_approve"), (self.sig(payloadHash="00"), "payload_hash_mismatch"), (self.sig(user="ai"), "non_human_identity")):
            s, d = self.call("POST", "/runs/payment-35/signal", sg); self.assertEqual(d["code"], want)
        self.assertEqual(self.engine.signals, []); self.assertEqual(self.call("POST", "/runs/payment-99/signal", self.sig())[0], 404)
    def test_reject_ends_the_run(self):
        self.awaiting(); s, d = self.call("POST", "/runs/payment-35/signal", {"type": "reject", "user": "carol", "reason": "invoice unverified"})
        self.assertEqual((s, d["run"]["stage"], d["run"]["rejection"]["user"], d["run"]["rejection"]["reason"]), (200, "rejected", "carol", "invoice unverified"))
    def test_a_signal_the_workflow_ignores_is_reported_not_swallowed(self):
        self.awaiting(); orig = self.engine.signal
        def ignoring(rid, kind, user, h, reason): self.engine.runs[rid]["ignored"].append({"approver": user, "why": "not allowed to approve this payment, or already counted"})
        self.engine.signal = ignoring
        try: s, d = self.call("POST", "/runs/payment-35/signal", self.sig())
        finally: self.engine.signal = orig
        self.assertEqual((s, d["code"]), (403, "engine_refused"))
    def test_a_workflow_that_never_answers_is_a_502_not_a_hang(self):
        self.awaiting(); self.engine.mute = True; s, d = self.call("POST", "/runs/payment-35/signal", self.sig()); self.assertEqual((s, d["code"]), (502, "engine_unavailable"))
    def test_an_engine_crash_is_a_502_with_a_short_message(self):
        class Boom(Fake):
            def state(self, rid): raise RuntimeError("temporal down " + "x" * 500)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), gateway.make_handler(Boom(), TOKEN)); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port); c.request("GET", "/runs/payment-35", headers={"Authorization": "Bearer " + TOKEN}); r = c.getresponse(); d = json.loads(r.read())
            self.assertEqual((r.status, d["code"]), (502, "engine_unavailable")); self.assertLess(len(d["error"]), 220)
        finally: srv.shutdown()
    def test_the_service_refuses_to_start_without_a_real_token(self):
        for tok in ("", "short"):
            os.environ["GATEWAY_TOKEN"] = tok
            with self.assertRaises(SystemExit): gateway.main()
        os.environ.pop("GATEWAY_TOKEN", None)


if __name__ == "__main__": unittest.main()
