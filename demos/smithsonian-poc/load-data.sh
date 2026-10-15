#!/bin/bash
# Loads the Smithsonian Open Access sample into a local Postgres database "si_poc" and (after the vocabulary build, see
# README) adds the concept column. It also starts a local MinIO (a stand-in for Amazon S3) and puts the museum directory CSV in it,
# so the demo has two real data sources: Postgres (the records) and object storage (a CSV). Usage: demo-smithsonian-poc/load-data.sh
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

# ---- second data source: a CSV in object storage (MinIO simulates S3 locally; needs Docker)
MINIO_NAME=si-poc-minio; MINIO_PORT=19110; MINIO_CONSOLE=19111
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. The demo's second data source (a CSV in object storage) needs it: start Docker Desktop and run this again." >&2
  exit 1
fi
if [ -z "$(docker ps -q -f name=^${MINIO_NAME}$)" ]; then
  docker rm -f "$MINIO_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$MINIO_NAME" -p 127.0.0.1:$MINIO_PORT:9000 -p 127.0.0.1:$MINIO_CONSOLE:9001 \
    -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin quay.io/minio/minio server /data --console-address ":9001" >/dev/null
fi
for i in $(seq 1 30); do curl -s -m2 "http://127.0.0.1:$MINIO_PORT/minio/health/ready" >/dev/null 2>&1 && break; sleep 1; done
S3="http://127.0.0.1:$MINIO_PORT"; AUTH=(--aws-sigv4 "aws:amz:us-east-1:s3" --user minioadmin:minioadmin)
curl -s -o /dev/null "${AUTH[@]}" -X PUT "$S3/si-poc"
curl -s -o /dev/null -w "museum directory uploaded to s3://si-poc/museums.csv (HTTP %{http_code})\n" "${AUTH[@]}" -X PUT --data-binary @data-src/si_museums.csv "$S3/si-poc/museums.csv"
