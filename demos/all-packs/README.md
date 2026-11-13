# All demo packs in one stack

Supply chain, manufacturing, IT & operational risk and the Smithsonian Open Access sample, together, on the container setup. The Ask app shows
them as a pack picker; each pack's approved questions carry its own category.

```bash
docker compose -f docker-compose.yml -f demos/all-packs/docker-compose.packs.yml up --build
```

Run it from the repository root. Ask is at `http://localhost:8080` (`curator` / `Curator-SI-1` sees everything; `public` / `Public-SI-1` sees Open
Access Smithsonian records only), the admin console at `http://localhost:8080/admin` (`admin` / `Admin-SI-1`). These are fixed demo logins in a public
repo: change them before the stack is reachable beyond your own machine.

## How it fits the free edition's three data sources

| Source | What it holds | Tables are addressed as |
|---|---|---|
| `pg` (Postgres) | schemas `suppliers`, `inventory`, `procurement` (supply chain and manufacturing), `risk`, `smithsonian` | `pg.risk.incidents` |
| `mdb` (MariaDB) | database `security` (vendors, vulnerabilities) | `mdb.security.vendors` |
| `files` (object store CSV) | the museum directory | `files.museums` |

`OMNIGATE_FEDERATION_AUTO_DISCOVER_SCHEMAS=true` makes every schema of a connection queryable, so the packs share one connector instead of one
source per schema. `OMNIGATE_ROUTER_SCHEMA_RULES` is blank on purpose: the base file maps schema names to the old per-schema sources, which breaks the
`connector.schema.table` names.

## The approved questions

`demo-questions-all-packs.json` holds 28 questions (5 + 6 + 12 + 5), all checked to run on this stack. Rules learned while checking them (app 0.10.16):

- Write each table as `connector.schema.table`. The one exception is the CSV, which is `files.museums` when the statement also touches another source.
- In a statement that spans two sources, `CURRENT_DATE - 365` fails to plan. Write `CURRENT_DATE - INTERVAL '365' DAY` in a filter, or
  `TIMESTAMPDIFF(DAY, date_col, CURRENT_DATE)` in the select list.
- Questions that Ask answers on its own (not from the bank) are a separate matter: see thinkingsense-ai/Server#43 (closed on 2026-11-10 with its bar unmet; free-form accuracy is still weak).

The Smithsonian vocabulary build (`POST /api/ontology/vocabulary/build`) also works here from app 0.10.16; the `concept` column is preloaded from
`demos/smithsonian-poc/vocabulary-concepts.csv` so the demo does not depend on it.
