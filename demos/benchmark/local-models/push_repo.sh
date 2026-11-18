#!/bin/bash
# Copies the Docker repo to ~/Docker on a benchmark node WITHOUT secrets.
#   demos/benchmark/local-models/push_repo.sh ubuntu@<node-ip>            # copy
#   demos/benchmark/local-models/push_repo.sh --check                     # only list what would be refused
# Excludes secret-type files (.env, *.tfvars, *.tfstate*, .terraform, *.pem, *.key, licence files) AND scans what remains: it refuses to copy if any file
# holds an Anthropic-key-shaped string or a private-key header. (A plain rsync of the repo once copied a Terraform tfvars and a tfstate backup holding a real
# key to a cloud node: found and deleted the same hour. This script exists so that cannot repeat.)
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
EXCL=(--exclude .git --exclude node_modules --exclude dist --exclude '*.pyc' --exclude __pycache__ --exclude .env --exclude '*.tfvars' --exclude '*.tfstate*'
      --exclude .terraform --exclude '*.pem' --exclude '*.key' --exclude 'licence-*' --exclude 'agency/local/.cj' --exclude 'agency/local/commercial.override.yml')
LIST=$(mktemp); trap 'rm -f "$LIST"' EXIT
rsync -an "${EXCL[@]}" --out-format='%n' "$ROOT/" "$(mktemp -d)/" | grep -v '/$' > "$LIST" || true
BAD=$(cd "$ROOT" && tr '\n' '\0' < "$LIST" | xargs -0 grep -IlE 'sk-ant-[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' 2>/dev/null || true)
if [ -n "$BAD" ]; then echo "REFUSED: these files would be copied and contain a key-shaped string:" >&2; echo "$BAD" >&2; exit 2; fi
echo "scan clean: $(wc -l < "$LIST" | tr -d ' ') files, none holds a key-shaped string"
[ "${1:-}" = "--check" ] && exit 0
rsync -az --delete "${EXCL[@]}" -e "ssh -o BatchMode=yes" "$ROOT/" "$1:~/Docker/"
