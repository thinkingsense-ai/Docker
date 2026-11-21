"""Governed facts for one risk-assessment run: the system's row from the Priorities question (the same SQL the screen asks, one system), the register's current rating for it, and the exposure rating
of the case when the estate is connected. Every row comes through POST /api/query, so access policy and the audit log apply. ASSESS_TABLE_PREFIX (default RCA_TABLE_PREFIX) is the connector prefix ("pg." in the
all-packs stack). A test keeps SQL equal to demos/it-risk-estate/demo-questions-priorities.json."""
import os, re
import facts as base
import exposure_facts, exposure_rules

SQL = "SELECT s.system_id, s.name AS system, s.business_criticality AS tier, s.environment, s.data_class, s.internet_facing, COALESCE(d.dependents, 0) AS dependents, s.end_of_support, COALESCE(p.open_patches, 0) AS open_patches, COALESCE(p.known_exploited_open, 0) AS known_exploited_open, p.max_epss_open, p.max_cvss_open, COALESCE(c.untested_changes, 0) AS untested_changes, r.days_since_test, r.result AS recovery_result, COALESCE(k.credentials_wide, 0) AS credentials_wide, CASE WHEN t.technology IS NULL THEN 0 ELSE 1 END AS in_scenario, s.loss_event, g.rating AS registered_rating, g.set_by AS registered_by, g.assessed_at AS registered_at FROM {p}estate.systems s LEFT JOIN (SELECT system_id, COUNT(*) AS dependents FROM {p}estate.dependencies GROUP BY system_id) d ON d.system_id = s.system_id LEFT JOIN (SELECT system_id, COUNT(*) AS open_patches, SUM(CASE WHEN known_exploited THEN 1 ELSE 0 END) AS known_exploited_open, MAX(epss) AS max_epss_open, MAX(cvss_score) AS max_cvss_open FROM {p}estate.patches WHERE applied_on IS NULL GROUP BY system_id) p ON p.system_id = s.system_id LEFT JOIN (SELECT system_id, COUNT(*) AS untested_changes FROM {p}estate.changes WHERE preprod_tested = FALSE GROUP BY system_id) c ON c.system_id = s.system_id LEFT JOIN {p}estate.recovery_tests r ON r.system_id = s.system_id LEFT JOIN (SELECT system_id, COUNT(*) AS credentials_wide FROM (SELECT system_id FROM {p}estate.sharepoint_items WHERE kind = 'credential' AND shared_with IN ('department','company','external','anyone') UNION ALL SELECT system_id FROM {p}estate.slack_messages WHERE kind = 'credential' AND channel_kind IN ('public','external')) w WHERE system_id IS NOT NULL GROUP BY system_id) k ON k.system_id = s.system_id LEFT JOIN {p}estate.scenario_technology t ON t.technology = s.technology AND t.case_id = 'nov-2026-cluster' LEFT JOIN (SELECT a.item_ref, a.rating, a.set_by, a.assessed_at FROM {p}register.assessments a JOIN (SELECT item_ref, MAX(assessment_id) AS latest FROM {p}register.assessments WHERE item_type = 'system' GROUP BY item_ref) m ON m.latest = a.assessment_id) g ON g.item_ref = s.name {where}ORDER BY s.business_criticality, s.system_id"
CASE = os.environ.get("ASSESS_EXPOSURE_CASE", "nov-2026-cluster")


def _prefix(): return os.environ.get("ASSESS_TABLE_PREFIX", os.environ.get("RCA_TABLE_PREFIX", ""))
def _query(sql): return base.query_table(sql, os.environ.get("RCA_WORKSPACE"))


def gather(system_id):
    n = int(system_id); p = _prefix()
    cols, rows = _query(SQL.format(p=p, where="WHERE s.system_id = %d " % n))
    if not rows: raise RuntimeError("system %d not found" % n)
    row = dict(zip(cols, rows[0])); name = str(row.get("system", ""))
    cur = _query("SELECT rating, set_by, assessed_at, node_id FROM %sregister.assessments WHERE item_type = 'system' AND item_ref = '%s' ORDER BY assessment_id DESC LIMIT 1" % (p, name.replace("'", "''")))[1]
    register = dict(zip(("rating", "set_by", "assessed_at", "node_id"), (str(x) for x in cur[0]))) if cur else None
    exposure = {"assessed": False, "reason": "the estate exposure rating is off on this stack"}
    if exposure_facts.enabled():
        e = exposure_facts.gather(CASE)
        if e.get("assessed"):
            r = exposure_rules.rate(e["answers"]); exposure = {"assessed": True, "case_id": CASE, "level": r["level"], "complete": r["complete"], "sentence": r["sentence"]}
        else: exposure = {"assessed": False, "reason": e.get("error") or e.get("reason", "not assessed")}
    return {"system_id": n, "table": {"columns": cols, "rows": [list(rows[0])]}, "register": register, "exposure": exposure}
