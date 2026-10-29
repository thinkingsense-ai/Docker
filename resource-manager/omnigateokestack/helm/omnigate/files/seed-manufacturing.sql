
-- ---------------------------------------------------------------------------------------------
-- Parts, bills of materials, supplier capabilities and quotes (a small robotics-hardware story).
--
-- Applied by the ensure-manufacturing-demo init container (templates/_helpers.tpl) on every pod start, but
-- only when inventory.parts does not exist yet and the three demo schemas are there, so a new install and an
-- upgraded one end up the same and a restart never touches the rows. One transaction: all or nothing.
--
-- Added to the SAME three schemas on purpose, not a fourth: the free edition allows three
-- backends, and every schema here is registered as one. Supplier knowledge lives in `suppliers`,
-- product and catalog data in `inventory`, requests for quote and quotes in `procurement`, so
-- the interesting questions are still cross-schema joins. Everything below is invented demo data;
-- the existing rows above are untouched (their demo questions and checks keep their answers).
-- ---------------------------------------------------------------------------------------------

-- Four more suppliers (ids 5-8). The first four above have no purchase orders for these parts.
INSERT INTO suppliers.suppliers VALUES
 (5, 'Lone Star Machining Inc', 'USA', 'AMER'),
 (6, 'Kansai Precision Works', 'Japan', 'APAC'),
 (7, 'Bavarian Castings AG', 'Germany', 'EMEA'),
 (8, 'Monterrey Sheet Metal SA', 'Mexico', 'AMER')
ON CONFLICT DO NOTHING;

-- What each supplier's sites can make, and the tightest tolerance they can hold for it.
CREATE TABLE IF NOT EXISTS suppliers.supplier_capabilities (
  capability_id INT PRIMARY KEY,
  supplier_id INT,
  process VARCHAR(40),
  material VARCHAR(30),
  min_tolerance_mm NUMERIC(5,3),
  max_dimension_mm INT
);
INSERT INTO suppliers.supplier_capabilities VALUES
 (1, 2, '5-axis CNC milling', 'Aluminum', 0.010, 600),
 (2, 2, '5-axis CNC milling', 'Steel', 0.010, 500),
 (3, 2, 'Grinding', 'Steel', 0.003, 300),
 (4, 4, 'Sheet metal', 'Aluminum', 0.100, 2400),
 (5, 4, 'Welding', 'Steel', 0.500, 3000),
 (6, 5, '5-axis CNC milling', 'Aluminum', 0.020, 800),
 (7, 5, 'CNC turning', 'Steel', 0.015, 400),
 (8, 6, '5-axis CNC milling', 'Aluminum', 0.010, 400),
 (9, 6, 'CNC turning', 'Steel', 0.005, 300),
 (10, 6, 'Grinding', 'Steel', 0.002, 250),
 (11, 7, 'Die casting', 'Aluminum', 0.150, 500),
 (12, 8, 'Sheet metal', 'Aluminum', 0.100, 1800),
 (13, 8, 'Injection molding', 'ABS', 0.150, 400),
 (14, 1, 'PCB assembly', 'Electronics', 0.050, 300);

CREATE TABLE IF NOT EXISTS suppliers.supplier_certifications (
  cert_id INT PRIMARY KEY,
  supplier_id INT,
  certification VARCHAR(30),
  expires_on DATE
);
INSERT INTO suppliers.supplier_certifications VALUES
 (1, 2, 'ISO 9001', '2027-06-30'),
 (2, 2, 'AS9100', '2027-03-31'),
 (3, 4, 'ISO 9001', '2027-09-30'),
 (4, 4, 'AS9100', '2026-12-31'),
 (5, 5, 'ISO 9001', '2027-05-31'),
 (6, 5, 'AS9100', '2027-08-31'),
 (7, 6, 'ISO 9001', '2028-01-31'),
 (8, 6, 'IATF 16949', '2027-11-30'),
 (9, 7, 'ISO 9001', '2027-04-30'),
 (10, 7, 'IATF 16949', '2027-04-30'),
 (11, 8, 'ISO 9001', '2027-02-28'),
 (12, 1, 'ISO 9001', '2027-10-31');

-- Product side: two assemblies (a robot joint module and a gripper), their parts, a standard-parts
-- catalog, and how closely a part matches a catalog item. SKU-CTRL-9001 is the existing controller
-- board from the stock data above, so the bill of materials also joins to real stock.
CREATE TABLE IF NOT EXISTS inventory.parts (
  part_no VARCHAR(20) PRIMARY KEY,
  description VARCHAR(60),
  category VARCHAR(30),
  source_type VARCHAR(10),
  material VARCHAR(30),
  process VARCHAR(40),
  tolerance_mm NUMERIC(5,3),
  revision CHAR(1)
);
INSERT INTO inventory.parts VALUES
 ('SKU-CTRL-9001', 'Joint controller board', 'Electronics', 'CATALOG', 'Electronics', NULL, NULL, 'A'),
 ('JM-1001', 'Joint housing', 'Housing', 'CUSTOM', 'Aluminum', '5-axis CNC milling', 0.020, 'C'),
 ('JM-1002', 'Output flange', 'Flange', 'CUSTOM', 'Aluminum', '5-axis CNC milling', 0.010, 'B'),
 ('JM-1003', 'Motor mount bracket', 'Bracket', 'CUSTOM', 'Aluminum', 'Sheet metal', 0.100, 'A'),
 ('JM-1004', 'Cable guard cover', 'Cover', 'CUSTOM', 'ABS', 'Injection molding', 0.150, 'A'),
 ('JM-1005', 'Cross-roller bearing 60 mm', 'Bearing', 'CATALOG', 'Steel', NULL, NULL, 'A'),
 ('JM-1006', 'Strain wave gear reducer', 'Reducer', 'CATALOG', 'Steel', NULL, NULL, 'A'),
 ('JM-1007', 'Hollow shaft', 'Shaft', 'CUSTOM', 'Steel', 'CNC turning', 0.005, 'B'),
 ('JM-1008', 'Shaft collar 20 mm', 'Collar', 'CUSTOM', 'Steel', 'CNC turning', 0.050, 'A'),
 ('JM-1009', 'Socket head cap screw M4x12', 'Fastener', 'CATALOG', 'Steel', NULL, NULL, 'A'),
 ('JM-1010', 'Dowel pin 6x20', 'Fastener', 'CATALOG', 'Steel', NULL, NULL, 'A'),
 ('JM-1011', 'Encoder board', 'Electronics', 'CUSTOM', 'Electronics', 'PCB assembly', NULL, 'D'),
 ('JM-1012', 'Sealed connector 8-pin', 'Connector', 'CATALOG', 'Plastic', NULL, NULL, 'A'),
 ('GR-2001', 'Gripper finger', 'Finger', 'CUSTOM', 'Aluminum', '5-axis CNC milling', 0.020, 'A'),
 ('GR-2002', 'Gripper body', 'Housing', 'CUSTOM', 'Aluminum', 'Die casting', 0.150, 'B');

CREATE TABLE IF NOT EXISTS inventory.assemblies (
  assembly_no VARCHAR(12) PRIMARY KEY,
  description VARCHAR(60),
  target_build_qty INT,
  need_date DATE
);
INSERT INTO inventory.assemblies VALUES
 ('JM-200', 'Robot joint module', 50, '2026-12-15'),
 ('GR-50', 'Two-finger gripper', 100, '2027-01-15');

CREATE TABLE IF NOT EXISTS inventory.bom_lines (
  assembly_no VARCHAR(12),
  line_no INT,
  part_no VARCHAR(20),
  qty_per INT,
  PRIMARY KEY (assembly_no, line_no)
);
INSERT INTO inventory.bom_lines VALUES
 ('JM-200', 1, 'JM-1001', 1),
 ('JM-200', 2, 'JM-1002', 1),
 ('JM-200', 3, 'JM-1003', 1),
 ('JM-200', 4, 'JM-1004', 1),
 ('JM-200', 5, 'JM-1005', 1),
 ('JM-200', 6, 'JM-1006', 1),
 ('JM-200', 7, 'JM-1007', 1),
 ('JM-200', 8, 'JM-1008', 2),
 ('JM-200', 9, 'JM-1009', 24),
 ('JM-200', 10, 'JM-1010', 4),
 ('JM-200', 11, 'JM-1011', 1),
 ('JM-200', 12, 'JM-1012', 1),
 ('JM-200', 13, 'SKU-CTRL-9001', 1),
 ('GR-50', 1, 'GR-2001', 2),
 ('GR-50', 2, 'GR-2002', 1),
 ('GR-50', 3, 'JM-1003', 1),
 ('GR-50', 4, 'JM-1009', 8),
 ('GR-50', 5, 'JM-1012', 1);

CREATE TABLE IF NOT EXISTS inventory.catalog_items (
  catalog_sku VARCHAR(24) PRIMARY KEY,
  description VARCHAR(60),
  category VARCHAR(30),
  unit_price_usd NUMERIC(8,2),
  in_stock_qty INT,
  lead_time_days INT
);
INSERT INTO inventory.catalog_items VALUES
 ('CAT-XRB-60', 'Cross-roller bearing 60 mm', 'Bearing', 184.00, 35, 3),
 ('CAT-SWG-60', 'Strain wave gear reducer 60 mm, ratio 100', 'Reducer', 612.00, 12, 10),
 ('CAT-COL-20', 'Shaft collar 20 mm, clamp type', 'Collar', 3.80, 2400, 2),
 ('CAT-SHCS-M4X12', 'Socket head cap screw M4x12, A2', 'Fastener', 0.14, 50000, 2),
 ('CAT-DWL-6X20', 'Dowel pin 6x20, hardened', 'Fastener', 0.46, 12000, 2),
 ('CAT-CON-8P', 'Sealed connector 8-pin', 'Connector', 7.25, 800, 5),
 ('CAT-BKT-L40', 'L-bracket 40x40x3 aluminum', 'Bracket', 2.95, 1500, 2);

-- A part can match a catalog item with some confidence and a stated basis; below 1.00 a person decides.
CREATE TABLE IF NOT EXISTS inventory.part_equivalences (
  part_no VARCHAR(20),
  catalog_sku VARCHAR(24),
  match_confidence NUMERIC(3,2),
  basis VARCHAR(80),
  PRIMARY KEY (part_no, catalog_sku)
);
INSERT INTO inventory.part_equivalences VALUES
 ('JM-1005', 'CAT-XRB-60', 1.00, 'Same bearing, dimensions match'),
 ('JM-1006', 'CAT-SWG-60', 0.95, 'Ratio and flange match, backlash not checked'),
 ('JM-1008', 'CAT-COL-20', 0.90, 'Bore and width match, tolerance is looser'),
 ('JM-1009', 'CAT-SHCS-M4X12', 1.00, 'Same standard'),
 ('JM-1010', 'CAT-DWL-6X20', 1.00, 'Same standard'),
 ('JM-1012', 'CAT-CON-8P', 0.85, 'Pin count and seal rating match, keying differs'),
 ('JM-1003', 'CAT-BKT-L40', 0.55, 'Outline close, hole pattern differs');

-- Requests for quote on the custom parts, and the quotes that came back. promise_date is the date the
-- supplier promises delivery if the order is placed on the quote date.
CREATE TABLE IF NOT EXISTS procurement.rfqs (
  rfq_id INT PRIMARY KEY,
  part_no VARCHAR(20),
  quantity INT,
  need_date DATE,
  status VARCHAR(12)
);
INSERT INTO procurement.rfqs VALUES
 (7001, 'JM-1001', 50, '2026-12-01', 'OPEN'),
 (7002, 'JM-1002', 50, '2026-12-01', 'OPEN'),
 (7003, 'JM-1003', 150, '2026-12-15', 'OPEN'),
 (7004, 'JM-1004', 50, '2026-12-01', 'OPEN'),
 (7005, 'JM-1007', 50, '2026-12-01', 'OPEN'),
 (7006, 'JM-1011', 50, '2026-11-20', 'OPEN'),
 (7007, 'GR-2001', 200, '2027-01-05', 'OPEN'),
 (7008, 'GR-2002', 100, '2027-01-05', 'OPEN'),
 (7009, 'JM-1008', 100, '2026-12-01', 'OPEN');

CREATE TABLE IF NOT EXISTS procurement.quotes (
  quote_id INT PRIMARY KEY,
  rfq_id INT,
  supplier_id INT,
  unit_price_usd NUMERIC(8,2),
  lead_time_days INT,
  quoted_on DATE,
  promise_date DATE
);
INSERT INTO procurement.quotes VALUES
 (8001, 7001, 5, 48.50, 21, '2026-10-15', '2026-11-05'),
 (8002, 7001, 2, 61.20, 28, '2026-10-15', '2026-11-12'),
 (8003, 7001, 6, 44.10, 35, '2026-10-16', '2026-11-20'),
 (8004, 7002, 2, 92.00, 30, '2026-10-15', '2026-11-14'),
 (8005, 7002, 6, 85.40, 38, '2026-10-16', '2026-11-23'),
 (8006, 7002, 5, 79.00, 21, '2026-10-15', '2026-11-05'),
 (8007, 7003, 4, 6.80, 14, '2026-10-19', '2026-11-02'),
 (8008, 7003, 8, 5.90, 21, '2026-10-19', '2026-11-09'),
 (8009, 7004, 8, 3.10, 45, '2026-10-20', '2026-12-04'),
 (8010, 7005, 6, 58.00, 30, '2026-10-18', '2026-11-17'),
 (8011, 7005, 5, 41.50, 18, '2026-10-18', '2026-11-05'),
 (8012, 7006, 1, 38.40, 40, '2026-10-22', '2026-12-01'),
 (8013, 7007, 5, 9.80, 21, '2026-10-21', '2026-11-11'),
 (8014, 7007, 6, 8.20, 35, '2026-10-21', '2026-11-25'),
 (8015, 7007, 2, 12.10, 28, '2026-10-21', '2026-11-18'),
 (8016, 7008, 7, 11.40, 49, '2026-10-21', '2026-12-09'),
 (8017, 7009, 5, 6.40, 12, '2026-10-22', '2026-11-03'),
 (8018, 7009, 6, 5.90, 20, '2026-10-22', '2026-11-11');
