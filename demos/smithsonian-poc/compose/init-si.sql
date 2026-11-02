-- Runs once, on a fresh Postgres volume (the base compose file's Postgres mounts everything in /docker-entrypoint-initdb.d).
-- Loads the Smithsonian Open Access sample into its own database, si_poc, the same table the Mac demo (load-data.sh) builds,
-- including the subject-vocabulary "concept" column (load-vocabulary.sh does that step by hand on the Mac).
CREATE DATABASE si_poc;
\connect si_poc
CREATE TABLE si_topics (record_id text, title text, unit_code text, topic text, cc0 boolean, image_url text, record_link text, culturally_sensitive boolean DEFAULT false);
\copy si_topics(record_id,title,unit_code,topic,cc0,image_url,record_link) FROM '/si-data/si_open_access_sample.csv' CSV HEADER
UPDATE si_topics SET image_url = NULL WHERE image_url = '';
CREATE INDEX ON si_topics(unit_code);
CREATE INDEX ON si_topics(topic);

CREATE TEMP TABLE cm(canonical_concept text, member_label text, source_units text, occurrence_count int, confidence float, status text);
\copy cm FROM '/si-data/vocabulary-concepts.csv' CSV HEADER
ALTER TABLE si_topics ADD COLUMN concept text;
UPDATE si_topics t SET concept = COALESCE((SELECT canonical_concept FROM cm WHERE member_label = t.topic AND status = 'AUTO_ACCEPTED' LIMIT 1), t.topic);

-- The app reads as a SELECT-only account, not the postgres superuser (the same posture the cloud stacks use), so no question can change the data.
CREATE ROLE omnigate_ro LOGIN PASSWORD 'omnigate_ro';
GRANT CONNECT ON DATABASE si_poc TO omnigate_ro;
GRANT USAGE ON SCHEMA public TO omnigate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO omnigate_ro;
