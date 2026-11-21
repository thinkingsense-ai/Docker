"""Governed facts for one major-incident decision: the firm's incident, any decision already recorded for it, the regulators the firm declared, and the notification rules. Every row comes through
POST /api/query (access policy and the audit log apply). MAJOR_TABLE_PREFIX (default RCA_TABLE_PREFIX) is the connector prefix ("pg." in the all-packs stack). The incidents are INVENTED incidents of the simulated firm."""
import os
import facts as base


def _prefix(): return os.environ.get("MAJOR_TABLE_PREFIX", os.environ.get("RCA_TABLE_PREFIX", ""))
def _q(sql): return base.query(sql, os.environ.get("RCA_WORKSPACE"))


def gather(incident_id):
    n = int(incident_id); p = _prefix()
    inc = _q("SELECT incident_id, title, system_id, awareness_at, summary FROM %sregister.firm_incidents WHERE incident_id = %d" % (p, n))
    if not inc: raise RuntimeError("incident %d not found" % n)
    dec = _q("SELECT classified_at, regimes, set_by FROM %sregister.major_incident_decisions WHERE incident_id = %d" % (p, n))
    prof = _q("SELECT regulator, declared FROM %sregister.firm_profile ORDER BY regulator" % p)
    rules = _q("SELECT rule_id, regulator, jurisdiction, seq, stage, title, hours, starts_from, also_within_hours_of_awareness, report_kind, source, checked, note FROM %sregister.notification_rules ORDER BY regulator, seq" % p)
    return {"incident": inc[0], "decision": dec[0] if dec else None, "profile": prof, "rules": rules}
