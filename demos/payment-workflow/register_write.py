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

