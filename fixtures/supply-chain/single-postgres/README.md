# Supply chain fixture — Tier B: single Postgres

Same story/schema/data as `../README.md` — for a user who only has Postgres available. All four
"backends" (`suppliers`, `inventory`, `procurement`, `logistics`) are real schemas in ONE Postgres
database; ThinkingSense still genuinely federates across all four (real `FederationStage`/`RouterStage`
code path, same as the multi-database Tier A) — it just needs zero extra infrastructure.

## Quick start

```bash
psql -h <host> -U <user> -d <db> -f seed.sql
cp omnigate.env.example my.env   # edit HOST/PORT/DB/USER/PASS at the top
source my.env
java -jar ../../../target/omnigate.jar
```

Live-verified: the canonical question (see `../README.md`) returns the exact same 3-row answer as
Tier A, first attempt, through the default Calcite engine.
