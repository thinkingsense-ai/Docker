"""The evidence block of an answer (spec FR-11), built only from what the Server's own events said, plus how the layer applied the scope."""
class Evidence:
    def __init__(self, workspace, pack, scope, started):
        self.workspace, self.pack, self.scope, self.started = workspace, pack, scope, started
        self.backends, self.origin, self.sql, self.model, self.checks = [], None, None, None, []
        self.sources_hidden = self.sql_hidden = self.truncated = False; self.no_sources = False; self.warnings = []
        self.step_sql = []

    def see(self, ev):
        s = ev.get("step")
        if s == "planned":
            self.backends = ev.get("backends") or []; self.origin = ev.get("source"); self.sources_hidden = bool(ev.get("sourcesHidden"))
        elif s == "sql" and not ev.get("rejected"):
            self.sql = ev.get("sql"); self.model = ev.get("model") or self.model; self.sql_hidden = bool(ev.get("sqlHidden"))
        elif s == "check": self.checks.append({"id": ev.get("id"), "status": ev.get("status")})
        elif s == "done":
            self.sql = ev.get("sql") or self.sql; self.model = ev.get("model") or self.model; self.truncated = bool(ev.get("truncated"))
            self.sql_hidden = bool(ev.get("sqlHidden")) or self.sql_hidden; self.no_sources = bool(ev.get("answeredWithoutDataSources"))

    def build(self, now):
        w = list(self.warnings)
        if self.pack and self.scope == "server-backends": w.append("The Workspace limits data sources, not schemas: other schemas on the same source are still visible to the planner (Server#109).")
        if self.pack and self.scope == "none": w.append("No Workspace is configured for this pack: the question was asked in All data.")
        if self.pack and self.scope == "agency-hint": w.append("Scope was applied by adding the pack's data sets to the question; the Server does not enforce it.")
        if self.truncated: w.append("The result was cut at the Server's row limit.")
        if self.sql_hidden: w.append("SQL is hidden for this user.")
        if self.sources_hidden: w.append("Source names are hidden for this user.")
        return {"workspace": self.workspace or "all", "pack": self.pack["id"] if self.pack else None, "scopeEnforcedBy": self.scope,
                "sources": [] if self.sources_hidden else [{"id": b} for b in self.backends],
                "intendedSources": self.pack["sources"] if self.pack else None,
                "origin": self.origin, "sql": None if self.sql_hidden else self.sql, "model": self.model, "checks": self.checks,
                "answeredWithoutDataSources": self.no_sources, "elapsedMs": int((now - self.started) * 1000), "warnings": w}
