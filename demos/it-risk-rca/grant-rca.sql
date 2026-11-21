-- Runs after init-smithsonian-and-readonly.sql, which creates the omnigate_ro role.
GRANT USAGE ON SCHEMA rca TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA rca TO omnigate_ro;

-- The feed adapter's own role: it may write the feed tables and the candidates it creates, nothing else (it cannot touch the briefs, links or verdicts). The password is a local-demo value:
-- set a different one before this role exists anywhere real.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'feed_writer') THEN CREATE ROLE feed_writer LOGIN PASSWORD 'feed-writer-local'; END IF;
END $$;
GRANT USAGE ON SCHEMA rca TO feed_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON rca.feed_sources, rca.feed_items, rca.candidate_feed_items TO feed_writer;
GRANT SELECT, INSERT, UPDATE ON rca.candidates TO feed_writer;
GRANT USAGE ON rca.candidate_seq, rca.feed_items_item_id_seq TO feed_writer;
