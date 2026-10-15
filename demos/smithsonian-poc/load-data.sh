#!/bin/bash
# Loads the Smithsonian Open Access sample into a local Postgres database "si_poc" and (after the vocabulary build, see
# README) adds the concept column. It also starts a small local S3-compatible object store (a stand-in for Amazon S3, in Docker) and puts the museum directory CSV in it,
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

# ---- second data source: a CSV in object storage (a local S3-compatible store simulates S3; needs Docker)
MINIO_NAME=si-poc-minio; MINIO_PORT=19110   # the container keeps its original name; it is SeaweedFS now
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. The demo's second data source (a CSV in object storage) needs it: start Docker Desktop and run this again." >&2
  exit 1
fi
if [ -z "$(docker ps -q -f name=^${MINIO_NAME}$)" ]; then
  docker rm -f "$MINIO_NAME" >/dev/null 2>&1 || true
  # S3-compatible object storage. MinIO's own image (quay.io/minio/minio) is no longer publicly pullable, so use SeaweedFS (the same
  # pinned image the cloud stacks use for their S3 demo data). Override with SI_S3_IMAGE and SI_S3_ARGS to use another S3 server.
  S3_IMAGE="${SI_S3_IMAGE:-docker.io/chrislusf/seaweedfs@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d}"
  S3_ARGS="${SI_S3_ARGS:-server -dir=/data -s3 -s3.port=9000 -master.volumeSizeLimitMB=1024 -volume.max=0}"
  docker run -d --name "$MINIO_NAME" -p 127.0.0.1:$MINIO_PORT:9000 "$S3_IMAGE" $S3_ARGS >/dev/null
fi
for i in $(seq 1 30); do curl -s -m2 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$MINIO_PORT/" 2>/dev/null | grep -q "^[23]" && break; sleep 1; done
# The store has no access control configured, so these keys are placeholders (kept so launch.sh and the upload use the same values).
S3="http://127.0.0.1:$MINIO_PORT"; AUTH=(--aws-sigv4 "aws:amz:us-east-1:s3" --user minioadmin:minioadmin)
curl -s -o /dev/null "${AUTH[@]}" -X PUT "$S3/si-poc"
curl -s -o /dev/null -w "museum directory uploaded to s3://si-poc/museums.csv (HTTP %{http_code})\n" "${AUTH[@]}" -X PUT --data-binary @data-src/si_museums.csv "$S3/si-poc/museums.csv"
