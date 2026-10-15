#!/usr/bin/env bash
# Runs the cross-replica OIDC login test against a deployed cluster.
#
#   KUBECONFIG=/path/to/kubeconfig ./oidc-test.sh [--swap] [--port 8080]
#
# Port-forwards omnigate-omnigate-0 and -1, then starts oidc-cross-pod-proxy.py on localhost so that
# the login START goes to one pod and the provider's CALLBACK to the other. Sign in from a browser at
# http://localhost:8080/app/oidc/login (Ask app) or /auth/oidc/login (admin). --swap reverses which pod
# starts and which finishes. Ctrl-C stops everything.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
port=8080 login_pod=0 callback_pod=1
while [ $# -gt 0 ]; do
  case $1 in
    --swap) login_pod=1 callback_pod=0 ;;
    --port) port=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

kubectl get pod omnigate-omnigate-0 omnigate-omnigate-1 >/dev/null
trap 'kill $(jobs -p) 2>/dev/null' EXIT
kubectl port-forward "pod/omnigate-omnigate-$login_pod" 18081:8080 >/dev/null &
kubectl port-forward "pod/omnigate-omnigate-$callback_pod" 18082:8080 >/dev/null &
sleep 3
echo "login starts on omnigate-omnigate-$login_pod, callback finishes on omnigate-omnigate-$callback_pod"
echo "open http://localhost:$port/app/oidc/login   (or /auth/oidc/login for the admin console)"
exec python3 "$here/oidc-cross-pod-proxy.py" --listen "$port" --login 127.0.0.1:18081 --callback 127.0.0.1:18082
