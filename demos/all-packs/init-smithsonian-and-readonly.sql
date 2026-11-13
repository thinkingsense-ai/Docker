-- Runs after the pack seeds, once, on a fresh Postgres volume. Loads the Smithsonian Open Access sample as the `smithsonian` schema of the
-- same database as the other packs (one Postgres connector serves them all), then makes the app's account SELECT-only.
CREATE SCHEMA IF NOT EXISTS smithsonian;
CREATE TABLE smithsonian.si_topics (record_id text, title text, unit_code text, topic text, cc0 boolean, image_url text, record_link text, culturally_sensitive boolean DEFAULT false);
\copy smithsonian.si_topics(record_id,title,unit_code,topic,cc0,image_url,record_link) FROM '/si-data/si_open_access_sample.csv' CSV HEADER
UPDATE smithsonian.si_topics SET image_url = NULL WHERE image_url = '';
CREATE INDEX ON smithsonian.si_topics(unit_code);
CREATE INDEX ON smithsonian.si_topics(topic);

CREATE TEMP TABLE cm(canonical_concept text, member_label text, source_units text, occurrence_count int, confidence float, status text);
\copy cm FROM '/si-data/vocabulary-concepts.csv' CSV HEADER
ALTER TABLE smithsonian.si_topics ADD COLUMN concept text;
UPDATE smithsonian.si_topics t SET concept = COALESCE((SELECT canonical_concept FROM cm WHERE member_label = t.topic AND status = 'AUTO_ACCEPTED' LIMIT 1), t.topic);

-- The app reads as a SELECT-only account, not the postgres superuser, so no question can change the data.
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omnigate_ro') THEN CREATE ROLE omnigate_ro LOGIN PASSWORD 'omnigate_ro'; END IF; END $$;
GRANT CONNECT ON DATABASE postgres TO omnigate_ro;
GRANT USAGE ON SCHEMA suppliers, inventory, procurement, risk, smithsonian, bom, treasury TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA suppliers, inventory, procurement, risk, smithsonian, bom, treasury TO omnigate_ro;
