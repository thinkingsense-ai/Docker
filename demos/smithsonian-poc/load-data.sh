#!/bin/bash
# Loads the Smithsonian Open Access sample into a local Postgres database "si_poc" and (after the vocabulary build, see
# README) adds the concept column. It also starts a local S3-compatible object store (SeaweedFS, a stand-in for Amazon S3) and puts the museum directory CSV in it,
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

# ---- second data source: a CSV in object storage (a local S3-compatible server stands in for Amazon S3; needs Docker)
S3_NAME=si-poc-s3; S3_PORT=19110
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. The demo's second data source (a CSV in object storage) needs it: start Docker Desktop and run this again." >&2
  exit 1
fi
docker rm -f si-poc-minio >/dev/null 2>&1 || true   # the container this demo used before it moved off MinIO
if [ -z "$(docker ps -q -f name=^${S3_NAME}$)" ]; then
  docker rm -f "$S3_NAME" >/dev/null 2>&1 || true
  # MinIO's own image (quay.io/minio/minio) is no longer publicly pullable, so use SeaweedFS in S3 mode: the same pinned image the cloud
  # stacks use for their S3 demo data, and it answers the same path-style S3 calls. Override with SI_S3_IMAGE and SI_S3_ARGS to use another S3 server.
  S3_IMAGE="${SI_S3_IMAGE:-docker.io/chrislusf/seaweedfs@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d}"
  S3_ARGS="${SI_S3_ARGS:-server -dir=/data -s3 -s3.port=9000 -master.volumeSizeLimitMB=1024 -volume.max=0}"
  docker run -d --name "$S3_NAME" -p 127.0.0.1:$S3_PORT:9000 "$S3_IMAGE" $S3_ARGS >/dev/null
fi
for i in $(seq 1 60); do curl -s -m2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$S3_PORT/" 2>/dev/null | grep -q '^[23]' && break; sleep 1; done
S3="http://127.0.0.1:$S3_PORT"; AUTH=(--aws-sigv4 "aws:amz:us-east-1:s3" --user minioadmin:minioadmin)
curl -s -o /dev/null "${AUTH[@]}" -X PUT "$S3/si-poc"
curl -s -o /dev/null -w "museum directory uploaded to s3://si-poc/museums.csv (HTTP %{http_code})\n" "${AUTH[@]}" -X PUT --data-binary @data-src/si_museums.csv "$S3/si-poc/museums.csv"
