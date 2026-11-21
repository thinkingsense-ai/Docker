"""The adapter's only database access: the `psql` client, connecting as the feed_writer role (demos/it-risk-rca/grant-rca.sql), which can write the feed tables and the candidates it creates and nothing else.
Values reach SQL only as one JSON document bound to a psql variable (`:'payload'`, which psql quotes as a literal), never by string-building, so a headline cannot change a statement.
`psql` rather than a Python driver keeps the image dependency-free (the driver would be one more licence on the register)."""
import json, os, subprocess

UPSERT_SOURCES = """
INSERT INTO rca.feed_sources (source_id, name, url, kind, enabled)
  SELECT x.id, x.name, x.url, x.kind, TRUE FROM jsonb_to_recordset(:'payload'::jsonb) AS x(id text, name text, url text, kind text)
  ON CONFLICT (source_id) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url, kind = EXCLUDED.kind, enabled = TRUE;
UPDATE rca.feed_sources SET enabled = FALSE WHERE source_id NOT IN (SELECT x.id FROM jsonb_to_recordset(:'payload'::jsonb) AS x(id text));
"""
STATES = "SELECT COALESCE(jsonb_object_agg(source_id, jsonb_build_object('etag', etag, 'last_modified', last_modified)), '{}'::jsonb) FROM rca.feed_sources;"
RECORD_RUN = """
UPDATE rca.feed_sources s SET last_attempt_at = x.at, last_status = x.status, last_error = x.error, items_last_run = x.items,
  last_success_at = CASE WHEN x.success THEN x.at ELSE s.last_success_at END,
  etag = CASE WHEN x.success THEN x.etag ELSE s.etag END, last_modified = CASE WHEN x.success THEN x.last_modified ELSE s.last_modified END
  FROM jsonb_to_record(:'payload'::jsonb) AS x(id text, at timestamp, status text, error text, items int, success boolean, etag text, last_modified text) WHERE s.source_id = x.id;
"""
INSERT_ITEMS = """
INSERT INTO rca.feed_items (source_id, url, title, published_at, first_seen_at, seen_hash, matched, claim_type, match_terms)
  SELECT x.source_id, x.url, x.title, x.published_at, x.first_seen_at, x.seen_hash, x.matched, x.claim_type, x.match_terms
  FROM jsonb_to_recordset(:'payload'::jsonb) AS x(source_id text, url text, title text, published_at timestamp, first_seen_at timestamp, seen_hash text, matched boolean, claim_type text, match_terms text)
  ON CONFLICT (seen_hash) DO NOTHING RETURNING item_id;
"""
RECENT = """
SELECT COALESCE(jsonb_agg(r), '[]'::jsonb) FROM (
  SELECT i.item_id, i.title, COALESCE(i.published_at, i.first_seen_at) AS "when", i.claim_type, s.name AS source,
         (SELECT cf.candidate_id FROM rca.candidate_feed_items cf WHERE cf.item_id = i.item_id ORDER BY cf.candidate_id LIMIT 1) AS candidate_id
  FROM rca.feed_items i JOIN rca.feed_sources s ON s.source_id = i.source_id
  WHERE i.matched AND COALESCE(i.published_at, i.first_seen_at) >= (:'payload'::jsonb ->> 'since')::timestamp ORDER BY i.item_id LIMIT 500) r;
"""
APPLY = """
WITH g AS (SELECT * FROM jsonb_to_recordset(:'payload'::jsonb) AS t(cid int, key int, items jsonb, title text, claim_type text, first_seen date, summary text, lead bigint)),
ids AS (SELECT g.key, COALESCE(g.cid, nextval('rca.candidate_seq'))::int AS cid, g.items, g.title, g.claim_type, g.first_seen, g.summary, g.lead FROM g),
ins AS (INSERT INTO rca.candidates (candidate_id, case_id, claim_id, title, claim_type, status, first_seen, summary, lead_item_id)
        SELECT cid, NULL, NULL, title, claim_type, 'not_yet_traced', first_seen, summary, lead FROM ids WHERE cid NOT IN (SELECT candidate_id FROM rca.candidates) RETURNING candidate_id),
upd AS (UPDATE rca.candidates c SET title = ids.title, claim_type = ids.claim_type, first_seen = ids.first_seen, summary = ids.summary, lead_item_id = ids.lead
        FROM ids WHERE c.candidate_id = ids.cid AND c.status = 'not_yet_traced' AND c.case_id IS NULL RETURNING c.candidate_id)
INSERT INTO rca.candidate_feed_items (candidate_id, item_id) SELECT ids.cid, v::bigint FROM ids, jsonb_array_elements_text(ids.items) v ON CONFLICT DO NOTHING;
"""
PURGE = "DELETE FROM rca.feed_items WHERE first_seen_at < (:'payload'::jsonb ->> 'before')::timestamp AND item_id NOT IN (SELECT item_id FROM rca.candidate_feed_items);"


class PsqlStore:
    def __init__(self, env=None): self.env = dict(os.environ, **(env or {}))

    def _run(self, sql, payload=None):
        cmd = ["psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1"] + (["-v", "payload=" + json.dumps(payload, default=str)] if payload is not None else []) + ["-f", "-"]
        r = subprocess.run(cmd, input=sql, capture_output=True, text=True, env=self.env, timeout=120)
        if r.returncode: raise RuntimeError("psql failed: %s" % r.stderr.strip()[:300])
        return r.stdout

    def upsert_sources(self, sources): self._run(UPSERT_SOURCES, sources)
    def source_states(self): return json.loads(self._run(STATES) or "{}")
    def record_run(self, row): self._run(RECORD_RUN, row)
    def insert_items(self, items): return len([l for l in self._run(INSERT_ITEMS, items).split() if l.isdigit()]) if items else 0
    def recent_matched(self, since): return json.loads(self._run(RECENT, {"since": since}) or "[]")
    def apply_clusters(self, groups):
        if groups: self._run(APPLY, [{"cid": g["candidate_id"], "key": i, "items": g["item_ids"], "title": g["title"], "claim_type": g["claim_type"], "first_seen": g["first_seen"], "summary": g["summary"], "lead": g["lead_item_id"]} for i, g in enumerate(groups)])
    def purge(self, before): self._run(PURGE, {"before": before})
