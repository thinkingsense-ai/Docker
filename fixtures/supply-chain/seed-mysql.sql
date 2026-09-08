-- Backend: inventory (MySQL) -- the warehouse management system's stock levels.
CREATE TABLE IF NOT EXISTS warehouse_inventory (
  warehouse_id INT,
  sku VARCHAR(20),
  supplier_id INT,
  qty_on_hand INT
);
DELETE FROM warehouse_inventory;
INSERT INTO warehouse_inventory VALUES
 (100, 'SKU-CTRL-9001', 1, 240),
 (100, 'SKU-CAP-4420', 3, 1800),
 (200, 'SKU-CTRL-9001', 1, 60),
 (200, 'SKU-RES-1100', 2, 500);
