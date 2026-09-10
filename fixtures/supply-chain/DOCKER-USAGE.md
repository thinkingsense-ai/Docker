# Running the supply chain fixture on this Docker image

> **⚠️ Real, checked limitation, not a docs typo**: this fixture needs a real fix to
> `FederationStage` (resolving a backend whose name differs from its real database schema — e.g.
> `suppliers`/`public`) that isn't in the currently published release (`v0.1.0`, this repo's
> default `OMNIGATE_RELEASE_TAG`) — tried live, it fails with *"the generated query references a
> table that doesn't exist"*. It will work once a release built after this fix is published; until
> then, either build the image from the `Server` source repo directly, or check this repo's
> [Releases](https://github.com/thinkingsense-ai/Docker/releases) for a tag newer than `v0.1.0`
> and pass it via `--build-arg OMNIGATE_RELEASE_TAG=<tag>` (see this repo's own README, "Picking up
> a newer release").

> **⚠️ Also real, also checked: this fixture exceeds the free edition's backend cap.** Step 2
> below registers **5** named backends (`demo` + `suppliers`/`inventory`/`procurement`/
> `logistics`) — the free edition keeps only the first 3 (see the main `README.md`'s "Free edition
> limits" table) and silently drops the rest, logged as a warning. The canonical question in Step
> 3 needs all four supply-chain backends, so it will fail (missing table) on the free image as
> written. To actually run this fixture end-to-end on the free image, drop the `demo` backend from
> `OMNIGATE_BACKENDS` (leaving exactly the 4 supply-chain backends — still one over the cap, so
> also drop one of the four, e.g. `logistics`, and adjust the canonical question accordingly) — or
> run against the commercial edition instead (build from the `Server` source repo with no
> `OMNIGATE_EDITION` env var set, which defaults to commercial).

The easiest path — **reuses the Postgres you already have running** from `docker compose up`, no
new containers needed. This is Tier B (single Postgres) from `README.md`.

## Step 1 — seed the extra schemas into your already-running Postgres

```bash
docker compose exec -T postgres psql -U postgres -d postgres < fixtures/supply-chain/single-postgres/seed.sql
```

(Run this from the root of this repo, with `docker compose up` already running.)

## Step 2 — point OmniGate at the new schemas

Open `docker-compose.yml`, find the `OMNIGATE_BACKENDS` line under the `omnigate` service, and
replace it with this (adds the four new schemas alongside the existing seeded `demo` backend):

```yaml
OMNIGATE_BACKENDS: "demo=jdbc:postgresql://postgres:5432/postgres|postgres|postgres;suppliers=jdbc:postgresql://postgres:5432/postgres?currentSchema=suppliers|postgres|postgres;inventory=jdbc:postgresql://postgres:5432/postgres?currentSchema=inventory|postgres|postgres;procurement=jdbc:postgresql://postgres:5432/postgres?currentSchema=procurement|postgres|postgres;logistics=jdbc:postgresql://postgres:5432/postgres?currentSchema=logistics|postgres|postgres"
OMNIGATE_ROUTER_SCHEMA_RULES: "suppliers:suppliers,inventory:inventory,procurement:procurement,logistics:logistics"
```

Then restart:

```bash
docker compose up -d
```

## Step 3 — ask the canonical question

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
  those instead (values are in `omnigate.env.example` in that same directory).
- **Tier C — CSV / object storage + Postgres**: see `csv-object-storage/README.md`. Seed
  `procurement`/`logistics` the same way as Step 1 above (using `csv-object-storage/seed-postgres.sql`
  instead), then mount `csv-object-storage/` into the `omnigate` container (add a `volumes:` entry
  to `docker-compose.yml`) and set `OMNIGATE_BACKENDS` per that directory's own
  `omnigate.env.example`, with `CSV_DIR` pointing at the mounted path inside the container.
