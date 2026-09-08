-- Backend: logistics (SQL Server) -- the logistics/TMS system's shipments.
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'logistics')
BEGIN
  CREATE DATABASE logistics;
END
GO
USE logistics;
GO
IF OBJECT_ID('shipments', 'U') IS NOT NULL DROP TABLE shipments;
CREATE TABLE shipments (
  shipment_id INT PRIMARY KEY,
  po_id INT,
  carrier VARCHAR(40),
  eta_date DATE,
  status VARCHAR(20)
);
INSERT INTO shipments VALUES (9001, 5001, 'Pacific Direct Freight', '2026-09-15', 'IN_TRANSIT');
INSERT INTO shipments VALUES (9002, 5002, 'Pacific Direct Freight', '2026-09-18', 'IN_TRANSIT');
INSERT INTO shipments VALUES (9003, 5003, 'EuroCargo Line', '2026-08-30', 'DELIVERED');
INSERT INTO shipments VALUES (9004, 5004, 'TransPacific Express', '2026-09-20', 'IN_TRANSIT');
GO
