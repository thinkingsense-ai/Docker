-- IT & operational risk demo data, MariaDB half (third-party vendors and vulnerabilities). Invented.
-- Pairs with seed-it-risk-postgres.sql; this database must be registered under the name "security".
-- Dates are relative to the day this script runs (CURDATE()).

CREATE DATABASE IF NOT EXISTS security;
USE security;

CREATE TABLE vendors (
  vendor_id INT PRIMARY KEY,
  name VARCHAR(60),
  tier INT,                    -- 1 = critical third party
  country VARCHAR(30),
  last_assessed DATE,
  assessment_rating VARCHAR(10)
);
INSERT INTO vendors VALUES
 (1, 'Northwind Cloud Services',   1, 'USA',     DATE_SUB(CURDATE(), INTERVAL 120 DAY), 'Medium'),
 (2, 'Meridian Market Data',       1, 'UK',      DATE_SUB(CURDATE(), INTERVAL 410 DAY), 'Medium'),
 (3, 'Atlas Card Networks',        1, 'USA',     DATE_SUB(CURDATE(), INTERVAL 200 DAY), 'Low'),
 (4, 'Helix Treasury Software',    1, 'Germany', DATE_SUB(CURDATE(), INTERVAL 520 DAY), 'High'),
 (5, 'Sentinel Fraud Analytics',   2, 'Israel',  DATE_SUB(CURDATE(), INTERVAL 90 DAY),  'Low'),
 (6, 'Veritas Identity Checks',    2, 'USA',     DATE_SUB(CURDATE(), INTERVAL 380 DAY), 'Medium'),
 (7, 'PeopleWorks HRIS',           3, 'USA',     DATE_SUB(CURDATE(), INTERVAL 300 DAY), 'Low'),
 (8, 'Archivia Storage',           3, 'Ireland', DATE_SUB(CURDATE(), INTERVAL 600 DAY), 'Medium');

CREATE TABLE vulnerabilities (
  vuln_id INT PRIMARY KEY,
  app_id INT,
  cve VARCHAR(20),
  cvss NUMERIC(3,1),
  severity VARCHAR(10),
  found_on DATE,
  patch_due DATE,
  patched_on DATE              -- NULL = still open
);
INSERT INTO vulnerabilities VALUES
 ( 1,  1, 'CVE-2026-1101', 9.8, 'Critical', DATE_SUB(CURDATE(), INTERVAL 45 DAY), DATE_SUB(CURDATE(), INTERVAL 31 DAY), NULL),
 ( 2,  2, 'CVE-2026-1177', 9.1, 'Critical', DATE_SUB(CURDATE(), INTERVAL 20 DAY), DATE_SUB(CURDATE(), INTERVAL 6 DAY),  NULL),
 ( 3,  4, 'CVE-2026-0988', 8.8, 'High',     DATE_SUB(CURDATE(), INTERVAL 30 DAY), DATE_ADD(CURDATE(), INTERVAL 0 DAY),  NULL),
 ( 4,  6, 'CVE-2026-1204', 9.6, 'Critical', DATE_SUB(CURDATE(), INTERVAL 12 DAY), DATE_ADD(CURDATE(), INTERVAL 2 DAY),  NULL),
 ( 5,  8, 'CVE-2026-1230', 9.4, 'Critical', DATE_SUB(CURDATE(), INTERVAL 38 DAY), DATE_SUB(CURDATE(), INTERVAL 24 DAY), DATE_SUB(CURDATE(), INTERVAL 20 DAY)),
 ( 6, 12, 'CVE-2026-0871', 9.9, 'Critical', DATE_SUB(CURDATE(), INTERVAL 70 DAY), DATE_SUB(CURDATE(), INTERVAL 56 DAY), NULL),
 ( 7, 12, 'CVE-2026-0872', 7.5, 'High',     DATE_SUB(CURDATE(), INTERVAL 70 DAY), DATE_SUB(CURDATE(), INTERVAL 40 DAY), NULL),
 ( 8,  3, 'CVE-2026-1190', 8.1, 'High',     DATE_SUB(CURDATE(), INTERVAL 22 DAY), DATE_ADD(CURDATE(), INTERVAL 8 DAY),  NULL),
 ( 9,  7, 'CVE-2026-1215', 7.2, 'High',     DATE_SUB(CURDATE(), INTERVAL 50 DAY), DATE_SUB(CURDATE(), INTERVAL 20 DAY), DATE_SUB(CURDATE(), INTERVAL 25 DAY)),
 (10,  9, 'CVE-2026-1066', 9.2, 'Critical', DATE_SUB(CURDATE(), INTERVAL 33 DAY), DATE_SUB(CURDATE(), INTERVAL 19 DAY), NULL),
 (11, 11, 'CVE-2026-0755', 6.5, 'Medium',   DATE_SUB(CURDATE(), INTERVAL 90 DAY), DATE_SUB(CURDATE(), INTERVAL 30 DAY), NULL),
 (12, 14, 'CVE-2026-1099', 9.0, 'Critical', DATE_SUB(CURDATE(), INTERVAL 25 DAY), DATE_SUB(CURDATE(), INTERVAL 11 DAY), NULL),
 (13, 15, 'CVE-2026-0604', 5.3, 'Medium',   DATE_SUB(CURDATE(), INTERVAL 120 DAY),DATE_SUB(CURDATE(), INTERVAL 60 DAY), DATE_SUB(CURDATE(), INTERVAL 70 DAY)),
 (14, 16, 'CVE-2026-1188', 8.4, 'High',     DATE_SUB(CURDATE(), INTERVAL 10 DAY), DATE_ADD(CURDATE(), INTERVAL 20 DAY), NULL),
 (15,  5, 'CVE-2026-1122', 7.8, 'High',     DATE_SUB(CURDATE(), INTERVAL 28 DAY), DATE_SUB(CURDATE(), INTERVAL 1 DAY),  NULL),
 (16, 13, 'CVE-2026-1143', 6.1, 'Medium',   DATE_SUB(CURDATE(), INTERVAL 15 DAY), DATE_ADD(CURDATE(), INTERVAL 45 DAY), NULL);

