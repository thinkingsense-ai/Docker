-- Copied from fixtures/supply-chain/single-postgres/seed.sql (this repo's root) -- same fixture
-- used there for a Postgres-only local docker-compose demo, reused here so this cloud stack's own
-- seeded demo actually exercises real cross-schema federation (OMNIGATE_BACKENDS in secrets.yaml
-- registers each schema as its own "backend"), not just a single flat table set.
--
-- Auto-run by the official postgres image's own /docker-entrypoint-initdb.d mechanism -- see
-- templates/postgres.yaml -- on first container start against an empty data directory.

CREATE SCHEMA IF NOT EXISTS suppliers;
CREATE TABLE IF NOT EXISTS suppliers.suppliers (
  supplier_id INT PRIMARY KEY,
  name VARCHAR(80),
  country VARCHAR(40),
  region VARCHAR(40)
);
DELETE FROM suppliers.suppliers;
INSERT INTO suppliers.suppliers VALUES
 (1, 'Mekong Circuits Co', 'Vietnam', 'APAC'),
 (2, 'Rhineland Precision GmbH', 'Germany', 'EMEA'),
 (3, 'Saigon Semiconductor Ltd', 'Vietnam', 'APAC'),
 (4, 'Great Lakes Fabrication', 'USA', 'AMER');

CREATE SCHEMA IF NOT EXISTS inventory;
CREATE TABLE IF NOT EXISTS inventory.warehouse_inventory (
  warehouse_id INT,
  sku VARCHAR(20),
  supplier_id INT,
  qty_on_hand INT
);
DELETE FROM inventory.warehouse_inventory;
INSERT INTO inventory.warehouse_inventory VALUES
 (100, 'SKU-CTRL-9001', 1, 240),
 (100, 'SKU-CAP-4420', 3, 1800),
 (200, 'SKU-CTRL-9001', 1, 60),
 (200, 'SKU-RES-1100', 2, 500);

CREATE SCHEMA IF NOT EXISTS procurement;
CREATE TABLE IF NOT EXISTS procurement.purchase_orders (
  po_id INT PRIMARY KEY,
  sku VARCHAR(20),
  warehouse_id INT,
  supplier_id INT,
  qty_ordered INT,
  status VARCHAR(20)
);
DELETE FROM procurement.purchase_orders;
INSERT INTO procurement.purchase_orders VALUES
 (5001, 'SKU-CTRL-9001', 100, 1, 500, 'IN_TRANSIT'),
 (5002, 'SKU-CAP-4420', 100, 3, 2000, 'IN_TRANSIT'),
 (5003, 'SKU-RES-1100', 200, 2, 300, 'DELIVERED'),
 (5004, 'SKU-CTRL-9001', 200, 1, 150, 'IN_TRANSIT');

CREATE SCHEMA IF NOT EXISTS logistics;
CREATE TABLE IF NOT EXISTS logistics.shipments (
  shipment_id INT PRIMARY KEY,
  po_id INT,
  carrier VARCHAR(40),
  eta_date DATE,
  status VARCHAR(20)
);
DELETE FROM logistics.shipments;
INSERT INTO logistics.shipments VALUES
 (9001, 5001, 'Pacific Direct Freight', '2026-09-15', 'IN_TRANSIT'),
 (9002, 5002, 'Pacific Direct Freight', '2026-09-18', 'IN_TRANSIT'),
 (9003, 5003, 'EuroCargo Line', '2026-08-30', 'DELIVERED'),
 (9004, 5004, 'TransPacific Express', '2026-09-20', 'IN_TRANSIT');
