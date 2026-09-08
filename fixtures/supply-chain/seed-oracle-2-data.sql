-- Backend: procurement (Oracle). Run as the "procurement" user created by seed-oracle-1-user.sql
-- -- the procurement system's purchase orders.
BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE purchase_orders';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN -- ORA-00942: table doesn't exist -- fine, first run
    RAISE;
  END IF;
END;
/
-- Bounded NUMBER precision deliberately, not bare NUMBER: Oracle reports an unconstrained NUMBER
-- column to JDBC metadata as precision=0/scale=-127, which Calcite's own JdbcSchema type
-- inference rejects outright ("DECIMAL precision 0 must be between 1 and 19") -- a real,
-- separate Calcite/Oracle-adapter limitation (see docs/deployment/trino-cluster.md and this
-- fixture's own README for the full explanation). Bounding precision here is both the real fix
-- for this fixture's own Calcite-path compatibility AND correct schema practice regardless.
CREATE TABLE purchase_orders (
  po_id NUMBER(10) PRIMARY KEY,
  sku VARCHAR2(20),
  warehouse_id NUMBER(10),
  supplier_id NUMBER(10),
  qty_ordered NUMBER(10),
  status VARCHAR2(20)
);
INSERT INTO purchase_orders VALUES (5001, 'SKU-CTRL-9001', 100, 1, 500, 'IN_TRANSIT');
INSERT INTO purchase_orders VALUES (5002, 'SKU-CAP-4420', 100, 3, 2000, 'IN_TRANSIT');
INSERT INTO purchase_orders VALUES (5003, 'SKU-RES-1100', 200, 2, 300, 'DELIVERED');
INSERT INTO purchase_orders VALUES (5004, 'SKU-CTRL-9001', 200, 1, 150, 'IN_TRANSIT');
COMMIT;
EXIT;
