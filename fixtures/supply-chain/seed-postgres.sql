-- Backend: suppliers (Postgres) -- the legacy ERP system's supplier master data.
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id INT PRIMARY KEY,
  name VARCHAR(80),
  country VARCHAR(40),
  region VARCHAR(40)
);
DELETE FROM suppliers;
INSERT INTO suppliers VALUES
 (1, 'Mekong Circuits Co', 'Vietnam', 'APAC'),
 (2, 'Rhineland Precision GmbH', 'Germany', 'EMEA'),
 (3, 'Saigon Semiconductor Ltd', 'Vietnam', 'APAC'),
 (4, 'Great Lakes Fabrication', 'USA', 'AMER');
