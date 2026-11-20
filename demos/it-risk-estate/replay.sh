#!/bin/sh
# Stands in for the Kafka connector: applies the events in replay/ to the estate tables one at a time, as an upsert sink would, with a pause between them.
# Off unless demos/it-risk-estate/docker-compose.estate-replay.yml is added. After the last event Q3 (where runbooks and credentials sit) is worse than at start-up,
# on purpose: it shows an exposure rating rising as events arrive. Re-running is safe (upserts); a fresh Postgres volume starts back at the backlog.
set -eu
: "${PGHOST:=postgres}" "${PGUSER:=postgres}" "${PGDATABASE:=postgres}" "${ESTATE_REPLAY_SECONDS:=45}"
export PGHOST PGUSER PGDATABASE; export PGPASSWORD="${PGPASSWORD:-postgres}"
tries=0; until pg_isready -q; do tries=$((tries+1)); [ "$tries" -gt 60 ] && { echo 'replay: Postgres not reachable' >&2; exit 1; }; sleep 2; done
for f in /replay/*.sql; do
  sleep "$ESTATE_REPLAY_SECONDS"
  echo "replay: $(basename "$f")"
  psql -v ON_ERROR_STOP=1 -q -f "$f"
done
echo "replay: done"
