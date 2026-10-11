#!/bin/bash
# Switch a running GCP (GKE) stack between the free and commercial OmniGate image without rebuilding the cluster.
# Run it from the omnigategkestack directory you deployed from (Cloud Shell: where setup.sh lives), after `git pull` so the
# directory has the commercial-image settings (image_pull_username / image_pull_auth_token).
#
#   switch-edition-gke.sh --to commercial --pull-user <ns/user> --pull-token <auth token> \
#                         [--image-tag v0.10.4] [--url http://<lb>:8080 --admin-token <token>]
#   switch-edition-gke.sh --to free
#
# Only the image changes; the cluster, network, database volumes and OmniGate's saved configuration stay, and the OmniGate pod restarts.
# The settings are written to terraform.tfvars so later applies keep them.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/lib/ocir-check.sh"
DIR=$PWD TO= USER_= TOKEN= TAG= URL= ATOK=
while [ $# -gt 0 ]; do case $1 in
  --to) TO=$2; shift 2;; --pull-user) USER_=$2; shift 2;; --pull-token) TOKEN=$2; shift 2;; --image-tag) TAG=$2; shift 2;;
  --url) URL=$2; shift 2;; --admin-token) ATOK=$2; shift 2;; --dir) DIR=$2; shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
{ [ "$TO" = commercial ] || [ "$TO" = free ]; } || { sed -n 2,13p "$0"; exit 2; }
cd "$DIR"; [ -f terraform.tfvars ] && [ -f variables.tf ] || { echo "run this from the omnigategkestack directory (or pass --dir)" >&2; exit 2; }
grep -q image_pull_username variables.tf || { echo "this directory predates the commercial-image settings: run 'git pull' first" >&2; exit 2; }
if [ "$TO" = commercial ]; then
  { [ -n "$USER_" ] && [ -n "$TOKEN" ]; } || { echo "--to commercial needs --pull-user and --pull-token" >&2; exit 2; }
  CUR=$(sed -nE 's/^[[:space:]]*image_tag[[:space:]]*=[[:space:]]*"([^"]*)".*/\1/p' terraform.tfvars | head -1)
  check_commercial_pull "$USER_" "$TOKEN" "${TAG:-${CUR:-$(latest_app_tag)}}"
fi
cp terraform.tfvars terraform.tfvars.before-switch
# Drop the three image settings (and image_tag when one was given), then append the new ones.
python3 - "$TO" "$COMMERCIAL_REPO" "$USER_" "$TOKEN" "$TAG" <<'PY'
import re, sys
to, repo, user, token, tag = sys.argv[1:6]
lines = open("terraform.tfvars").read().splitlines()
drop = {"image_repository", "image_pull_username", "image_pull_auth_token"} | ({"image_tag"} if tag else set())
keep = [l for l in lines if not (re.match(r"\s*(\w+)\s*=", l) and re.match(r"\s*(\w+)", l).group(1) in drop)]
if to == "commercial":
    keep += [f'image_repository = "{repo}"', f'image_pull_username = "{user}"', f'image_pull_auth_token = "{token}"']
if tag:
    keep.append(f'image_tag = "{tag}"')
open("terraform.tfvars", "w").write("\n".join(keep) + "\n")
PY
chmod 600 terraform.tfvars
terraform apply -auto-approve -input=false
[ -z "$URL" ] || [ -z "$ATOK" ] || wait_for_edition "$URL" "$ATOK"
