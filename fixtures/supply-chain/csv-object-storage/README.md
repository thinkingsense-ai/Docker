# Supply chain fixture — Tier C: CSV / object storage + Postgres (mixed connectors)

Same story/schema/data as `../README.md` — for demoing a real mixed federation: `suppliers.csv`
and `warehouse_inventory.csv` stand in for data that would live in real object storage (S3/Azure
Blob) in production, while `purchase_orders`/`shipments` stay in a real Postgres database.

## Quick start (local files, no object storage needed)

```bash
psql -h <host> -U <user> -d <db> -f seed-postgres.sql
cp omnigate.env.example my.env   # edit CSV_DIR (absolute path to this directory) and Postgres creds
source my.env
java -jar ../../../target/omnigate.jar
```

Live-verified: the canonical question (see `../README.md`) returns the exact same 3-row answer as
Tiers A/B, first attempt.

## Using real object storage instead of a local directory

`omnigate.env.example`'s own comments explain the swap: change `"provider":"local","baseDir":
"<path>"` to `"provider":"s3","bucket":"<your-bucket>"` (upload `suppliers.csv`/
`warehouse_inventory.csv` to that bucket first, with AWS credentials configured the usual way) or
`"provider":"azureblob","accountName":"..."`. Nothing else changes — same `tables` map, same
federated join, same NL2SQL/Federation-Plans behavior, regardless of which object-storage provider
is actually behind it.

## Real quirk found while building this (already handled in `omnigate.env.example`)

The inline Calcite model's own `"name"` field for a `GENERIC_REST`/CSV backend must match the
ThinkingSense backend name exactly (e.g. `"suppliers"`, not a short label like `"s"`) — NL2SQL's schema
catalog picks up that inline name as the real queryable schema prefix, so a mismatched short name
leaks into generated SQL and breaks the join. Found live; `omnigate.env.example` already uses the
correct matching names.

## Real, honest limitation

CSV/S3-backed (`GENERIC_REST`/`ConnectorProvider`-mounted) backends have no Trino catalog mapping
today (see `docs/deployment/trino-cluster.md`'s coverage table) — this tier only works with the
default Calcite engine. Leave `OMNIGATE_QUERY_ENGINE`/`OMNIGATE_TRINO_JDBC_URL` unset.
