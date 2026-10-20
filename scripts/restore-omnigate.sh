#!/bin/bash
# Restore a backup made by backup-omnigate.sh into a running OmniGate deployment (the same deployment, or a fresh one made from the same stack).
#
#   restore-omnigate.sh --from <backup folder> [--kubeconfig F] [--context C] [--namespace default] [--release omnigate] --yes
#
# This REPLACES the deployment's databases (the ones in the backup) and the admin console's saved settings with what is in the backup. The app is
# stopped during the restore (a minute or two) and started again. The licence in the backup, if any, is put back. The HTTPS certificate is not
# restored: a new deployment keeps (or makes) its own, which names its own address.
# Deploy the new stack first (the same release or newer), let it come up, then run this.
set -euo pipefail
KC= CTX= NS=default REL=omnigate FROM= YES=0
while [ $# -gt 0 ]; do case $1 in
  --from) FROM=${2%/}; shift 2;; --kubeconfig) KC=$2; shift 2;; --context) CTX=$2; shift 2;; --namespace) NS=$2; shift 2;; --release) REL=$2; shift 2;;
  --yes) YES=1; shift;; *) echo "unknown argument $1" >&2; exit 2;; esac; done
[ -n "$FROM" ] && [ -d "$FROM" ] || { sed -n 2,9p "$0"; exit 2; }
ls "$FROM"/db-*.dump >/dev/null 2>&1 || { echo "No db-*.dump files in $FROM: not a backup folder." >&2; exit 1; }
[ "$YES" = 1 ] || { echo "This replaces the databases and saved settings in namespace $NS with the backup in $FROM. Run again with --yes to go ahead." >&2; exit 1; }
K=(kubectl); [ -n "$KC" ] && K+=(--kubeconfig "$KC"); [ -n "$CTX" ] && K+=(--context "$CTX"); K+=(-n "$NS")
PG=$REL-postgres-0; APP=$REL-omnigate
"${K[@]}" get pod "$PG" >/dev/null 2>&1 || { echo "No database pod $PG in namespace $NS; deploy the stack first." >&2; exit 1; }
KIND=deploy; "${K[@]}" get deploy "$APP" >/dev/null 2>&1 || KIND=statefulset
REPLICAS=$("${K[@]}" get $KIND "$APP" -o jsonpath='{.spec.replicas}')

echo "== stopping the app"
"${K[@]}" scale $KIND "$APP" --replicas=0 >/dev/null
"${K[@]}" wait --for=delete pod -l app.kubernetes.io/component=omnigate --timeout=180s >/dev/null 2>&1 || true
trap '"${K[@]}" scale $KIND "$APP" --replicas="$REPLICAS" >/dev/null 2>&1 || true' EXIT

echo "== databases"
for f in "$FROM"/db-*.dump; do
  db=$(basename "$f" .dump); db=${db#db-}
  "${K[@]}" exec -i "$PG" -- pg_restore -U postgres -d "$db" --clean --if-exists --no-owner < "$f" 2>&1 | grep -v "^pg_restore: warning" || true
  printf '  restored %s\n' "$db"
done

if [ -f "$FROM/config-store.tgz" ] && "${K[@]}" get pvc "$APP-data" >/dev/null 2>&1; then
  echo "== admin console settings"
  "${K[@]}" delete pod "$REL-restore-helper" --ignore-not-found >/dev/null
  "${K[@]}" apply -f - >/dev/null <<YAML
apiVersion: v1
kind: Pod
metadata: {name: $REL-restore-helper}
spec:
  restartPolicy: Never
  tolerations: [{key: kubernetes.io/arch, operator: Equal, value: arm64, effect: NoSchedule}]
  containers:
    - {name: h, image: docker.io/library/postgres:16-alpine, command: [sleep, "600"], volumeMounts: [{name: d, mountPath: /var/lib/omnigate/data}]}
  volumes: [{name: d, persistentVolumeClaim: {claimName: $APP-data}}]
YAML
  "${K[@]}" wait --for=condition=Ready pod "$REL-restore-helper" --timeout=180s >/dev/null
  # keep this deployment's own certificate (tls) and the volume's lost+found; replace everything else
  "${K[@]}" exec "$REL-restore-helper" -- sh -c "find /var/lib/omnigate/data -mindepth 1 -maxdepth 1 ! -name tls ! -name lost+found -exec rm -rf {} +"
  "${K[@]}" exec -i "$REL-restore-helper" -- tar xzf - -C /var/lib/omnigate --exclude=data/tls --exclude=data/lost+found < "$FROM/config-store.tgz"
  "${K[@]}" delete pod "$REL-restore-helper" --wait=false >/dev/null
  echo "  restored"
fi

if [ -f "$FROM/licence.txt" ]; then
  echo "== licence"
  L=$(tr -d '[:space:]' < "$FROM/licence.txt")
  "${K[@]}" patch secret "$REL-omnigate-license" -p "{\"stringData\":{\"license\":\"$L\"}}" >/dev/null && echo "  put back"
fi

echo "== starting the app"
"${K[@]}" scale $KIND "$APP" --replicas="$REPLICAS" >/dev/null; trap - EXIT
"${K[@]}" rollout status $KIND "$APP" --timeout=600s
echo "Restore finished."
