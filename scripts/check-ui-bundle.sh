#!/usr/bin/env bash
# Checks that an OmniGate web UI bundle contains the pages the release is supposed to ship.
#
#   check-ui-bundle.sh --dir <extracted web-dist directory>
#   check-ui-bundle.sh --url https://<host>          (a running deployment; the page is public, no login needed)
#   check-ui-bundle.sh --tag vX.Y.Z [--repo owner/name]   (downloads web-dist.tar.gz from that release with gh)
#
# The strings to look for are in scripts/ui-bundle-expect.txt. Exit 0 when every one is found, 1 when one is missing, 2 on a usage
# or download error. Why: the UI is built by hand and uploaded as a release asset, so a release can carry a UI older than its server.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
EXPECT="$HERE/ui-bundle-expect.txt"
mode=; arg=; repo=thinkingsense-ai/Docker
while [ $# -gt 0 ]; do
  case $1 in
    --dir|--url|--tag) mode=${1#--}; arg=${2:-}; shift 2 ;;
    --repo) repo=${2:-}; shift 2 ;;
    *) echo "usage: $0 --dir DIR | --url URL | --tag vX.Y.Z [--repo owner/name]" >&2; exit 2 ;;
  esac
done
[ -n "$mode" ] && [ -n "$arg" ] || { echo "usage: $0 --dir DIR | --url URL | --tag vX.Y.Z [--repo owner/name]" >&2; exit 2; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
js="$work/all.js"; : > "$js"
case $mode in
  dir)
    ls "$arg"/assets/*.js >/dev/null 2>&1 || { echo "no assets/*.js under $arg" >&2; exit 2; }
    cat "$arg"/assets/*.js > "$js" ;;
  tag)
    gh release download "$arg" --repo "$repo" -p web-dist.tar.gz -D "$work" >/dev/null 2>&1 || { echo "cannot download web-dist.tar.gz from $repo $arg" >&2; exit 2; }
    mkdir "$work/x"; tar -xzf "$work/web-dist.tar.gz" -C "$work/x"
    cat "$work/x"/assets/*.js > "$js" 2>/dev/null || { echo "web-dist.tar.gz of $arg has no assets/*.js" >&2; exit 2; } ;;
  url)
    base=${arg%/}
    curl -sk -m 30 "$base/" > "$work/index.html" || { echo "cannot fetch $base/" >&2; exit 2; }
    scripts=$(grep -o 'assets/[A-Za-z0-9._-]*\.js' "$work/index.html" | sort -u)
    [ -n "$scripts" ] || { echo "$base/ names no script under assets/" >&2; exit 2; }
    for s in $scripts; do curl -sk -m 60 "$base/$s" >> "$js" || { echo "cannot fetch $base/$s" >&2; exit 2; }; done ;;
esac
[ -s "$js" ] || { echo "the bundle's JavaScript is empty" >&2; exit 2; }

missing=0
while IFS= read -r want; do
  case $want in ''|'#'*) continue ;; esac
  if grep -qF -- "$want" "$js"; then echo "ok       UI bundle contains '$want'"
  else echo "MISSING  UI bundle does not contain '$want'"; missing=1; fi
done < "$EXPECT"
[ $missing -eq 0 ] || echo "The web UI was built before the release's pages were added: rebuild it (cd web && npm ci && npm run build) and upload web-dist.tar.gz again." >&2
exit $missing
