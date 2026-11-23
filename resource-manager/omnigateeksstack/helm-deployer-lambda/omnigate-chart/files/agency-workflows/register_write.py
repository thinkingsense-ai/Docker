"""The one write the product makes by itself: a new row in its own risk register (never an edit; register.assessments refuses UPDATE and DELETE). Kept apart from activities.py so it is unit-tested
without the Temporal SDK. The writer is the register_writer role, which can only INSERT. REGISTER_WRITE=dry-run records the exact row and adds nothing."""
import json, os, subprocess
import assess_rules

REGISTER_WRITE = os.environ.get("REGISTER_WRITE", "live")        # live (default): add the row to the register. dry-run: record the exact row and add nothing.
INSERT = """INSERT INTO register.assessments (item_type, item_ref, node_id, rating, likelihood_band, impact_band, likelihood_inputs, impact_inputs, control_evidence, set_by, role, run_id, evidence_digest, source)
SELECT x.item_type, x.item_ref, x.node_id, x.rating, x.likelihood_band, x.impact_band, x.likelihood_inputs, x.impact_inputs, x.control_evidence, x.set_by, x.role, x.run_id, x.evidence_digest, 'workflow'
FROM json_to_record(:'payload'::json) AS x(item_type text, item_ref text, node_id text, rating text, likelihood_band text, impact_band text, likelihood_inputs text, impact_inputs text, control_evidence text, set_by text, role text, run_id text, evidence_digest text)
ON CONFLICT (run_id) WHERE run_id IS NOT NULL DO NOTHING RETURNING assessment_id;"""

def build_register_row(action: dict, prop: dict) -> dict:
    """The exact register row an approved record action adds. Attribution is the approvers of this run, as the Server's workflow API delivered them; the role is always the second line."""
    return {"item_type": action["item_type"], "item_ref": action["item_ref"], "node_id": action["category"], "rating": action["rating"], "likelihood_band": action["likelihood"], "impact_band": action["impact"],
            "likelihood_inputs": prop["likelihood_inputs"][:300], "impact_inputs": prop["impact_inputs"][:300], "control_evidence": prop["control_evidence"][:400],
            "set_by": ", ".join(action["approvers"])[:120], "role": "second", "run_id": action["idempotency_key"], "evidence_digest": action["proposal_digest"]}

def write(action, prop):
    """The one write the product makes by itself: a new row in its own register (never an edit; the table refuses UPDATE and DELETE). A hold adds nothing. The writer is the register_writer role,
    which can only INSERT. REGISTER_WRITE=dry-run records the exact row and adds nothing."""
    if action["type"] != assess_rules.RECORD: return {"mode": "no-write", "note": "a hold adds nothing to the register"}
    row = build_register_row(action, prop)
    if REGISTER_WRITE != "live": return {"mode": "dry-run", "would_send": {"method": "INSERT", "path": "register.assessments", "body": row}, "note": "not written: REGISTER_WRITE is dry-run"}
    env = dict(os.environ, PGPASSWORD=os.environ.get("REGISTER_DB_PASSWORD", ""))
    cmd = ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-v", "payload=" + json.dumps(row), "-h", os.environ.get("REGISTER_DB_HOST", "postgres"), "-p", os.environ.get("REGISTER_DB_PORT", "5432"),
           "-U", os.environ.get("REGISTER_DB_USER", "register_writer"), "-d", os.environ.get("REGISTER_DB_NAME", "postgres"), "-f", "-"]
    r = subprocess.run(cmd, input=INSERT, capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0: raise RuntimeError("the register write failed: %s" % r.stderr.strip()[:200])
    got = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    return {"mode": "live", "sent": {"method": "INSERT", "path": "register.assessments #%s" % got if got else "register.assessments (already written by this run)"}, "assessment_id": got or None}


MAJOR_INSERT = """INSERT INTO register.major_incident_decisions (incident_id, decision, classified_at, regimes, set_by, role, run_id, evidence_digest, source)
SELECT x.incident_id, 'major', x.classified_at::timestamptz, x.regimes, x.set_by, x.role, x.run_id, x.evidence_digest, 'workflow'
FROM json_to_record(:'payload'::json) AS x(incident_id int, classified_at text, regimes text, set_by text, role text, run_id text, evidence_digest text)
ON CONFLICT DO NOTHING RETURNING decision_id;"""


def build_major_row(action, classified_at):
    """The exact row an approved decision adds. classified_at is when the approval completed, which is when the clocks start."""
    return {"incident_id": action["incident_id"], "classified_at": classified_at, "regimes": ",".join(action["regimes"])[:60], "set_by": ", ".join(action["approvers"])[:120], "role": "second",
            "run_id": action["idempotency_key"], "evidence_digest": action["proposal_digest"]}


def _psql(sql, row):
    env = dict(os.environ, PGPASSWORD=os.environ.get("REGISTER_DB_PASSWORD", ""))
    cmd = ["psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-v", "payload=" + json.dumps(row), "-h", os.environ.get("REGISTER_DB_HOST", "postgres"), "-p", os.environ.get("REGISTER_DB_PORT", "5432"),
           "-U", os.environ.get("REGISTER_DB_USER", "register_writer"), "-d", os.environ.get("REGISTER_DB_NAME", "postgres"), "-f", "-"]
    r = subprocess.run(cmd, input=sql, capture_output=True, text=True, env=env, timeout=30)
    if r.returncode != 0: raise RuntimeError("the register write failed: %s" % r.stderr.strip()[:200])
    return r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""


def write_major(action, classified_at):
    """Adds ONE decision row as register_writer (INSERT only). Nothing is sent to any regulator. REGISTER_WRITE=dry-run records the row without adding it."""
    row = build_major_row(action, classified_at)
    if REGISTER_WRITE != "live": return {"mode": "dry-run", "would_send": {"method": "INSERT", "path": "register.major_incident_decisions", "body": row}, "note": "not written: REGISTER_WRITE is dry-run"}
    got = _psql(MAJOR_INSERT, row)
    return {"mode": "live", "sent": {"method": "INSERT", "path": "register.major_incident_decisions #%s" % got if got else "register.major_incident_decisions (already recorded)"}, "decision_id": got or None}
