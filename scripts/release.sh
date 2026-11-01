#!/usr/bin/env bash
# One command per phase of an app release, in the order RELEASING.md describes. Every phase stops on the first failure
# and each prints what it is about to do; --dry-run prints without changing anything.
#
#   scripts/release.sh app    0.10.15   bump + notes check, Server release, ghcr images, Docker release (jar + UI)
#   scripts/release.sh pins   0.10.15   wait for "Build images", merge the "Bump pins" PR, verify the pins
#   scripts/release.sh stacks 0.10.15 --notes FILE
#                                       self-pin PR (eks, aks), merge, then the four stack releases at the merge commit
#   scripts/release.sh docs   0.10.15   deploy-page PR in the Landing repo (merged only with --merge)
#
# Run `app` after writing Server/docs/releases/<version>.md. `pins` and `stacks` are separate on purpose: the clean-room
# checks sit between them (RELEASING.md), and merging the pins PR is a person's decision.
# Checkouts are found next to this repo (../Server, ../Landing); override with SERVER_DIR / LANDING_DIR.
set -euo pipefail

DOCKER_DIR=$(cd "$(dirname "$0")/.." && pwd)
SERVER_DIR=${SERVER_DIR:-$DOCKER_DIR/../Server}
LANDING_DIR=${LANDING_DIR:-$DOCKER_DIR/../Landing}
DOCKER_REPO=thinkingsense-ai/Docker
SERVER_REPO=thinkingsense-ai/Server
SERVER_REMOTE=${SERVER_REMOTE:-thinkingsense-server}

phase=${1:-}; version=${2:-}
[ -n "$phase" ] && [ -n "$version" ] || { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
shift 2
dry=0; merge=0; skip_tests=0; notes_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1 ;;
    --merge) merge=1 ;;
    --skip-tests) skip_tests=1 ;;
    --notes) notes_file=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must look like 0.10.15" >&2; exit 2; }
minor=${version%.*}
tag="v$version"

say() { echo "==> $*"; }
run() { if [ $dry = 1 ]; then echo "    [dry-run] $*"; else "$@"; fi; }
previous_version() { # the latest app tag before this one
  git -C "$SERVER_DIR" tag --list 'v[0-9]*' --sort=-v:refname | grep -v -x "$tag" | head -1 | sed 's/^v//'
}
next_stack() { # next patch of the newest <prefix>-stack-vX.Y.Z release
  local prefix=$1 last
  last=$(gh release list --repo $DOCKER_REPO --limit 100 --json tagName --jq '.[].tagName' | grep "^$prefix-stack-v" | sed "s/^$prefix-stack-v//" | sort -V | tail -1)
  echo "${last%.*}.$(( ${last##*.} + 1 ))"
}

phase_app() {
  local prev notes="$SERVER_DIR/docs/releases/$version.md"
  prev=$(previous_version)
  [ -f "$notes" ] || { echo "write $notes first (the upgrade notes are the release notes)" >&2; exit 1; }
  [ -z "$(git -C "$SERVER_DIR" status --porcelain)" ] || { echo "Server has uncommitted changes" >&2; exit 1; }
  [ "$(git -C "$SERVER_DIR" branch --show-current)" = main ] || { echo "Server is not on main" >&2; exit 1; }
  say "release $version on top of $prev"

  if [ $skip_tests = 0 ]; then
    if [ -x "$SERVER_DIR/scripts/test-infra.sh" ]; then
      say "full test suite, with the test services started and stopped around it (scripts/test-infra.sh test)"
      run "$SERVER_DIR/scripts/test-infra.sh" test
    else
      say "full test suite (no scripts/test-infra.sh here, so the container-dependent tests need their services already running)"
      run bash -c "cd '$SERVER_DIR' && mvn -B test"
    fi
  fi

  say "bump the version ($prev -> $version) in AppVersion, docker-compose.yml, README.md"
  if [ $dry = 0 ]; then
    sed -i.bak "s/$prev/$version/g" "$SERVER_DIR/src/main/java/com/omnigate/core/AppVersion.java" "$SERVER_DIR/docker-compose.yml" && rm -f "$SERVER_DIR"/src/main/java/com/omnigate/core/AppVersion.java.bak "$SERVER_DIR/docker-compose.yml.bak"
    python3 - "$SERVER_DIR/README.md" "$prev" "$version" <<'PY'
import sys
p, prev, new = sys.argv[1:]
s = open(p, encoding="utf-8").read()
s = s.replace(f"server:{prev}", f"server:{new}").replace(f":{prev}-free", f":{new}-free")
s = s.replace(f"start with [{prev}](docs/releases/{prev}.md)", f"start with [{new}](docs/releases/{new}.md) (patch: see the notes), then [{prev}](docs/releases/{prev}.md)", 1)
open(p, "w", encoding="utf-8").write(s)
PY
    git -C "$SERVER_DIR" add src/main/java/com/omnigate/core/AppVersion.java docker-compose.yml README.md
    git -C "$SERVER_DIR" commit -q -m "Release $version: version bump and upgrade notes"
  fi
  run git -C "$SERVER_DIR" push -q "$SERVER_REMOTE" main
  run git -C "$SERVER_DIR" tag "$tag"
  run git -C "$SERVER_DIR" push -q "$SERVER_REMOTE" "$tag"
  run gh release create "$tag" --repo $SERVER_REPO --title "$version" --notes-file "$notes" --latest

  say "build the jar and a fresh UI bundle, and check the bundle"
  local out; out=$(mktemp -d /tmp/release-$version.XXXXXX)
  run bash -c "cd '$SERVER_DIR' && mvn -q -B -DskipTests package && cp target/omnigate.jar '$out/'"
  run bash -c "cd '$SERVER_DIR/web' && npm ci --no-audit --no-fund >/dev/null && npm run build >/dev/null && tar -czf '$out/web-dist.tar.gz' -C dist ."
  run "$DOCKER_DIR/scripts/check-ui-bundle.sh" --dir "$SERVER_DIR/web/dist"

  say "build and push the ghcr images (commercial, :$minor, free)"
  local img=ghcr.io/thinkingsense-ai/server
  run bash -c "cd '$SERVER_DIR' && docker build -f Dockerfile.commercial -t $img:$version -t $img:$minor . && docker build -f Dockerfile.free -t $img:$version-free ."
  if [ $dry = 0 ]; then
    [ "$(docker run --rm --entrypoint cat $img:$version /opt/omnigate/EDITION)" = commercial ] || { echo "commercial image has the wrong edition marker" >&2; exit 1; }
    [ "$(docker run --rm --entrypoint cat $img:$version-free /opt/omnigate/EDITION)" = free ] || { echo "free image has the wrong edition marker" >&2; exit 1; }
  fi
  run docker push -q $img:$version
  run docker push -q $img:$minor
  run docker push -q $img:$version-free

  say "Docker release with omnigate.jar and web-dist.tar.gz (starts the Build images workflow)"
  run gh release create "$tag" --repo $DOCKER_REPO --title "$version" --notes-file "$notes" --latest "$out/omnigate.jar" "$out/web-dist.tar.gz"
  say "next: scripts/release.sh pins $version"
}

phase_pins() {
  say "waiting for the Build images run for $tag"
  local id status
  for _ in $(seq 1 60); do
    id=$(gh run list --repo $DOCKER_REPO --workflow "Build images" --json databaseId,headBranch,event --jq "[.[] | select(.headBranch==\"$tag\" and .event==\"release\")][0].databaseId")
    [ -n "$id" ] && [ "$id" != null ] && break
    sleep 10
  done
  [ -n "${id:-}" ] && [ "$id" != null ] || { echo "no Build images run found for $tag" >&2; exit 1; }
  for _ in $(seq 1 120); do
    status=$(gh run view "$id" --repo $DOCKER_REPO --json status,conclusion --jq '.status+" "+(.conclusion // "")')
    case "$status" in completed*) break ;; esac
    sleep 15
  done
  [ "$status" = "completed success" ] || { echo "Build images ended with: $status" >&2; exit 1; }
  local pr; pr=$(gh pr list --repo $DOCKER_REPO --head "pins-$tag" --json number --jq '.[0].number')
  [ -n "$pr" ] || { echo "no 'Bump pins to $tag' PR found" >&2; exit 1; }
  say "merging pins PR #$pr"
  run gh pr merge "$pr" --repo $DOCKER_REPO --squash --delete-branch
  run bash -c "cd '$DOCKER_DIR' && git checkout -q main && git pull -q origin main && python3 scripts/version-pins.py check"
  say "next: the clean-room checks, then scripts/release.sh stacks $version --notes FILE"
}

phase_stacks() {
  [ -n "$notes_file" ] && [ -f "$notes_file" ] || { echo "--notes FILE is required (the text for the four stack releases)" >&2; exit 2; }
  local eks aks gke oke
  eks=$(next_stack eks); aks=$(next_stack aks); gke=$(next_stack gke); oke=$(next_stack oke)
  say "stack releases: eks v$eks, aks v$aks, gke v$gke, oke v$oke"
  cd "$DOCKER_DIR"
  run git checkout -q main
  run git pull -q origin main
  local branch="self-pins-$version"
  run git checkout -q -b "$branch"
  run python3 scripts/version-pins.py bump-self eks "v$eks"
  run python3 scripts/version-pins.py bump-self aks "v$aks"
  run git commit -qam "Move the eks and aks self-pins to eks-stack-v$eks and aks-stack-v$aks"
  run git push -q origin "$branch"
  run gh pr create --repo $DOCKER_REPO --base main --head "$branch" --title "Move the eks and aks self-pins to eks-stack-v$eks and aks-stack-v$aks" --body "Self-pins for the stack releases that carry app $version."
  run gh pr merge "$branch" --repo $DOCKER_REPO --squash --delete-branch
  run git checkout -q main
  run git pull -q origin main
  local sha; sha=$(git rev-parse HEAD)
  say "tagging at the merge commit $sha"
  local out; out=$(mktemp -d /tmp/stacks-$version.XXXXXX)
  rel() { # dir, version, tag, name
    local z="$out/$1-v$2.zip" extra=()
    run git archive --format=zip --prefix="$1/" -o "$z" "$sha:resource-manager/$1"
    if [ "$1" = omnigateeksstack ]; then
      [ $dry = 1 ] || git show "$sha:resource-manager/$1/template.yaml" > "$out/template.yaml"
      extra=("$out/template.yaml")
    fi
    run gh release create "$3" --repo $DOCKER_REPO --target "$sha" --title "$4 stack v$2" --notes-file "$notes_file" --latest=false "$z" ${extra[@]+"${extra[@]}"}
  }
  rel omnigateokestack "$oke" "oke-stack-v$oke" OKE
  rel omnigateeksstack "$eks" "eks-stack-v$eks" EKS
  rel omnigateaksstack "$aks" "aks-stack-v$aks" AKS
  rel omnigategkestack "$gke" "gke-stack-v$gke" GKE
  run git fetch -q --tags origin
  run python3 scripts/version-pins.py check --verify-tags
  echo "$oke $eks $aks $gke" > "$out/versions"
  if command -v aws >/dev/null && aws sts get-caller-identity >/dev/null 2>&1; then
    run "$DOCKER_DIR/scripts/upload-eks-template.sh" "v$eks"
  else
    say "EKS: no AWS credentials here; run scripts/upload-eks-template.sh v$eks where you have them (the AWS deploy page waits for it)"
  fi
  say "next: scripts/release.sh docs $version"
}

phase_docs() {
  cd "$LANDING_DIR"
  local oke eks aks
  oke=$(gh release list --repo $DOCKER_REPO --limit 100 --json tagName --jq '.[].tagName' | grep '^oke-stack-v' | sed 's/^oke-stack-v//' | sort -V | tail -1)
  aks=$(gh release list --repo $DOCKER_REPO --limit 100 --json tagName --jq '.[].tagName' | grep '^aks-stack-v' | sed 's/^aks-stack-v//' | sort -V | tail -1)
  eks=$(gh release list --repo $DOCKER_REPO --limit 100 --json tagName --jq '.[].tagName' | grep '^eks-stack-v' | sed 's/^eks-stack-v//' | sort -V | tail -1)
  say "deploy pages: oke v$oke, aks v$aks, image v$version (eks v$eks only once its S3 template is uploaded)"
  run git checkout -q main
  run git pull -q origin main
  run git checkout -q -b "deploy-$version"
  if [ $dry = 0 ]; then
    sed -i.bak -E "s/oke-stack-v[0-9]+\.[0-9]+\.[0-9]+/oke-stack-v$oke/g; s/omnigateokestack-v[0-9]+\.[0-9]+\.[0-9]+/omnigateokestack-v$oke/g" deploy-oci.html
    sed -i.bak -E "s/aks-stack-v[0-9]+\.[0-9]+\.[0-9]+/aks-stack-v$aks/g" deploy-azure.html
    sed -i.bak -E "s#omnigate:v[0-9]+\.[0-9]+\.[0-9]+#omnigate:v$version#" deploy-docker.html
    if curl -sfI "https://thinkingsense-cfn-templates.s3.amazonaws.com/eks-stack-v$eks/template.yaml" >/dev/null; then
      # lines that name a minimum or an older affected release are history, not the current release
      sed -i.bak -E "/older release than|or later/! s/eks-stack-v[0-9]+\.[0-9]+\.[0-9]+/eks-stack-v$eks/g" deploy-aws.html
    else
      echo "    EKS template v$eks is not readable in S3: leaving deploy-aws.html where it is"
    fi
    rm -f ./*.bak
    if git diff --quiet; then
      say "the deploy pages already name oke v$oke, aks v$aks and image v$version: nothing to change, no PR opened"
      git checkout -q main
      git branch -D "deploy-$version" -q
      return 0
    fi
    git commit -qam "Deploy pages: OKE stack v$oke, AKS stack v$aks, ARM image v$version"
  fi
  run git push -q origin "deploy-$version"
  run gh pr create --base main --head "deploy-$version" --title "Deploy pages: OKE stack v$oke, AKS stack v$aks, ARM image v$version" --body "Points the deploy pages at the new stack releases and image."
  if [ $merge = 1 ]; then run gh pr merge "deploy-$version" --squash --delete-branch; else say "PR opened; merge it, or re-run with --merge"; fi
}

case "$phase" in
  app) phase_app ;;
  pins) phase_pins ;;
  stacks) phase_stacks ;;
  docs) phase_docs ;;
  *) echo "unknown phase $phase" >&2; exit 2 ;;
esac
