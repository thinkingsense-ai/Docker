#!/bin/bash
# Back up a running OmniGate deployment on any of the four clouds: the databases and the admin console's saved settings (and the licence).
#
#   backup-omnigate.sh [--kubeconfig F] [--context C] [--namespace default] [--release omnigate] [--out DIR] [--consistent]
#
# Writes a timestamped folder under DIR (default ./omnigate-backup) with:
#   db-<name>.dump        every PostgreSQL database in the deployment (custom format; restore with restore-omnigate.sh)
#   config-store.tgz      the admin console's saved settings (trusted questions, users, saved settings), from the app's data volume
#   licence.txt           the installed licence, if any
#   manifest.txt          what was backed up, from which image
# Treat the folder as a secret: it holds your data and the licence.
#
# By default the settings are copied while the app runs, which is quick but may miss a change made in the last moments. --consistent
# stops the app (scaled to zero) for the copy, which takes a minute or two, and starts it again.
# With an external config database (several replicas) the settings are in the database and the database dumps cover them.
set -euo pipefail
KC= CTX= NS=default REL=omnigate OUT=./omnigate-backup CONSISTENT=0
while [ $# -gt 0 ]; do case $1 in
  --kubeconfig) KC=$2; shift 2;; --context) CTX=$2; shift 2;; --namespace) NS=$2; shift 2;; --release) REL=$2; shift 2;;
  --out) OUT=$2; shift 2;; --consistent) CONSISTENT=1; shift;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
K=(kubectl); [ -n "$KC" ] && K+=(--kubeconfig "$KC"); [ -n "$CTX" ] && K+=(--context "$CTX"); K+=(-n "$NS")
umask 077
DIR="$OUT/$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$DIR"
PG=$REL-postgres-0; APP=$REL-omnigate
"${K[@]}" get pod "$PG" >/dev/null 2>&1 || { echo "No database pod $PG in namespace $NS; check --release / --namespace / --kubeconfig." >&2; exit 1; }

echo "== databases"
DBS=$("${K[@]}" exec "$PG" -- psql -U postgres -d postgres -tAc "select datname from pg_database where not datistemplate and datname <> 'postgres' union all select 'postgres' order by 1")
for db in $DBS; do
  "${K[@]}" exec "$PG" -- pg_dump -U postgres -Fc "$db" > "$DIR/db-$db.dump"
  [ -s "$DIR/db-$db.dump" ] || { echo "dump of $db is empty" >&2; exit 1; }
  printf '  %-12s %s bytes\n' "$db" "$(wc -c < "$DIR/db-$db.dump" | tr -d ' ')"
done

echo "== admin console settings"
KIND=deploy; "${K[@]}" get deploy "$APP" >/dev/null 2>&1 || KIND=statefulset
if "${K[@]}" get pvc "$APP-data" >/dev/null 2>&1; then
  if [ "$CONSISTENT" = 1 ]; then
    REPLICAS=$("${K[@]}" get $KIND "$APP" -o jsonpath='{.spec.replicas}')
    echo "  stopping the app for a consistent copy"
    "${K[@]}" scale $KIND "$APP" --replicas=0 >/dev/null
    "${K[@]}" wait --for=delete pod -l app.kubernetes.io/component=omnigate --timeout=180s >/dev/null 2>&1 || true
    trap '"${K[@]}" scale $KIND "$APP" --replicas="$REPLICAS" >/dev/null' EXIT
    "${K[@]}" delete pod "$REL-backup-helper" --ignore-not-found >/dev/null
    "${K[@]}" apply -f - >/dev/null <<YAML
apiVersion: v1
kind: Pod
metadata: {name: $REL-backup-helper}
spec:
  restartPolicy: Never
  tolerations: [{key: kubernetes.io/arch, operator: Equal, value: arm64, effect: NoSchedule}]
  containers:
    - {name: h, image: docker.io/library/postgres:16-alpine, command: [sleep, "600"], volumeMounts: [{name: d, mountPath: /var/lib/omnigate/data, readOnly: true}]}
  volumes: [{name: d, persistentVolumeClaim: {claimName: $APP-data}}]
YAML
    "${K[@]}" wait --for=condition=Ready pod "$REL-backup-helper" --timeout=180s >/dev/null
    "${K[@]}" exec "$REL-backup-helper" -- tar czf - -C /var/lib/omnigate data > "$DIR/config-store.tgz"
    "${K[@]}" delete pod "$REL-backup-helper" --wait=false >/dev/null
    "${K[@]}" scale $KIND "$APP" --replicas="$REPLICAS" >/dev/null; trap - EXIT
    echo "  app started again"
  else
    "${K[@]}" exec "deploy/$APP" -- tar czf - -C /var/lib/omnigate data > "$DIR/config-store.tgz"
  fi
  printf '  config-store.tgz %s bytes (%s)\n' "$(wc -c < "$DIR/config-store.tgz" | tr -d ' ')" "$([ "$CONSISTENT" = 1 ] && echo consistent || echo 'copied while running')"
else
  echo "  no data volume (external config database): the settings are in the database dumps"
fi

echo "== licence"
if L=$("${K[@]}" get secret "$REL-omnigate-license" -o jsonpath='{.data.license}' 2>/dev/null | base64 -d 2>/dev/null) && [ -n "$L" ]; then
  printf '%s' "$L" > "$DIR/licence.txt"; echo "  saved"
else echo "  none installed"; fi

{ echo "backup taken: $(date -u +%FT%TZ)"; echo "release: $REL in namespace $NS"
  echo "image: $("${K[@]}" get $KIND "$APP" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)"
  echo "databases: $(echo $DBS | tr '\n' ' ')"; echo "settings: $([ "$CONSISTENT" = 1 ] && echo consistent || echo 'copied while running')"; } > "$DIR/manifest.txt"
echo; echo "Backup written to $DIR"
