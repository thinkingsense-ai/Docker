-- IT & operational risk demo data (a mid-size financial firm), Postgres half. Invented; no real firm's data.
-- Two data sources, so the demo also shows a question answered across two different databases:
--   risk      (this file, Postgres)  business services with recovery objectives, applications, outages,
--                                    risk register, risk appetite, controls and their tests, key risk
--                                    indicators, audit issues
--   security  (seed-it-risk-mariadb.sql, MariaDB)  third-party vendors, vulnerabilities
-- Each source is registered under the same name as its schema/database ("risk", "security"); the federation
-- planner needs that. applications.vendor_id and vulnerabilities.app_id point across the two.
-- Dates are relative to the day this script runs (CURRENT_DATE), so "overdue", "last 12 months" and "not tested
-- recently" stay meaningful for a demo run soon after install.

CREATE SCHEMA IF NOT EXISTS risk;

-- ------------------------------------------------------------------ operations
CREATE TABLE risk.business_services (
  service_id INT PRIMARY KEY,
  name VARCHAR(60),
  tier INT,                    -- 1 = most critical
  owner VARCHAR(40),
  rto_minutes INT,             -- recovery time objective: longest acceptable outage
  rpo_minutes INT,             -- recovery point objective: longest acceptable data loss
  revenue_per_hour_usd INT
);
INSERT INTO risk.business_services VALUES
 (1, 'Payments Processing',     1, 'Dana Whitfield',   30,   5, 480000),
 (2, 'Trading Platform',        1, 'Marcus Oyelaran',  15,   1, 650000),
 (3, 'Online Banking',          1, 'Priya Raman',      60,  15, 210000),
 (4, 'Customer Onboarding',     2, 'Lena Hoffmann',   240,  60,  45000),
 (5, 'Regulatory Reporting',    2, 'Tomas Eriksen',   480, 240,  12000),
 (6, 'Treasury Management',     1, 'Aisha Bello',      45,  10, 320000),
 (7, 'Internal HR Portal',      3, 'Grace Lindqvist', 1440, 480,   1500),
 (8, 'Document Management',     3, 'Ravi Menon',      960, 240,   3000);

CREATE TABLE risk.applications (
  app_id INT PRIMARY KEY,
  name VARCHAR(60),
  service_id INT,
  hosting VARCHAR(20),
  vendor_id INT                -- security.vendors (MariaDB); NULL for in-house systems
);
INSERT INTO risk.applications VALUES
 ( 1, 'Payment Gateway',          1, 'On-prem', NULL),
 ( 2, 'Card Switch',              1, 'On-prem', 3),
 ( 3, 'Fraud Scoring Engine',     1, 'AWS',     5),
 ( 4, 'Order Management System',  2, 'On-prem', NULL),
 ( 5, 'Market Data Feed',         2, 'AWS',     2),
 ( 6, 'Web Banking Portal',       3, 'Azure',   NULL),
 ( 7, 'Mobile Banking API',       3, 'Azure',   1),
 ( 8, 'Identity Provider',        3, 'Azure',   1),
 ( 9, 'KYC Verification',         4, 'AWS',     6),
 (10, 'Document Capture',         4, 'AWS',     6),
 (11, 'Regulatory Data Mart',     5, 'On-prem', NULL),
 (12, 'Treasury Workstation',     6, 'On-prem', 4),
 (13, 'Cash Forecasting',         6, 'GCP',     NULL),
 (14, 'HR Portal',                7, 'AWS',     7),
 (15, 'Records Archive',          8, 'On-prem', 8),
 (16, 'Collaboration Suite',      8, 'Azure',   1);

CREATE TABLE risk.incidents (
  incident_id INT PRIMARY KEY,
  app_id INT,
  started_on DATE,
  duration_minutes INT,
  severity VARCHAR(10),        -- SEV1 worst
  root_cause VARCHAR(30)
);
INSERT INTO risk.incidents VALUES
 ( 1,  1, CURRENT_DATE - 14,  52, 'SEV1', 'Change failure'),
 ( 2,  1, CURRENT_DATE - 160, 18, 'SEV2', 'Capacity'),
 ( 3,  2, CURRENT_DATE - 40,  95, 'SEV1', 'Vendor outage'),
 ( 4,  2, CURRENT_DATE - 300, 22, 'SEV2', 'Hardware'),
 ( 5,  3, CURRENT_DATE - 75,  31, 'SEV2', 'Change failure'),
 ( 6,  4, CURRENT_DATE - 25,  41, 'SEV1', 'Change failure'),
 ( 7,  4, CURRENT_DATE - 210, 12, 'SEV3', 'Capacity'),
 ( 8,  5, CURRENT_DATE - 60,  28, 'SEV2', 'Vendor outage'),
 ( 9,  5, CURRENT_DATE - 330, 9,  'SEV3', 'Network'),
 (10,  6, CURRENT_DATE - 9,   120,'SEV1', 'Cyber attack'),
 (11,  6, CURRENT_DATE - 120, 35,  'SEV2', 'Capacity'),
 (12,  7, CURRENT_DATE - 33,  48,  'SEV2', 'Vendor outage'),
 (13,  8, CURRENT_DATE - 88,  70,  'SEV1', 'Vendor outage'),
 (14,  9, CURRENT_DATE - 50,  210, 'SEV2', 'Vendor outage'),
 (15, 10, CURRENT_DATE - 190, 85,  'SEV3', 'Software defect'),
 (16, 11, CURRENT_DATE - 100, 510, 'SEV2', 'Hardware'),
 (17, 12, CURRENT_DATE - 20,  64,  'SEV1', 'Vendor outage'),
 (18, 12, CURRENT_DATE - 240, 25,  'SEV3', 'Software defect'),
 (19, 13, CURRENT_DATE - 70,  15,  'SEV3', 'Change failure'),
 (20, 14, CURRENT_DATE - 45,  180, 'SEV3', 'Vendor outage'),
 (21, 15, CURRENT_DATE - 280, 600, 'SEV3', 'Hardware'),
 (22, 16, CURRENT_DATE - 15,  55,  'SEV3', 'Vendor outage'),
 (23,  1, CURRENT_DATE - 400, 40,  'SEV2', 'Change failure'),
 (24,  4, CURRENT_DATE - 450, 66,  'SEV1', 'Software defect');

-- ------------------------------------------------------------------ governance
CREATE TABLE risk.risk_appetite (
  category VARCHAR(30) PRIMARY KEY,
  max_residual_score INT      -- the board's tolerance: a residual score above this is outside appetite
);
INSERT INTO risk.risk_appetite VALUES
 ('Technology', 12), ('Cyber', 9), ('Third party', 12), ('Operational resilience', 10), ('Compliance', 8);

CREATE TABLE risk.risk_register (
  risk_id INT PRIMARY KEY,
  title VARCHAR(90),
  category VARCHAR(30),
  service_id INT,             -- risk.business_services
  owner VARCHAR(40),
  likelihood INT,             -- 1-5
  impact INT,                 -- 1-5
  inherent_score INT,         -- before controls
  residual_score INT,         -- after controls (likelihood x impact, as assessed)
  status VARCHAR(15)
);
INSERT INTO risk.risk_register VALUES
 ( 1, 'Card switch vendor outage halts card payments',            'Third party',            1, 'Dana Whitfield',   3, 5, 20, 15, 'Mitigating'),
 ( 2, 'Ransomware encrypts trading order data',                    'Cyber',                  2, 'Marcus Oyelaran',  3, 5, 25, 15, 'Mitigating'),
 ( 3, 'Unpatched critical flaws on payment systems',               'Cyber',                  1, 'Dana Whitfield',   4, 4, 20, 16, 'Open'),
 ( 4, 'Identity provider failure locks customers out',             'Technology',             3, 'Priya Raman',      2, 5, 16, 10, 'Mitigating'),
 ( 5, 'Failed change causes payment outage',                       'Operational resilience', 1, 'Dana Whitfield',   4, 4, 16, 12, 'Open'),
 ( 6, 'Treasury software vendor not assessed in over a year',      'Third party',            6, 'Aisha Bello',      3, 4, 16, 12, 'Open'),
 ( 7, 'Market data loss during trading hours',                     'Operational resilience', 2, 'Marcus Oyelaran',  2, 4, 12, 8,  'Mitigating'),
 ( 8, 'Regulatory report submitted late or incorrect',             'Compliance',             5, 'Tomas Eriksen',    3, 3, 12, 9,  'Open'),
 ( 9, 'KYC vendor outage delays onboarding',                       'Third party',            4, 'Lena Hoffmann',    3, 3, 12, 9,  'Mitigating'),
 (10, 'Data centre hardware failure on regulatory data mart',      'Technology',             5, 'Tomas Eriksen',    2, 3, 8,  6,  'Accepted'),
 (11, 'HR portal data exposure',                                   'Cyber',                  7, 'Grace Lindqvist',  2, 3, 9,  6,  'Accepted'),
 (12, 'Archive hardware degradation',                              'Technology',             8, 'Ravi Menon',       3, 2, 6,  6,  'Accepted'),
 (13, 'Cloud region outage affects online banking',                'Technology',             3, 'Priya Raman',      2, 4, 12, 8,  'Mitigating'),
 (14, 'Insider misuse of treasury payment approvals',              'Operational resilience', 6, 'Aisha Bello',      2, 5, 15, 10, 'Mitigating');

CREATE TABLE risk.controls (
  control_id INT PRIMARY KEY,
  title VARCHAR(90),
  control_type VARCHAR(15),   -- Preventive / Detective / Corrective
  risk_id INT,
  owner VARCHAR(40),
  test_every_days INT,        -- how often the control must be tested
  last_tested DATE,
  last_result VARCHAR(20)     -- Effective / Partially effective / Ineffective
);
INSERT INTO risk.controls VALUES
 ( 1, 'Warm standby for card switch',                  'Corrective', 1, 'Dana Whitfield',   180, CURRENT_DATE - 90,  'Effective'),
 ( 2, 'Dual-vendor routing for card payments',         'Preventive', 1, 'Dana Whitfield',   365, CURRENT_DATE - 410, 'Partially effective'),
 ( 3, 'Immutable backups of order data',               'Corrective', 2, 'Marcus Oyelaran',  90,  CURRENT_DATE - 60,  'Effective'),
 ( 4, 'Endpoint detection and response',               'Detective',  2, 'Marcus Oyelaran',  90,  CURRENT_DATE - 140, 'Effective'),
 ( 5, 'Critical patch within 14 days',                 'Preventive', 3, 'Dana Whitfield',   90,  CURRENT_DATE - 100, 'Ineffective'),
 ( 6, 'Vulnerability scanning of payment systems',     'Detective',  3, 'Dana Whitfield',   30,  CURRENT_DATE - 12,  'Effective'),
 ( 7, 'Identity provider failover',                    'Corrective', 4, 'Priya Raman',      180, CURRENT_DATE - 200, 'Partially effective'),
 ( 8, 'Change approval board and rollback plan',       'Preventive', 5, 'Dana Whitfield',   180, CURRENT_DATE - 170, 'Partially effective'),
 ( 9, 'Annual third-party security assessment',        'Detective',  6, 'Aisha Bello',      365, CURRENT_DATE - 520, 'Ineffective'),
 (10, 'Secondary market data provider',                'Corrective', 7, 'Marcus Oyelaran',  365, CURRENT_DATE - 150, 'Effective'),
 (11, 'Report completeness reconciliation',            'Detective',  8, 'Tomas Eriksen',    90,  CURRENT_DATE - 30,  'Effective'),
 (12, 'KYC provider SLA monitoring',                   'Detective',  9, 'Lena Hoffmann',    90,  CURRENT_DATE - 130, 'Effective'),
 (13, 'Hardware replacement programme',                'Preventive', 10,'Tomas Eriksen',    365, CURRENT_DATE - 300, 'Effective'),
 (14, 'Multi-region deployment of web banking',        'Corrective', 13,'Priya Raman',      365, CURRENT_DATE - 180, 'Effective'),
 (15, 'Dual approval on treasury payments',            'Preventive', 14,'Aisha Bello',      180, CURRENT_DATE - 60,  'Effective'),
 (16, 'Quarterly access recertification',             'Detective',  14,'Aisha Bello',      90,  CURRENT_DATE - 190, 'Partially effective');

CREATE TABLE risk.key_risk_indicators (
  kri_id INT PRIMARY KEY,
  name VARCHAR(70),
  category VARCHAR(30),
  amber_at NUMERIC(8,2),      -- the reading at which the indicator turns amber
  red_at NUMERIC(8,2),        -- ... and red
  higher_is_worse BOOLEAN
);
INSERT INTO risk.key_risk_indicators VALUES
 (1, 'Critical vulnerabilities past patch deadline',       'Cyber',                  2,    4,    TRUE),
 (2, 'Tier-1 outage minutes in the last 90 days',           'Operational resilience', 100,  200,  TRUE),
 (3, 'Tier-1 and tier-2 vendors not assessed in 12 months',  'Third party',            1,    3,    TRUE),
 (4, 'Controls overdue for testing',                         'Operational resilience', 2,    4,    TRUE),
 (5, 'Overdue audit issues',                                 'Compliance',             1,    3,    TRUE),
 (6, 'Change failure rate (percent)',                        'Technology',             10,   15,   TRUE),
 (7, 'Backup restore success rate (percent)',                'Operational resilience', 98,   95,   FALSE);

CREATE TABLE risk.kri_readings (
  kri_id INT,
  month_start DATE,
  reading NUMERIC(8,2),
  PRIMARY KEY (kri_id, month_start)
);
INSERT INTO risk.kri_readings
SELECT k, (date_trunc('month', CURRENT_DATE) - (m || ' months')::interval)::date, v
FROM (VALUES
 (1, 0, 5),(1, 1, 3),(1, 2, 2),
 (2, 0, 549),(2, 1, 210),(2, 2, 120),
 (3, 0, 3),(3, 1, 3),(3, 2, 2),
 (4, 0, 7),(4, 1, 6),(4, 2, 3),
 (5, 0, 4),(5, 1, 3),(5, 2, 2),
 (6, 0, 11),(6, 1, 13),(6, 2, 9),
 (7, 0, 97),(7, 1, 99),(7, 2, 99)
) AS t(k, m, v);

CREATE TABLE risk.audit_issues (
  issue_id INT PRIMARY KEY,
  risk_id INT,
  title VARCHAR(90),
  severity VARCHAR(10),
  opened_on DATE,
  due_on DATE,
  status VARCHAR(10),         -- Open / Closed
  owner VARCHAR(40)
);
INSERT INTO risk.audit_issues VALUES
 (1, 3,  'Critical patches not applied within policy',            'High',   CURRENT_DATE - 200, CURRENT_DATE - 40, 'Open',   'Dana Whitfield'),
 (2, 6,  'Treasury vendor assessment overdue',                    'High',   CURRENT_DATE - 150, CURRENT_DATE - 20, 'Open',   'Aisha Bello'),
 (3, 1,  'Dual-vendor routing never tested end to end',           'Medium', CURRENT_DATE - 120, CURRENT_DATE + 30, 'Open',   'Dana Whitfield'),
 (4, 5,  'Rollback plans missing for four releases',              'Medium', CURRENT_DATE - 90,  CURRENT_DATE - 5,  'Open',   'Dana Whitfield'),
 (5, 14, 'Access recertification skipped last quarter',           'Medium', CURRENT_DATE - 110, CURRENT_DATE - 10, 'Open',   'Aisha Bello'),
 (6, 8,  'Regulatory report reconciliation gaps',                 'Low',    CURRENT_DATE - 60,  CURRENT_DATE + 45, 'Open',   'Tomas Eriksen'),
 (7, 4,  'Identity provider failover test overdue',               'High',   CURRENT_DATE - 80,  CURRENT_DATE + 15, 'Open',   'Priya Raman'),
 (8, 13, 'Cloud region failover plan out of date',                'Low',    CURRENT_DATE - 300, CURRENT_DATE - 100,'Closed', 'Priya Raman'),
 (9, 9,  'KYC provider contract lacks outage SLA',                'Low',    CURRENT_DATE - 220, CURRENT_DATE - 60, 'Closed', 'Lena Hoffmann');
