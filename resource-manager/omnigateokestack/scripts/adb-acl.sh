#!/usr/bin/env bash
# Usage: adb-acl.sh <add|remove> <adb-ocid> <region> <node-pool-ocid>
#
# Adds (or removes) this stack's worker-node public IPs on an Autonomous Database's access
# control list. The ADB's ACL is a single replace-the-whole-list field, so this always reads the
# current list, merges, and writes it back -- it never overwrites entries it didn't add.
set -eu
export SUPPRESS_LABEL_WARNING=True

action=$1 adb=$2 region=$3 nodepool=$4

# JSON array -> one entry per line.
lines() { tr -d '[]" ' | tr ',' '\n' | grep -v -e '^$' -e '^null$' || true; }

node_ips=$(oci ce node-pool get --node-pool-id "$nodepool" --region "$region" \
  --query 'data.nodes[*]."public-ip"' | lines | sed 's#$#/32#' | sort -u)
if [ -z "$node_ips" ]; then
  echo "adb-acl: node pool reports no public IPs yet; nothing to $action" >&2
  exit 0
fi

current=$(oci db autonomous-database get --autonomous-database-id "$adb" --region "$region" \
  --query 'data."whitelisted-ips"' | lines | sort -u)

# An ADB with no ACL is open to everyone (or uses a private endpoint). Adding entries here would
# switch ACL enforcement ON and lock out every other client, so leave it alone.
if [ -z "$current" ]; then
  echo "adb-acl: $adb has no IP ACL (open or private endpoint); leaving it untouched" >&2
  exit 0
fi

if [ "$action" = add ]; then
  wanted=$(printf '%s\n%s\n' "$current" "$node_ips" | sort -u)
else
  wanted=$(comm -23 <(printf '%s\n' "$current") <(printf '%s\n' "$node_ips"))
  if [ -z "$wanted" ]; then
    echo "adb-acl: removing these IPs would empty the ACL (which means open to all); skipping" >&2
    exit 0
  fi
fi

if [ "$wanted" = "$current" ]; then
  echo "adb-acl: ACL already correct ($action); nothing to do"
  exit 0
fi

json=$(printf '%s\n' "$wanted" | sed 's#.*#"&"#' | paste -sd, - | sed 's#^#[#; s#$#]#')

# The ADB briefly refuses updates while it's mid-operation, so retry.
for attempt in 1 2 3 4 5 6; do
  if oci db autonomous-database update --autonomous-database-id "$adb" --region "$region" \
       --whitelisted-ips "$json" --force --wait-for-state AVAILABLE --max-wait-seconds 600 >/dev/null; then
    echo "adb-acl: $action done -> $json"
    exit 0
  fi
  echo "adb-acl: update attempt $attempt failed; retrying in 30s" >&2
  sleep 30
done
echo "adb-acl: giving up after 6 attempts" >&2
exit 1
