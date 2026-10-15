#!/bin/bash
# VENDOR USE ONLY -- needs the private signing key. Issues a licence token for a customer.
#
#   issue-licence.sh --key /secure/path/licence-private-key --customer "Acme Corp" --term 1y|2y|3y|<N>m
#                    [--grace-days 7] [--jar omnigate.jar] [--cap maxBackends=10 ...]
#
# --term counts from today. --grace-days (default 7) is added to the expiry: until the app has its own soft-grace state
# (thinkingsense-ai/Server#21), a licence that expires 7 days after the paid end date IS the grace period. Set it to 0 once the app
# does grace itself, or customers get it twice. The token is printed on stdout; the customer, paid end date and the date the
# app will downgrade are printed on stderr, so you can paste the token without the extra lines.
set -euo pipefail
KEY= CUST= TERM= GRACE=7 JAR= CAPS=()
while [ $# -gt 0 ]; do case $1 in
  --key) KEY=$2; shift 2;; --customer) CUST=$2; shift 2;; --term) TERM=$2; shift 2;; --grace-days) GRACE=$2; shift 2;;
  --jar) JAR=$2; shift 2;; --cap) CAPS+=("$2"); shift 2;;
  *) echo "unknown argument $1" >&2; exit 2;; esac; done
{ [ -n "$KEY" ] && [ -n "$CUST" ] && [ -n "$TERM" ]; } || { sed -n 2,12p "$0"; exit 2; }
case $TERM in *y) DAYS=$(( ${TERM%y} * 365 ));; *m) DAYS=$(( ${TERM%m} * 30 ));; *) echo "--term must look like 1y, 2y, 3y or 6m" >&2; exit 2;; esac
if [ -z "$JAR" ]; then JAR=$(mktemp -t omnigate-jar); curl -fsSL -o "$JAR" https://github.com/thinkingsense-ai/Docker/releases/latest/download/omnigate.jar; trap 'rm -f "$JAR"' EXIT; fi
TOTAL=$(( DAYS + GRACE ))
TOKEN=$(java -cp "$JAR" com.omnigate.core.LicenseTool issue "$KEY" "$CUST" "$TOTAL" ${CAPS[@]+"${CAPS[@]}"})
PAID=$(python3 -c "import datetime;print((datetime.date.today()+datetime.timedelta(days=$DAYS)).isoformat())")
DOWN=$(python3 -c "import datetime;print((datetime.date.today()+datetime.timedelta(days=$TOTAL)).isoformat())")
echo "customer: $CUST   paid through: $PAID   app downgrades on: $DOWN (includes $GRACE days of grace)" >&2
java -cp "$JAR" com.omnigate.core.LicenseTool check "$TOKEN" >&2
printf '%s\n' "$TOKEN"
