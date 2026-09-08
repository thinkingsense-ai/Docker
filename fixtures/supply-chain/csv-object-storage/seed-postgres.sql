-- Supply chain fixture, Tier C: mixed connectors -- suppliers and warehouse_inventory live as
-- real CSV files (object storage / S3-shaped in production, a local directory for this demo --
-- see README.md), while procurement and logistics stay in a real Postgres database. Only the
-- database-resident tables need seeding here; the CSVs are already real files in this directory.

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
