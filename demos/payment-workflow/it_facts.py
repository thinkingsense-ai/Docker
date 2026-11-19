"""Governed facts for one vulnerability: every number comes from thinking sense's own query path (POST /api/query), so access policy and the audit log apply and no data is copied.
The two systems are read one statement each (a statement that joins Postgres and MariaDB would work, but reading them separately keeps each result small and each source named)."""
import facts as base
from it_rules import to_date

query = base.query


def gather(vuln_id):
    n = int(vuln_id)
    v = query("SELECT vuln_id, app_id, cve, cvss, severity, found_on, patch_due, patched_on FROM security.vulnerabilities WHERE vuln_id = %d" % n)
    if not v: raise RuntimeError("vulnerability %d not found" % n)
    v = v[0]
    app = query("SELECT a.app_id, a.name AS application, a.hosting, a.vendor_id, s.service_id, s.name AS service, s.tier, s.owner, s.rto_minutes, s.revenue_per_hour_usd "
                "FROM risk.applications a JOIN risk.business_services s ON s.service_id = a.service_id WHERE a.app_id = %d" % int(v["app_id"]))
    if not app: raise RuntimeError("application %s not found" % v["app_id"])
    app = app[0]; sid = int(app["service_id"])
    vendor = query("SELECT vendor_id, name, tier, country, last_assessed, assessment_rating FROM security.vendors WHERE vendor_id = %d" % int(app["vendor_id"])) if app.get("vendor_id") not in (None, "") else []
    incidents = query("SELECT i.incident_id, a.name AS application, i.started_on, i.duration_minutes, i.severity, i.root_cause FROM risk.incidents i JOIN risk.applications a ON a.app_id = i.app_id "
                      "WHERE a.service_id = %d ORDER BY i.started_on DESC" % sid)
    risks = query("SELECT r.risk_id, r.title, r.category, r.owner, r.residual_score, r.status, ap.max_residual_score FROM risk.risk_register r LEFT JOIN risk.risk_appetite ap ON ap.category = r.category "
                  "WHERE r.service_id = %d ORDER BY r.risk_id" % sid)
    controls = query("SELECT control_id, title, control_type, risk_id, last_tested, test_every_days, last_result FROM risk.controls WHERE risk_id IN (%s) ORDER BY control_id"
                     % ",".join(str(int(r["risk_id"])) for r in risks)) if risks else []
    apps = query("SELECT app_id FROM risk.applications WHERE service_id = %d" % sid)
    others = query("SELECT vuln_id, app_id, cve, cvss, patch_due FROM security.vulnerabilities WHERE patched_on IS NULL AND severity = 'Critical' AND vuln_id <> %d AND app_id IN (%s)"
                   % (n, ",".join(str(int(a["app_id"])) for a in apps))) if apps else []
    svc = {k: app[k] for k in ("service_id", "service", "tier", "owner", "rto_minutes", "revenue_per_hour_usd")}
    return {"vulnerability": v, "application": {k: app[k] for k in ("app_id", "application", "hosting", "vendor_id")}, "service": svc,
            "vendor": vendor[0] if vendor else None, "incidents": incidents, "risks": risks, "controls": controls, "other_open_critical_on_service": others}
