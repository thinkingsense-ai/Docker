"""Governed facts for one incident-brief run: every row comes from thinking sense's own query path (POST /api/query), so access policy and the audit log apply and nothing is copied.
The run is keyed by a claim id (rca.claims): the claim under test, and through it the case (a cluster of incidents). RCA_TABLE_PREFIX is the connector prefix the stack uses: "pg." in the
all-packs stack (tables are addressed connector.schema.table), empty on a stack with one source per schema."""
import os, re
import facts as base

def query(sql): return base.query(sql, os.environ.get("RCA_WORKSPACE"))             # the IT-risk Workspace on a stack whose Workspaces cover every source; unset elsewhere


def T(name): return "%srca.%s" % (os.environ.get("RCA_TABLE_PREFIX", ""), name)


def gather(claim_id):
    n = int(claim_id)
    c = query("SELECT claim_id, case_id, claim, verdict, open_incidents, note FROM %s WHERE claim_id = %d" % (T("claims"), n))
    if not c: raise RuntimeError("claim %d not found" % n)
    claim = c[0]; case = claim["case_id"]
    if not re.fullmatch(r"[a-z0-9-]{1,40}", str(case)): raise RuntimeError("unexpected case id")
    incidents = query("SELECT e.event_id, e.operator, e.label, e.when_text, l.link_id, l.statement AS cause, l.grade, COUNT(ls.signal_id) AS sources FROM %s e JOIN %s l ON l.event_id = e.event_id AND l.layer = 'cause' "
                      "LEFT JOIN %s ls ON ls.link_id = l.link_id WHERE e.case_id = '%s' GROUP BY e.event_id, e.operator, e.label, e.when_text, l.link_id, l.statement, l.grade ORDER BY e.event_id"
                      % (T("events"), T("links"), T("link_sources"), case))
    open_links = query("SELECT link_id, layer, statement, grade, reason FROM %s WHERE case_id = '%s' AND grade IN ('inferred','to_be_tested') ORDER BY link_id" % (T("links"), case))
    controls = query("SELECT l.link_id, l.statement AS root_condition, l.grade, m.owning_control, m.owner_role, m.framework, m.category FROM %s l JOIN %s m ON m.root_condition = l.control_root "
                     "WHERE l.case_id = '%s' AND l.layer = 'root_condition' ORDER BY l.link_id" % (T("links"), T("control_map"), case))
    speakers = query("SELECT e.operator, s.speaker, s.speaker_kind, s.publisher FROM %s l JOIN %s e ON e.event_id = l.event_id JOIN %s ls ON ls.link_id = l.link_id JOIN %s s ON s.signal_id = ls.signal_id "
                     "WHERE l.layer = 'cause' AND l.case_id = '%s' ORDER BY e.event_id" % (T("links"), T("events"), T("link_sources"), T("signals"), case))
    for i in incidents: i["sources"] = int(i["sources"])
    rows = query("SELECT l.link_id, l.layer, l.grade, l.control_root, e.operator AS who, ls.signal_id, ls.relation, ls.asserts, s.speaker, s.speaker_kind, s.source_kind FROM %s l LEFT JOIN %s e ON e.event_id = l.event_id "
                 "LEFT JOIN %s ls ON ls.link_id = l.link_id LEFT JOIN %s s ON s.signal_id = ls.signal_id WHERE l.case_id = '%s' ORDER BY l.link_id, ls.signal_id" % (T("links"), T("events"), T("link_sources"), T("signals"), case))
    byid = {}
    for r in rows:
        k = int(r["link_id"]); l = byid.setdefault(k, {"link_id": k, "layer": r["layer"], "grade": r["grade"], "has_control": r.get("control_root") not in (None, ""), "who": r.get("who") or "case", "sources": []})
        if r.get("signal_id") not in (None, ""): l["sources"].append({k2: r.get(k2) for k2 in ("signal_id", "relation", "asserts", "speaker", "speaker_kind", "source_kind")})
    links = [byid[k] for k in sorted(byid)]
    return {"claim": claim, "case_id": case, "incidents": incidents, "open_links": open_links, "controls": controls, "speakers": speakers, "links": links}
