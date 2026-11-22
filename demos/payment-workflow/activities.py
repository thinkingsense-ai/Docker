"""Activities: everything that touches the outside world (thinking sense, the model, the ERP, the decision file). A workflow only decides and waits; these do the I/O and can be retried."""
import json, os, urllib.request
from temporalio import activity
import assess_facts, assess_rules, major_facts, major_rules, decisions, register_write, facts as facts_mod, it_facts, it_rules, rca_facts, rca_rules, recommend as rec_mod, rules, sap_facts, sap_rules

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

@activity.defn
def it_gather_facts(vuln_id: int) -> dict:
    return it_facts.gather(vuln_id)

@activity.defn
def it_rules_gate(facts: dict, initiator: str) -> dict:
    return it_rules.gate(facts, initiator)

@activity.defn
def it_recommend(facts: dict, gate: dict) -> dict:
    return rec_mod.recommend(facts, gate, "vulnerability")

def build_it_call(action: dict) -> dict:
    """The exact call to the (not yet connected) GRC tool for an approved action: what the approver's hash covers and what the dry run shows."""
    path = {"remediate": "remediation-requests", "grant_exception": "exceptions"}[action["type"]]
    body = {k: action[k] for k in ("vuln_id", "cve", "service_id", "payload_hash", "approvers") if k in action}
    if action["type"] == "grant_exception": body["valid_days"] = 30
    return {"method": "POST", "path": "/grc/%s" % path, "body": body, "idempotency_key": action["idempotency_key"]}

@activity.defn
def it_write_back(action: dict) -> dict:
    """Always a dry run: the demo has no GRC or ticketing tool to send to, so the exact call is recorded and nothing is sent, whatever WRITE_BACK says."""
    return {"mode": "dry-run", "would_send": build_it_call(action), "note": "not sent: this demo has no GRC or ticketing tool connected"}

@activity.defn
def rca_gather_facts(claim_id: int) -> dict:
    return rca_facts.gather(claim_id)

@activity.defn
def rca_rules_gate(facts: dict, initiator: str) -> dict:
    return rca_rules.gate(facts, initiator)

@activity.defn
def rca_recommend(facts: dict, gate: dict) -> dict:
    return rec_mod.recommend(facts, gate, "incident")

def build_rca_call(action: dict) -> dict:
    """The exact call to the (not yet connected) briefing tool for an approved action: what the approver's hash covers and what the dry run shows."""
    path = {"publish": "publish", "hold": "hold"}[action["type"]]
    body = {k: action[k] for k in ("claim_id", "case_id", "brief_digest", "exposure_level", "exposure_set_by", "payload_hash", "approvers", "waiting_for") if k in action}
    return {"method": "POST", "path": "/briefs/%s/%s" % (action["case_id"], path), "body": body, "idempotency_key": action["idempotency_key"]}

@activity.defn
def rca_write_back(action: dict) -> dict:
    """Always a dry run: no distribution or briefing tool is connected, so the exact call is recorded and nothing is sent, whatever WRITE_BACK says."""
    return {"mode": "dry-run", "would_send": build_rca_call(action), "note": "not sent: no briefing or distribution tool is connected"}

@activity.defn
def assess_gather_facts(system_id: int) -> dict:
    return assess_facts.gather(system_id)

@activity.defn
def assess_rules_gate(facts: dict, initiator: str) -> dict:
    return assess_rules.gate(facts, initiator)

@activity.defn
def assess_recommend(facts: dict, gate: dict) -> dict:
    return rec_mod.recommend(facts, gate, "assessment")

@activity.defn
def assess_write_back(action: dict, prop: dict) -> dict:
    return register_write.write(action, prop)

@activity.defn
def major_gather_facts(incident_id: int) -> dict:
    return major_facts.gather(incident_id)

@activity.defn
def major_rules_gate(facts: dict, initiator: str) -> dict:
    return major_rules.gate(facts, initiator)

@activity.defn
def major_write_back(action: dict, classified_at: str) -> dict:
    return register_write.write_major(action, classified_at)

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
