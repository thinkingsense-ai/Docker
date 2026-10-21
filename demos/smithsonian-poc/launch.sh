#!/bin/bash
# Smithsonian POC demo instance (port 8110). Needs: Postgres db si_poc (see load-data.sh), a built target/omnigate.jar,
# a .env with the cloud model key (optional), and the local model servers (agentic :18090, fast :8092, embeddings :8120 (nomic-embed-text)).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
JAVA_BIN="${JAVA_BIN_OVERRIDE:-$("$HERE/java21.sh")}" || { echo "No Java 21 found (looked at JAVA_HOME, /usr/libexec/java_home -v 21 and the PATH). Install a Java 21 JDK, or set JAVA_HOME to one." >&2; exit 1; }
cd "$HERE/.."
export OMNIGATE_HTTP_PORT=8110 OMNIGATE_GRPC_PORT=7210 OMNIGATE_TLS_PORT=2610 OMNIGATE_ORACLE_PORT=1710 OMNIGATE_MYSQL_PORT=3510 OMNIGATE_PGWIRE_PORT=5610 OMNIGATE_MYWIRE_PORT=3511 OMNIGATE_HTTPS_PORT=8610
export OMNIGATE_DATA_DIR=demo-smithsonian-poc/data
export OMNIGATE_BACKENDS='si=jdbc:postgresql://127.0.0.1:5432/si_poc?currentSchema=public|'"${SI_DB_USER:-$USER}"'|'
# Second data source: the museum directory, a CSV in object storage (a local S3-compatible server standing in for S3). Queried as museums.museums.
export OMNIGATE_BACKENDS="$OMNIGATE_BACKENDS"';museums=jdbc:calcite:model=inline:{"version":"1.0","schemas":[{"name":"museums","type":"custom","factory":"com.omnigate.calcite.s3.S3SchemaFactory","operand":{"provider":"s3","bucket":"si-poc","endpoint":"http://127.0.0.1:19110","pathStyleAccess":true,"accessKeyId":"minioadmin","secretAccessKey":"minioadmin","region":"us-east-1","tables":{"museums":{"key":"museums.csv","format":"csv"}}}}]}|'
export OMNIGATE_ROUTER_SCHEMA_RULES='public:si,museums:museums'
export OMNIGATE_FEDERATION_SYNONYM_ADDRESSING=true
export OMNIGATE_ACCESS_POLICY_CONFIG=demo-smithsonian-poc/access-policy.yaml
# admin console login, and the two Ask users: a curator (role staff, sees everything) and a public visitor (CC0 only)
export OMNIGATE_AUTH_USERS='admin:iJZrK4sybaSbtK0YIYcjTg==:kL2m6rNCnLwpfitbhe2+bAaK9GdfApB53J4uHhUd160=:ADMIN'
export OMNIGATE_APP_USERS='curator:FWpGgbhhJGIzH6L2LzDgxA==:3DGHpcuM7Wm4qFb51Kraqshrb0cIJquigmGiM9waIw4=:staff:role=staff;public:095i6OACFonQSBaYZ34ahg==:0hJlOfamKLS2t+cnZjJaEcKyr6GH1CLbW+aKbJzToOk=::cc0_filter=true|sensitive_filter=false'
export OMNIGATE_APP_BANNER='Unofficial prototype. Closed demo. Open Access records only (CC0). Not affiliated with or endorsed by any museum.'
export OMNIGATE_LLM_MODE=local-first
export OMNIGATE_ASSISTANT_REMOTE_HOST=127.0.0.1 OMNIGATE_ASSISTANT_REMOTE_PORT=18090
export OMNIGATE_FAST_ASSISTANT_REMOTE_HOST=127.0.0.1 OMNIGATE_FAST_ASSISTANT_REMOTE_PORT=8092 OMNIGATE_FAST_ASSISTANT_PORT=8092
export OMNIGATE_EMBEDDING_REMOTE_HOST=127.0.0.1 OMNIGATE_EMBEDDING_REMOTE_PORT=8120
export OMNIGATE_QUESTION_BANK_RETRIEVAL_ENABLED=true
export OMNIGATE_AUDIT_LOG_FILE=demo-smithsonian-poc/audit.log
export OMNIGATE_CONFIG_CACHE_SECONDS=2
[ -f .env ] && { set -a; source .env; set +a; }
cp target/omnigate.jar demo-smithsonian-poc/run.jar
nohup "$JAVA_BIN" -Xmx4g -jar demo-smithsonian-poc/run.jar > demo-smithsonian-poc/server.log 2>&1 &
echo $! > demo-smithsonian-poc/server.pid
echo "Smithsonian POC demo starting on http://localhost:8110  (admin / Admin-SI-1, curator / Curator-SI-1, public / Public-SI-1)"
