"""Activities: everything that touches the outside world (thinking sense, the model, the ERP, the decision file). A workflow only decides and waits; these do the I/O and can be retried."""
import json, os, urllib.request
from temporalio import activity
import decisions, facts as facts_mod, recommend as rec_mod, rules, sap_facts, sap_rules

WRITE_BACK = os.environ.get("WRITE_BACK", "dry-run")             # dry-run (default): record the exact call, send nothing. live: send it to the ERP.
ERP_URL = os.environ.get("ERP_URL", "http://erp-mock:8086").rstrip("/")

@activity.defn
def gather_facts(payment_id: int) -> dict:
    return facts_mod.gather(payment_id)

@activity.defn
def rules_gate(facts: dict) -> dict:
    return rules.gate(facts)

@activity.defn
def sap_gather_facts(invoice_no: int) -> dict:
    return sap_facts.gather(invoice_no)

@activity.defn
def sap_rules_gate(facts: dict) -> dict:
    return sap_rules.gate(facts)

@activity.defn
def recommend(facts: dict, gate: dict) -> dict:
    return rec_mod.recommend(facts, gate)

def build_call(action: dict) -> dict:
    """The exact API call for an approved action. This is what the approver's hash covers and what dry-run shows."""
    if action.get("system") == "sap":
        return {"method": "POST", "url": "%s/Release?SupplierInvoice='%s'&FiscalYear='%s'" % (sap_facts.SVC, action["invoice_id"], action["fiscal_year"]),
                "needs": "an x-csrf-token fetched first, and a user allowed to release payment blocks", "idempotency_key": action["idempotency_key"]}
    kind = {"release": "release", "hold": "hold"}[action["type"]]
    return {"method": "POST", "path": "/payments/%d/%s" % (action["payment_id"], kind),
            "body": {k: action[k] for k in ("payment_id", "invoice_id", "amount", "currency", "payload_hash", "approvers")}, "idempotency_key": action["idempotency_key"]}

@activity.defn
def write_back(action: dict) -> dict:
    if action.get("system") == "sap":                       # SAP's public sandbox is read-only, so an SAP action is never sent, whatever WRITE_BACK says
        if action["type"] != "release": return {"mode": "no-write", "note": "keeping the payment block needs no change in SAP"}
        return {"mode": "dry-run", "would_send": build_call(action), "note": "not sent: SAP's public sandbox is read-only; a live release needs a tenant, credentials and a CSRF token"}
    call = build_call(action)
    if WRITE_BACK != "live": return {"mode": "dry-run", "would_send": call}
    req = urllib.request.Request(ERP_URL + call["path"], json.dumps(call["body"]).encode(), {"Content-Type": "application/json", "Idempotency-Key": call["idempotency_key"]})
    with urllib.request.urlopen(req, timeout=30) as r: return {"mode": "live", "sent": call, "response": json.load(r)}

@activity.defn
def record_decision(body: dict) -> dict:
    return {"hash": decisions.append(body)["hash"]}
