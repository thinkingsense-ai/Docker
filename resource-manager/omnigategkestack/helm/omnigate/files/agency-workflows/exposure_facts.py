"""Governed facts for the exposure rating: the five approved questions of the IT-risk Exposure screen, run through POST /api/query so access policy and the audit log apply.
The estate is SIMULATED (demos/it-risk-estate): no real firm system. The SQL is the approved questions' reference SQL with the case id as a parameter; a test keeps it equal to
demos/it-risk-estate/demo-questions-estate.json. EXPOSURE_TABLE_PREFIX (default RCA_TABLE_PREFIX) is the connector prefix ("pg." in the all-packs stack); EXPOSURE_ENABLED=off skips the rating
on a stack that has no estate schema (the brief is then rated "not assessed" and publishes without it)."""
import os, re
import facts as base

KEYS = ("systems", "access", "places", "exposures", "recovery")
SQL = {   # the approved questions' reference SQL (demos/it-risk-estate/demo-questions-estate.json) with the connector prefix {p} and the case {case} as parameters; a test keeps them equal
 'systems': "SELECT s.name AS system, s.technology, s.business_criticality AS tier, s.owned_by AS owner_team, s.environment, s.hosting FROM {p}estate.systems s JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' ORDER BY s.business_criticality, s.system_id",
 'access': "SELECT s.name AS resource, 'system' AS kind, s.data_class, a.principal AS reachable_by, a.people, a.level, CASE WHEN a.principal = s.owned_by THEN 'owner team' ELSE 'wider than the owner team' END AS reach FROM {p}estate.systems s JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' JOIN {p}estate.access_paths a ON a.system_id = s.system_id WHERE s.data_class IN ('restricted','confidential') UNION ALL SELECT b.name AS resource, 'bucket' AS kind, b.data_class, CASE WHEN b.public_read THEN 'anyone (public read)' ELSE b.write_group END AS reachable_by, b.write_people AS people, 'write' AS level, CASE WHEN b.public_read OR b.write_group <> s.owned_by THEN 'wider than the owner team' ELSE 'owner team' END AS reach FROM {p}estate.buckets b JOIN {p}estate.systems s ON s.system_id = b.system_id JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' WHERE b.data_class IN ('restricted','confidential')",
 'places': "SELECT s.name AS system, 'SharePoint: ' || i.site || ' / ' || i.library AS location, i.name AS item, i.kind, i.shared_with AS visible_to, i.audience AS people FROM {p}estate.sharepoint_items i JOIN {p}estate.systems s ON s.system_id = i.system_id JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' WHERE i.kind IN ('runbook','credential','recovery') UNION ALL SELECT s.name AS system, 'Slack: ' || m.channel AS location, m.excerpt AS item, m.kind, m.channel_kind AS visible_to, m.members AS people FROM {p}estate.slack_messages m JOIN {p}estate.systems s ON s.system_id = m.system_id JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' WHERE m.kind IN ('runbook','credential','recovery')",
 'exposures': "SELECT s.name AS system, 'security patch overdue' AS finding, p.advisory AS detail, p.severity, p.days_overdue AS days FROM {p}estate.patches p JOIN {p}estate.systems s ON s.system_id = p.system_id JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' WHERE p.applied_on IS NULL AND p.days_overdue > 0 UNION ALL SELECT s.name AS system, 'change without a pre-production test' AS finding, c.summary AS detail, c.change_type AS severity, c.days_ago AS days FROM {p}estate.changes c JOIN {p}estate.systems s ON s.system_id = c.system_id JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' WHERE c.preprod_tested = FALSE AND c.days_ago <= 30",
 'recovery': "SELECT s.name AS system, s.business_criticality AS tier, (SELECT COUNT(*) FROM {p}estate.dependencies d WHERE d.system_id = s.system_id) AS dependents, r.tested_on, r.result, r.rto_target_minutes, r.rto_actual_minutes, r.days_since_test FROM {p}estate.systems s JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = '{case}' LEFT JOIN {p}estate.recovery_tests r ON r.system_id = s.system_id ORDER BY s.business_criticality, s.system_id",
}


def enabled(): return os.environ.get("EXPOSURE_ENABLED", "on").lower() not in ("off", "false", "0", "no")


def _prefix(): return os.environ.get("EXPOSURE_TABLE_PREFIX", os.environ.get("RCA_TABLE_PREFIX", ""))
def _query(sql): return base.query_table(sql, os.environ.get("RCA_WORKSPACE"))
def _table(sql):
    cols, rows = _query(sql); return {"columns": cols, "rows": rows}


def gather(case_id):
    """The five answers for a case, or {"assessed": False, "reason": ...} when the case has no scenario technologies here (nothing to assess) or the estate is switched off, or
    {"assessed": False, "error": ...} when the estate could not be read (the gate then blocks publishing: an unread estate is not a clean one)."""
    if not re.fullmatch(r"[a-z0-9-]{1,40}", str(case_id)): raise RuntimeError("unexpected case id")
    if not enabled(): return {"assessed": False, "reason": "the estate is not connected on this stack (EXPOSURE_ENABLED is off)"}
    p = _prefix()
    try:
        _, n = _query("SELECT COUNT(*) AS n FROM %sestate.scenario_technology WHERE case_id = '%s'" % (p, case_id))
        if not n or int(n[0][0]) == 0: return {"assessed": False, "reason": "no technology in the estate is mapped to this case, so there is no exposure to rate"}
        return {"assessed": True, "case_id": case_id, "answers": {k: _table(SQL[k].format(p=p, case=case_id)) for k in KEYS}}
    except Exception as e:
        return {"assessed": False, "error": "the estate could not be read: %s" % str(e)[:200]}
