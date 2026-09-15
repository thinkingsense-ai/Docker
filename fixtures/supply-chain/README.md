# Supply chain federation fixture

A real, reusable fixture for testing/demoing federated NL2SQL, Federation Plans, and both the
Calcite and Trino query engines against a genuine cross-system join. **Use this fixture whenever a
"supply chain use case" is requested** — don't re-derive a new schema/story each time.

Same story, same schema, same seeded data, same canonical demo question/answer across three real
infrastructure tiers — pick whichever matches what's actually available:

| Tier | Directory | Real infrastructure needed |
|---|---|---|
| **A — 4 databases** | this directory (`docker-compose.yml`/`seed.sh`) | Postgres + MySQL + Oracle + SQL Server (real, separate engines — the full multi-dialect story) |
| **B — single Postgres** | `single-postgres/` | Just Postgres — the same 4 "backends" as 4 real schemas in one database |
| **C — CSV + Postgres (object storage)** | `csv-object-storage/` | Postgres for 2 tables, 2 tables as real CSV files (local directory, or real S3/Azure Blob — see that directory's own README) |

All three are real, live-verified end-to-end (not just written down) — the exact same canonical
question returns the exact same correct 3-row answer through all three, via both engines where
applicable (Tier C is Calcite-only — CSV/object-storage sources have no Trino mapping, see below).

## The story

A global electronics manufacturer sources components from suppliers tracked in a legacy ERP,
monitors warehouse stock in a WMS, places purchase orders through a procurement system, and tracks
shipments via a logistics/TMS platform — four real, independent systems that don't know about each
other, exactly the kind of "answer needs data from all four" question a federation layer exists for.

| System | Real backend | Table |
|---|---|---|
| ERP (supplier master data) | Postgres (`suppliers`) | `suppliers` |
| WMS (warehouse stock) | MySQL (`inventory`) | `warehouse_inventory` |
| Procurement | Oracle (`procurement`) | `purchase_orders` |
| Logistics/TMS | SQL Server (`logistics`) | `shipments` |

## Schema

```sql
-- suppliers (Postgres, schema "public")
suppliers(supplier_id INT PK, name VARCHAR, country VARCHAR, region VARCHAR)

-- warehouse_inventory (MySQL, schema "inventory")
warehouse_inventory(warehouse_id INT, sku VARCHAR, supplier_id INT, qty_on_hand INT)

-- purchase_orders (Oracle, schema "procurement" -- NOT "system", see below)
purchase_orders(po_id NUMBER PK, sku VARCHAR2, warehouse_id NUMBER, supplier_id NUMBER,
                qty_ordered NUMBER, status VARCHAR2)

-- shipments (SQL Server, schema "dbo", database "logistics")
shipments(shipment_id INT PK, po_id INT, carrier VARCHAR, eta_date DATE, status VARCHAR)
```

**Real join keys**: `purchase_orders.supplier_id -> suppliers.supplier_id`,
`purchase_orders.po_id -> shipments.po_id`, `purchase_orders.(sku, warehouse_id) ->
warehouse_inventory.(sku, warehouse_id)`.

**Why Oracle uses a `procurement` user, not `system`**: both ThinkingSense's own `SchemaIntrospector`
and Trino's own Oracle connector filter `SYSTEM` as a system schema (correctly — this is real,
checked behavior, not a workaround for a bug). A table owned by `SYSTEM` is invisible to either.
`seed-oracle-1-user.sql` creates a real, ordinary `procurement` application user for exactly this
reason.

**Real bugs this fixture found and fixed in `FederationStage` (the Calcite engine)**, all real,
live-caught, and now fixed — no workaround needed on your part:

1. Calcite's own JDBC driver was never explicitly loaded before `DriverManager.getConnection(...)`
   for the embedded federated connection, causing an intermittent `"No suitable driver"` error.
2. A MySQL backend's `"jdbc:mysql:"` URL was passed straight to the MariaDB driver (which rejects
   that scheme outright) inside `FederationStage`'s own connection-building path.
3. SQL Server was never wired into `FederationStage.driverClassNameFor` at all.
4. Oracle's unconstrained `NUMBER` columns (no declared precision) report `precision=0` to JDBC
   metadata, which Calcite's own type system rejects — fixed in this fixture's own schema
   (`NUMBER(10)`, not bare `NUMBER`) rather than in Calcite itself.
5. **The big one**: `FederationStage` mounts every backend under its own *backend name*, and used
   that same backend name as the literal schema-name filter when asking the backend for its real
   tables — silently correct only when an operator names a backend identically to its own real
   database schema (true of this whole codebase's own `FederationStageTest` fixture, by design,
   which is why this went unnoticed for so long), and silently wrong whenever a backend's name
   differs from its real schema (true of 3 of this fixture's 4 backends: `suppliers`/`public`,
   `logistics`/`dbo`, `inventory`/`inventory`). Fixed two ways: `OMNIGATE_ROUTER_SCHEMA_RULES`
   labels are now correctly rewritten from the real native schema name to the real backend/mount
   name before Calcite ever sees the SQL, and the JDBC schema filter itself now asks the real
   connection for its own real default schema (`Connection#getSchema()`) instead of guessing from
   the backend's name.

## Seeded data (real, exact — use these numbers when asserting results)

- **Suppliers**: Mekong Circuits Co (Vietnam), Rhineland Precision GmbH (Germany), Saigon
  Semiconductor Ltd (Vietnam), Great Lakes Fabrication (USA).
- **Purchase orders**: 5001 (SKU-CTRL-9001, supplier 1/Vietnam, qty 500, IN_TRANSIT), 5002
  (SKU-CAP-4420, supplier 3/Vietnam, qty 2000, IN_TRANSIT), 5003 (SKU-RES-1100, supplier 2/Germany,
  qty 300, DELIVERED), 5004 (SKU-CTRL-9001, supplier 1/Vietnam, qty 150, IN_TRANSIT).
- **Shipments**: 9001->5001 (Pacific Direct Freight, 2026-09-15, IN_TRANSIT), 9002->5002 (Pacific
  Direct Freight, 2026-09-18, IN_TRANSIT), 9003->5003 (EuroCargo Line, 2026-08-30, DELIVERED),
  9004->5004 (TransPacific Express, 2026-09-20, IN_TRANSIT).
- **Warehouse inventory**: (100, SKU-CTRL-9001, supplier 1, 240), (100, SKU-CAP-4420, supplier 3,
  1800), (200, SKU-CTRL-9001, supplier 1, 60), (200, SKU-RES-1100, supplier 2, 500).

**The canonical demo question and its correct answer**, live-verified through BOTH the default
Calcite engine and the opt-in Trino engine (`OMNIGATE_QUERY_ENGINE`/`OMNIGATE_TRINO_JDBC_URL` —
see `docs/deployment/trino-cluster.md`) — *"List each purchase order whose shipment status is
IN_TRANSIT and whose supplier country is Vietnam, including po_id, sku, quantity ordered, carrier,
eta_date, and current warehouse qty_on_hand for that sku"*:

| po_id | sku | qty_ordered | carrier | eta_date | qty_on_hand |
|---|---|---|---|---|---|
| 5001 | SKU-CTRL-9001 | 500 | Pacific Direct Freight | 2026-09-15 | 240 |
| 5002 | SKU-CAP-4420 | 2000 | Pacific Direct Freight | 2026-09-18 | 1800 |
| 5004 | SKU-CTRL-9001 | 150 | TransPacific Express | 2026-09-20 | 60 |

(PO 5003 is correctly excluded — DELIVERED, not IN_TRANSIT.)

## Quick start

```bash
cd fixtures/supply-chain
docker compose up -d
./seed.sh
source omnigate.env.example   # or copy its values into your own env
java -jar ../../target/omnigate.jar
```

Tear down when done: `./teardown.sh` (stops and removes the containers; the seed scripts
themselves are untouched and will recreate everything on the next `./seed.sh`).

## Known real quirks (already handled by seed.sh, documented here for context)

- **MySQL 8's `caching_sha2_password`**: the MariaDB JDBC driver (used for MySQL backends) needs
  `allowPublicKeyRetrieval=true&useSSL=false` on the connection URL — already in
  `omnigate.env.example`.
- **`mcr.microsoft.com/mssql-tools` runs under amd64 emulation on Apple Silicon** — works, just
  slower to start; `seed.sh` accounts for this with a real readiness wait.
- **A bind-mounted file under `/tmp` is NOT visible inside a Docker container on macOS** (Docker
  Desktop's default file sharing doesn't include `/tmp`/`/var/folders`) — `seed.sh` uses `$(pwd)`
  (this directory, under `/Users/...`) for every volume mount for exactly this reason.
