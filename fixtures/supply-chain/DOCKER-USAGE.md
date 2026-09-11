# Running the supply chain fixture on this Docker image

## Easiest path — one command, fully self-contained, no other repo needed

```bash
cd fixtures/supply-chain/single-postgres
docker compose up --build
```

This stands up a real Postgres (auto-seeded with all four supply-chain schemas) and an OmniGate
container built from this repo's own root `Dockerfile` — which bundles a real local reasoning
model, so this works with **zero external API key**. Then open **http://localhost:8080/**, log in
`demo`/`demo`, and ask the canonical question (see below). Live-verified: the bundled local model
gets the right 3 rows (PO 5001, 5002, 5004) on the first try.

> **Real, checked limitation — the free edition's 3-backend cap**: a naive 4-schema config
> (`suppliers`/`inventory`/`procurement`/`logistics` each as their own named backend) silently
> drops the 4th backend under the free edition's cap — confirmed live, and it quietly breaks the
> canonical question below (the dropped backend's table just isn't in the catalog, no error at
> all). `fixtures/supply-chain/single-postgres/docker-compose.yml` works around this with a real
> fix, not a data loss: `inventory` and `logistics` share ONE backend via a comma-separated
> `?currentSchema=inventory,logistics` (a genuine Postgres search-path feature, confirmed live to
> resolve tables from both schemas unqualified) — 3 backends, still 4 real separate schemas
> underneath. The commercial edition has no backend cap; split them back into 4 separate backends
> there if you'd rather. **Also worth knowing**: the bundled 3B local model doesn't always pull
> every requested column on a real 4-table join on the first attempt (confirmed live: it correctly
> found all 3 right purchase orders and joined `procurement`/`inventory`/`suppliers` correctly, but
> skipped the `carrier`/`eta_date` columns from `logistics` this one run) — set
> `OMNIGATE_LLM_API_KEY` alongside `OMNIGATE_LLM_MODE=local-first` (the compose file's own default)
> to let it escalate to a larger model on a lower-confidence answer, or use `cloud-first` for the
> most complete/accurate results.

## Manual path — reuse the Postgres you already have running

The easiest path if you're already running this repo's root `docker compose up` for something
else and don't want a second Postgres container.

### Step 1 — seed the extra schemas into your already-running Postgres

```bash
docker compose exec -T postgres psql -U postgres -d postgres < fixtures/supply-chain/single-postgres/seed.sql
```

(Run this from the root of this repo, with `docker compose up` already running.)

### Step 2 — point OmniGate at the new schemas

Open `docker-compose.yml`, find the `OMNIGATE_BACKENDS` line under the `omnigate` service, and
replace it with this (adds the supply-chain schemas alongside the existing seeded `demo` backend
-- already worked around the free-edition 3-backend cap the same way as the self-contained compose
above, since `demo` + 4 separate supply-chain backends would be 5 total):

```yaml
OMNIGATE_BACKENDS: "suppliers=jdbc:postgresql://postgres:5432/postgres?currentSchema=suppliers|postgres|postgres;inventory=jdbc:postgresql://postgres:5432/postgres?currentSchema=inventory,logistics|postgres|postgres;procurement=jdbc:postgresql://postgres:5432/postgres?currentSchema=procurement|postgres|postgres"
OMNIGATE_ROUTER_SCHEMA_RULES: "suppliers:suppliers,inventory:inventory,logistics:inventory,procurement:procurement"
```

Then restart:

```bash
docker compose up -d
```

### Step 3 — ask the canonical question

Open **http://localhost:8080/**, log in with `demo`/`demo` (see the main `README.md`), and ask:

> List each purchase order whose shipment status is exactly IN_TRANSIT and whose supplier country
> is exactly Vietnam, including po_id, sku, quantity ordered, carrier, eta_date, and current
> warehouse qty_on_hand for that sku.

You should get back exactly 3 rows (PO 5001, 5002, 5004) — see `README.md` for the full expected
answer and data.

## Other ways to run it (more real infrastructure, more setup)

- **Tier A — four real database engines** (Postgres + MySQL + Oracle + SQL Server): see
  `../supply-chain/docker-compose.yml` and `seed.sh` — stands up its own separate containers,
  independent of this repo's own `docker-compose.yml`. Once seeded, point `OMNIGATE_BACKENDS` at
  those instead (values are in `omnigate.env.example` in that same directory). Four real database
  engines means four real backends -- no free-edition cap workaround needed there, since it's
  already inherently a different physical server per schema, not four names on one Postgres.
- **Tier C — CSV / object storage + Postgres**: see `csv-object-storage/README.md`. Seed
  `procurement`/`logistics` the same way as Step 1 above (using `csv-object-storage/seed-postgres.sql`
  instead), then mount `csv-object-storage/` into the `omnigate` container (add a `volumes:` entry
  to `docker-compose.yml`) and set `OMNIGATE_BACKENDS` per that directory's own
  `omnigate.env.example`, with `CSV_DIR` pointing at the mounted path inside the container.
