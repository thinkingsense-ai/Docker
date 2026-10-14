#!/bin/bash
# Loads the Smithsonian Open Access sample into a local Postgres database "si_poc" and (after the vocabulary build, see
# README) adds the concept column. Usage: demo-smithsonian-poc/load-data.sh
set -euo pipefail
cd "$(dirname "$0")"
psql -h 127.0.0.1 -d postgres -qc "DROP DATABASE IF EXISTS si_poc" -c "CREATE DATABASE si_poc"
psql -h 127.0.0.1 -d si_poc -q <<SQL
CREATE TABLE si_topics (record_id text, title text, unit_code text, topic text, cc0 boolean, image_url text, record_link text, culturally_sensitive boolean DEFAULT false);
\copy si_topics(record_id,title,unit_code,topic,cc0,image_url,record_link) FROM 'data-src/si_open_access_sample.csv' CSV HEADER
UPDATE si_topics SET image_url = NULL WHERE image_url = '';
CREATE INDEX ON si_topics(unit_code); CREATE INDEX ON si_topics(topic);
SELECT count(*) AS rows, count(DISTINCT record_id) AS records, count(image_url) AS with_image, count(DISTINCT topic) AS labels FROM si_topics;
SQL
