# TPC-H demo add-on

A real ~1GB TPC-H dataset (customer, orders, part, partsupp, supplier, nation, region, and the
large LINEITEM fact table) you can run against this project either with data it generates and
hosts itself, or against your own cloud storage and database. This is a completely separate,
opt-in stack from the main `docker-compose.yml` one directory up — running it never touches or
conflicts with the main supply-chain demo.

## Why a separate stack, not a layer on the main one

A natural instinct is to run this as a Compose overlay (`-f docker-compose.yml -f
docker-compose.tpch.yml`) on top of the main stack's own `omnigate` service. That doesn't work
cleanly here: `OMNIGATE_BACKENDS` is one flat string per service, and when Compose merges
`environment` across `-f` files, a key present in both files is **replaced**, not appended. Layering
this add-on's `OMNIGATE_BACKENDS` (postgres1 + lineitem) onto the main stack's own `omnigate`
service would silently wipe out the supply-chain demo's own four backends. Instead, this add-on
ships its own `omnigate-tpch` container, on different ports, so both can run side by side if you
want, with zero risk of one clobbering the other's configuration.

## Two ways to run it

```bash
# From the Docker/ repo root:
./scripts/enable-tpch-demo.sh bundled   # ships its own MinIO + Postgres, pre-loaded
./scripts/enable-tpch-demo.sh byo       # bring your own object storage + database
```

Or directly with Compose, from this directory:

```bash
# Bundled
cp .env.example .env
docker compose -f docker-compose.tpch.yml --profile tpch-bundled up --build

# Bring-your-own (AWS shown; see .env.oci.example / .env.azure.example / .env.gcp.example for the others)
cp .env.aws.example .env   # edit with your own values
docker compose -f docker-compose.tpch.yml --profile tpch-byo up --build
```

Either way:
1. `tpch-loader` runs once, generates (or confirms it already generated) the TPC-H dataset via
   DuckDB's own `tpch` extension — the real dbgen row-generation algorithm, not a hand-rolled
   approximation — and loads LINEITEM into whichever object store is configured and the other
   seven tables into whichever Postgres is configured, then exits.
2. `omnigate-tpch` starts once the loader has finished, reachable at `http://localhost:18080/`
   (login `demo`/`demo` — **change or remove this** before exposing the container beyond your own
   machine).

Re-running `up` on an already-loaded stack is a fast no-op — the loader checks real row counts and
a real object/blob existence check before regenerating anything. Set `TPCH_FORCE_RELOAD=true` in
your `.env` to force a reload (e.g. after changing `TPCH_SCALE_FACTOR`).

## What "bundled" vs "bring-your-own" actually changes

| | Bundled (`tpch-bundled` profile) | Bring-your-own (`tpch-byo` profile) |
|---|---|---|
| LINEITEM storage | A real local MinIO container this stack creates for you | Your own AWS S3 / OCI Object Storage / Azure Blob Storage / GCS bucket |
| Dimension tables | A real local Postgres container this stack creates for you | Your own Postgres database |
| What you configure | Nothing required — `.env.example`'s defaults just work | Connection details for your own bucket + database (`.env.aws.example` / `.env.oci.example` / `.env.azure.example` / `.env.gcp.example`) |

AWS, OCI, and GCS are all reached through the identical S3-compatible code path in
`com.omnigate.calcite.s3.S3SchemaFactory` — only the endpoint URL and path-style setting differ
between providers, which is exactly what each `.env.*.example` file's own comments spell out.
Azure Blob Storage is a genuinely separate code path (a different auth/API shape entirely), both in
the Java connector and in this add-on's own loader script — see `.env.azure.example`.

## Scope and known limits, disclosed rather than discovered the hard way

- **Dimension tables load into Postgres only** in this version. Pointing `TPCH_DIM_JDBC_URL` at a
  different relational database (MySQL, Oracle, SQL Server) will not work — the loader speaks
  plain `psycopg2`/`COPY`, which is Postgres-specific. Extending the loader to other dialects is
  real, separate follow-on work.
- **`TPCH_DIM_JDBC_URL` must be a bare `jdbc:postgresql://host:port/database` URL with no query
  string of its own** in bring-your-own mode — the compose file appends `?currentSchema=public` to
  it directly, and there's no conditional templating in Compose to combine the two cleanly. If your
  Postgres needs extra JDBC parameters, this version doesn't support combining them.
- **Scale factor** defaults to 1 (~1GB total, matching dbgen's own documented sizing for scale
  factor 1). Raise `TPCH_SCALE_FACTOR` for a bigger dataset — the loader's idempotency check
  compares against the real expected row count for the configured scale factor, so changing it and
  re-running `up` triggers a real reload automatically.

## Tearing it down

```bash
docker compose -f docker-compose.tpch.yml --profile tpch-bundled down -v   # also drops the local data volumes
```

This only ever touches this add-on's own containers and volumes (`tpch-minio-data`,
`tpch-postgres-data`) — it has no effect on the main stack one directory up.
