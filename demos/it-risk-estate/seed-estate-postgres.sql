-- IT-risk exposure demo data, Postgres. A SIMULATED estate for an invented firm: nothing here describes a real organisation or a real system, and nobody connected to one.
-- It exists so the five exposure questions (docs/agency-it-risk-flow.md, section 6) can be asked and rated end to end. Figures are as of 2026-11-20, the date the data was written:
-- the "days" columns are stored, not computed from today, so the answers do not drift. Read-only for the app user, like every other pack. Reload by dropping the schema.
--
-- Databases and the object store are plain tables (the Server reads them as SQL sources). SharePoint and Slack are modelled the way a Kafka sink connector in upsert mode lands them:
-- one row per item or message (the latest state), with the topic, partition and offset of the last event. replay/ holds the events that arrive after start-up.

CREATE SCHEMA IF NOT EXISTS estate;
DROP TABLE IF EXISTS estate.slack_messages, estate.sharepoint_items, estate.recovery_tests, estate.dependencies, estate.changes, estate.patches, estate.buckets,
  estate.access_paths, estate.scenario_technology, estate.systems CASCADE;

CREATE TABLE estate.systems (
  system_id   INT PRIMARY KEY,
  name        VARCHAR(80) NOT NULL,
  technology  VARCHAR(60) NOT NULL,
  business_criticality INT NOT NULL CHECK (business_criticality IN (1,2,3)),
  owned_by    VARCHAR(60) NOT NULL,
  support_group VARCHAR(60) NOT NULL,
  environment VARCHAR(20) NOT NULL,
  data_class  VARCHAR(20) NOT NULL CHECK (data_class IN ('restricted','confidential','internal')),
  hosting     VARCHAR(60) NOT NULL,
  install_status VARCHAR(20) NOT NULL DEFAULT 'installed',
  end_of_support DATE,
  last_discovered DATE NOT NULL DEFAULT DATE '2026-11-20',
  loss_event  VARCHAR(160) NOT NULL DEFAULT ''
);
COMMENT ON TABLE  estate.systems IS 'SIMULATED estate inventory of an invented firm: one row per system, named toward the ServiceNow CMDB fields so a real connector changes the source and not the questions. technology is what a similar incident would affect.';
COMMENT ON COLUMN estate.systems.business_criticality IS 'ServiceNow business_criticality (Datadog tag tier): 1 is the most critical, 3 the least.';
COMMENT ON COLUMN estate.systems.owned_by IS 'ServiceNow owned_by (Datadog tag team): the team that owns the system.';
COMMENT ON COLUMN estate.systems.support_group IS 'ServiceNow support_group: the group that supports the system day to day.';
COMMENT ON COLUMN estate.systems.install_status IS 'ServiceNow install_status: installed, or retiring when the system is on its way out.';
COMMENT ON COLUMN estate.systems.end_of_support IS 'ServiceNow end_of_support: the date the vendor stops supporting this version; empty when none is announced. Invented values.';
COMMENT ON COLUMN estate.systems.last_discovered IS 'ServiceNow last_discovered: when discovery last saw the system, as of 2026-11-20.';
COMMENT ON COLUMN estate.systems.loss_event IS 'What a loss event on this system would look like in plain words: money lost, denial of service to many customers, or a breach with legal risk. Invented text.';
COMMENT ON COLUMN estate.systems.data_class IS 'restricted (card or customer-identifying data, regulated), confidential, or internal.';

CREATE TABLE estate.scenario_technology (
  case_id    VARCHAR(30) NOT NULL,
  technology VARCHAR(60) NOT NULL,
  why        VARCHAR(160) NOT NULL,
  PRIMARY KEY (case_id, technology)
);
COMMENT ON TABLE estate.scenario_technology IS 'For an incident case in the rca schema, the technologies a similar incident would hit here. The five exposure questions start from this list.';

CREATE TABLE estate.access_paths (
  system_id INT NOT NULL REFERENCES estate.systems(system_id),
  principal VARCHAR(60) NOT NULL,
  kind      VARCHAR(10) NOT NULL CHECK (kind IN ('group','vendor')),
  people    INT NOT NULL,
  level     VARCHAR(10) NOT NULL CHECK (level IN ('read','operate','admin')),
  PRIMARY KEY (system_id, principal)
);
COMMENT ON TABLE estate.access_paths IS 'Who can reach a system: a group or a vendor, how many people, and at what level. A group other than the owner team is wider than the owner.';

CREATE TABLE estate.buckets (
  bucket_id   INT PRIMARY KEY,
  system_id   INT NOT NULL REFERENCES estate.systems(system_id),
  name        VARCHAR(60) NOT NULL,
  data_class  VARCHAR(20) NOT NULL CHECK (data_class IN ('restricted','confidential','internal')),
  public_read BOOLEAN NOT NULL,
  encrypted   BOOLEAN NOT NULL,
  write_group VARCHAR(60) NOT NULL,
  write_people INT NOT NULL
);
COMMENT ON TABLE estate.buckets IS 'SIMULATED object-store inventory (an S3-compatible store): one row per bucket, with the system it belongs to, whether anyone can read it, whether it is encrypted and who can write.';

CREATE TABLE estate.patches (
  patch_id     INT PRIMARY KEY,
  system_id    INT NOT NULL REFERENCES estate.systems(system_id),
  advisory     VARCHAR(30) NOT NULL,
  severity     VARCHAR(10) NOT NULL CHECK (severity IN ('critical','high','medium')),
  released_on  DATE NOT NULL,
  due_on       DATE NOT NULL,
  applied_on   DATE,
  days_overdue INT NOT NULL,
  cve          VARCHAR(20),
  cvss_score   NUMERIC(3,1),
  known_exploited BOOLEAN NOT NULL DEFAULT FALSE,
  epss         NUMERIC(4,3)
);
COMMENT ON COLUMN estate.patches.cve IS 'Datadog cve: the vulnerability identifier the patch closes. INVENTED identifiers (CVE-2026-9xxx), none refers to a real flaw.';
COMMENT ON COLUMN estate.patches.cvss_score IS 'Datadog cvss.score: base severity 0 to 10. Invented values.';
COMMENT ON COLUMN estate.patches.known_exploited IS 'Whether the flaw is on a known-exploited-vulnerabilities list (CISA KEV in the real world). Invented values.';
COMMENT ON COLUMN estate.patches.epss IS 'Exploit prediction score, 0 to 1 (EPSS in the real world): the chance of exploitation in the next 30 days. Invented values.';
COMMENT ON TABLE  estate.patches IS 'Security patches by system. applied_on is empty while a patch is not applied.';
COMMENT ON COLUMN estate.patches.days_overdue IS 'Days past due_on as of 2026-11-20 for a patch not yet applied; 0 once applied or not yet due. Stored, not computed from today.';

CREATE TABLE estate.changes (
  change_id       INT PRIMARY KEY,
  system_id       INT NOT NULL REFERENCES estate.systems(system_id),
  summary         VARCHAR(100) NOT NULL,
  change_type     VARCHAR(20) NOT NULL,
  deployed_on     DATE NOT NULL,
  days_ago        INT NOT NULL,
  preprod_tested  BOOLEAN NOT NULL,
  peer_reviewed   BOOLEAN NOT NULL,
  change_window   VARCHAR(20) NOT NULL
);
COMMENT ON TABLE  estate.changes IS 'Changes made to systems. preprod_tested false means the change went to production without a pre-production test: the root condition (change and test capacity) in the incident brief.';
COMMENT ON COLUMN estate.changes.days_ago IS 'Days between deployed_on and 2026-11-20.';

CREATE TABLE estate.dependencies (
  system_id    INT NOT NULL REFERENCES estate.systems(system_id),
  dependent_id INT NOT NULL REFERENCES estate.systems(system_id),
  how          VARCHAR(80) NOT NULL,
  PRIMARY KEY (system_id, dependent_id)
);
COMMENT ON TABLE estate.dependencies IS 'What depends on a system: dependent_id stops working, or loses its failover, if system_id fails.';

CREATE TABLE estate.recovery_tests (
  system_id           INT PRIMARY KEY REFERENCES estate.systems(system_id),
  tested_on           DATE,
  test_kind           VARCHAR(40) NOT NULL,
  result              VARCHAR(20) NOT NULL,
  rto_target_minutes  INT,
  rto_actual_minutes  INT,
  days_since_test     INT
);
COMMENT ON TABLE  estate.recovery_tests IS 'The last recovery test for each system. A system never tested has an empty tested_on and result never tested.';
COMMENT ON COLUMN estate.recovery_tests.days_since_test IS 'Days since the last test as of 2026-11-20; empty when never tested.';

CREATE TABLE estate.sharepoint_items (
  item_id         INT PRIMARY KEY,
  site            VARCHAR(60) NOT NULL,
  library         VARCHAR(60) NOT NULL,
  name            VARCHAR(100) NOT NULL,
  kind            VARCHAR(12) NOT NULL CHECK (kind IN ('runbook','credential','recovery','other')),
  shared_with     VARCHAR(12) NOT NULL CHECK (shared_with IN ('owners','team','department','company','external','anyone')),
  audience        INT NOT NULL,
  system_id       INT REFERENCES estate.systems(system_id),
  modified_at     TIMESTAMP NOT NULL,
  kafka_topic     VARCHAR(40) NOT NULL,
  kafka_partition INT NOT NULL,
  kafka_offset    BIGINT NOT NULL
);
COMMENT ON TABLE  estate.sharepoint_items IS 'SIMULATED SharePoint documents, as a Kafka sink connector in upsert mode would land them: the latest state of each item, with the topic, partition and offset of its last event. No real SharePoint was read.';
COMMENT ON COLUMN estate.sharepoint_items.shared_with IS 'Widest audience the item is shared with: owners, team, department, company, external or anyone. audience is how many people that is.';
COMMENT ON COLUMN estate.sharepoint_items.kind IS 'What the document is: a runbook, a credential (passwords or tokens), recovery steps, or something else.';

CREATE TABLE estate.slack_messages (
  message_id      INT PRIMARY KEY,
  channel         VARCHAR(40) NOT NULL,
  channel_kind    VARCHAR(10) NOT NULL CHECK (channel_kind IN ('private','public','external')),
  members         INT NOT NULL,
  author          VARCHAR(40) NOT NULL,
  kind            VARCHAR(12) NOT NULL CHECK (kind IN ('runbook','credential','recovery','chat')),
  system_id       INT REFERENCES estate.systems(system_id),
  excerpt         VARCHAR(200) NOT NULL,
  posted_at       TIMESTAMP NOT NULL,
  kafka_topic     VARCHAR(40) NOT NULL,
  kafka_partition INT NOT NULL,
  kafka_offset    BIGINT NOT NULL
);
COMMENT ON TABLE  estate.slack_messages IS 'SIMULATED Slack messages, landed like the SharePoint items: one row per message with the Kafka position of its event. No real Slack was read. Credentials in the demo are invented placeholders.';
COMMENT ON COLUMN estate.slack_messages.members IS 'How many people can read the channel. A public channel is readable by everyone in the workspace.';

INSERT INTO estate.systems (system_id, name, technology, business_criticality, owned_by, support_group, environment, data_class, hosting, install_status, end_of_support, last_discovered, loss_event) VALUES
 (1, 'Payment gateway (production)', 'Payment gateway software', 1, 'Payments Engineering', 'Payments Engineering', 'production', 'restricted', 'on-premise cluster', 'installed', DATE '2027-06-30', DATE '2026-11-20', 'Failed payments or double postings: direct money lost and a card-scheme reporting duty.'),
 (2, 'Payment gateway (disaster recovery)', 'Payment gateway software', 1, 'Payments Engineering', 'Payments Engineering', 'dr', 'restricted', 'secondary data centre', 'installed', DATE '2027-06-30', DATE '2026-11-20', 'A failed failover leaves card payments down: denial of service to many customers.'),
 (3, 'Domain controllers', 'Windows Server', 1, 'Platform Operations', 'Platform Operations', 'production', 'confidential', 'on-premise', 'installed', DATE '2026-12-31', DATE '2026-11-20', 'Loss of sign-in for staff and operators: large-scale denial of service inside the firm.'),
 (4, 'Branch file servers', 'Windows Server', 2, 'Platform Operations', 'Platform Operations', 'production', 'confidential', 'on-premise', 'installed', NULL, DATE '2026-11-20', 'Branch files unavailable: branch work stops; no customer data leaves.'),
 (5, 'Back-office application servers', 'Windows Server', 2, 'Platform Operations', 'Platform Operations', 'production', 'internal', 'on-premise', 'installed', NULL, DATE '2026-11-20', 'Back-office processing delayed; limited customer impact.'),
 (6, 'Branch voice and ATM link', 'Legacy TDM telecom', 2, 'Network Operations', 'Network Operations', 'production', 'internal', 'carrier-leased lines', 'installed', DATE '2026-12-31', DATE '2026-11-20', 'Branch voice and ATM links down: denial of service to branch customers.'),
 (7, 'Core banking database', 'Postgres', 1, 'Data Platform', 'Data Platform', 'production', 'restricted', 'on-premise cluster', 'installed', NULL, DATE '2026-11-20', 'Ledger corrupted or exposed: money lost and a breach with legal risk.'),
 (8, 'Customer web portal', 'Web application', 1, 'Digital Channels', 'Digital Channels', 'production', 'confidential', 'cloud', 'installed', NULL, DATE '2026-11-20', 'Portal down or defaced: denial of service to many customers.'),
 (9, 'Analytics warehouse', 'Postgres', 3, 'Data Platform', 'Data Platform', 'production', 'confidential', 'cloud', 'installed', NULL, DATE '2026-11-20', 'Analytics unavailable; a breach would expose confidential data.'),
 (10, 'HR system', 'SaaS HR suite', 3, 'HR Technology', 'HR Technology', 'production', 'restricted', 'vendor-hosted', 'installed', NULL, DATE '2026-11-20', 'Employee records exposed: a breach with legal risk.'),
 (11, 'Backup vault', 'Backup appliance', 1, 'Platform Operations', 'Platform Operations', 'production', 'restricted', 'secondary data centre', 'installed', NULL, DATE '2026-11-20', 'Backups lost or encrypted: recovery impossible after another loss event.');

-- The November 2026 cluster: a latent defect in payment-gateway software on on-premise hardware (the Chase slowdown), a Windows defect (the Microsoft 365 outage), and a legacy
-- telecom instability (the FAA stop, as the FAA describes it). Those are the three technologies a similar incident would hit here.
INSERT INTO estate.scenario_technology VALUES
 ('nov-2026-cluster', 'Payment gateway software', 'A software bug in on-premise hardware slowed transactions at a large bank.'),
 ('nov-2026-cluster', 'Windows Server',           'A months-old Windows defect, exposed by an update, took a global service down.'),
 ('nov-2026-cluster', 'Legacy TDM telecom',       'Legacy telecom instability, as one official account of the ground stop puts it.');

INSERT INTO estate.access_paths VALUES
 (1, 'Payments Engineering',   'group',  22,   'admin'),
 (1, 'Payments Operations',    'group',  35,   'operate'),
 (1, 'Gateway vendor support', 'vendor', 4,    'admin'),
 (2, 'Payments Engineering',   'group',  22,   'admin'),
 (2, 'Payments Operations',    'group',  35,   'operate'),
 (3, 'Platform Operations',    'group',  28,   'admin'),
 (3, 'All IT staff',           'group',  410,  'read'),
 (4, 'Platform Operations',    'group',  28,   'admin'),
 (4, 'All branch staff',       'group',  2300, 'operate'),
 (5, 'Platform Operations',    'group',  28,   'admin'),
 (6, 'Network Operations',     'group',  14,   'admin'),
 (6, 'Carrier support',        'vendor', 6,    'admin');

INSERT INTO estate.buckets VALUES
 (1, 1, 'gateway-audit-logs',    'restricted',   FALSE, TRUE,  'Payments Engineering', 22),
 (2, 2, 'gateway-dr-snapshots',  'restricted',   FALSE, TRUE,  'Platform Operations',  28),
 (3, 6, 'tdm-config-backups',    'confidential', FALSE, FALSE, 'Carrier support',      6);

INSERT INTO estate.patches (patch_id, system_id, advisory, severity, released_on, due_on, applied_on, days_overdue) VALUES
 (1, 1, 'GW-SEC-2026-14',  'critical', '2026-10-20', '2026-11-03', '2026-11-02', 0),
 (2, 3, 'MS-2026-11-A',    'critical', '2026-10-28', '2026-11-04', NULL,         0),
 (3, 4, 'MS-2026-11-B',    'high',     '2026-10-28', '2026-11-11', NULL,         0),
 (4, 5, 'MS-2026-10-C',    'high',     '2026-10-14', '2026-10-28', '2026-11-10', 0),
 (5, 6, 'TDM-FW-2026-02',  'high',     '2026-09-16', '2026-09-30', NULL,         0);
UPDATE estate.patches p SET cve = v.cve, cvss_score = v.cvss, known_exploited = v.kev, epss = v.epss FROM (VALUES
 (1, 'CVE-2026-9001', 8.1, FALSE, 0.042), (2, 'CVE-2026-9002', 9.8, TRUE, 0.912), (3, 'CVE-2026-9003', 7.5, FALSE, 0.118),
 (4, 'CVE-2026-9004', 7.2, FALSE, 0.067), (5, 'CVE-2026-9005', 8.8, FALSE, 0.231)) AS v(id, cve, cvss, kev, epss) WHERE p.patch_id = v.id;
UPDATE estate.patches SET days_overdue = GREATEST(0, DATE '2026-11-20' - due_on) WHERE applied_on IS NULL;

INSERT INTO estate.changes (change_id, system_id, summary, change_type, deployed_on, days_ago, preprod_tested, peer_reviewed, change_window) VALUES
 (1, 1, 'Gateway release 7.4.2',                 'software release', '2026-11-09', 0, TRUE,  TRUE,  'off-hours'),
 (2, 3, 'Domain controller update rollup',       'patch',            '2026-11-12', 0, FALSE, TRUE,  'business hours'),
 (3, 5, 'Application server configuration change','configuration',  '2026-11-16', 0, FALSE, FALSE, 'business hours'),
 (4, 4, 'File server migration',                 'migration',        '2026-11-05', 0, TRUE,  TRUE,  'off-hours'),
 (5, 2, 'DR failover configuration',             'configuration',    '2026-10-30', 0, FALSE, TRUE,  'off-hours');
UPDATE estate.changes SET days_ago = DATE '2026-11-20' - deployed_on;

INSERT INTO estate.dependencies VALUES
 (1, 8, 'Card payments on the customer portal'),
 (1, 7, 'Settlement posting to the core ledger'),
 (2, 1, 'Failover target for the production gateway'),
 (3, 4, 'Staff sign-in to the branch file servers'),
 (3, 5, 'Staff sign-in to the back-office servers'),
 (3, 7, 'Operator sign-in to the core banking database'),
 (3, 8, 'Staff sign-in to the portal back end'),
 (6, 4, 'Wide-area link to the branch file servers');

INSERT INTO estate.recovery_tests VALUES
 (1, '2026-04-22', 'failover to disaster recovery',  'passed over target', 30,  41,  NULL),
 (2, '2026-04-22', 'failover to disaster recovery',  'passed over target', 30,  41,  NULL),
 (3, '2026-09-12', 'domain controller restore',       'passed',             120, 95,  NULL),
 (4, '2026-06-01', 'restore from the backup vault',   'passed',             240, 200, NULL),
 (5, '2026-08-20', 'restore from the backup vault',   'passed',             240, 180, NULL),
 (6, NULL,         'none',                            'never tested',       NULL, NULL, NULL);
UPDATE estate.recovery_tests SET days_since_test = DATE '2026-11-20' - tested_on WHERE tested_on IS NOT NULL;

-- Latest state of each SharePoint item and Slack message at start-up (offsets 1 to n). Later events are in replay/.
INSERT INTO estate.sharepoint_items VALUES
 (1, 'Payments Engineering', 'Runbooks', 'Gateway failover runbook',                   'runbook',    'team',       22,   1, '2026-11-02 09:14', 'sharepoint.items', 0, 101),
 (2, 'Payments Engineering', 'Runbooks', 'Gateway admin credentials (shared sheet)',   'credential', 'owners',     3,    1, '2026-10-28 16:40', 'sharepoint.items', 0, 102),
 (3, 'Platform Operations',  'Recovery', 'Domain controller rebuild steps',            'recovery',   'team',       28,   3, '2026-09-12 11:05', 'sharepoint.items', 0, 103),
 (4, 'Platform Operations',  'Recovery', 'Branch file server restore guide',           'recovery',   'department', 410,  4, '2026-06-01 15:22', 'sharepoint.items', 0, 104),
 (5, 'Network Operations',   'Carrier',  'Carrier escalation contacts and line IDs',   'runbook',    'external',   6,    6, '2026-08-03 10:00', 'sharepoint.items', 0, 105),
 (6, 'Payments Engineering', 'Design',   'Gateway architecture overview',              'other',      'team',       22,   1, '2026-07-19 13:30', 'sharepoint.items', 0, 106);

INSERT INTO estate.slack_messages VALUES
 (1, '#payments-oncall', 'private', 18,   'a.nguyen',  'runbook',  1,    'Failover steps are pinned: fail over to DR first, then check the queue depth.',                               '2026-11-09 22:10', 'slack.messages', 0, 201),
 (2, '#it-help',         'public',  640,  'svc-desk',  'recovery', 4,    'Reminder: branch shares are restored from the nightly vault job; ask Platform Operations to start it.',        '2026-11-05 08:45', 'slack.messages', 0, 202),
 (3, '#network-ops',     'private', 14,   'r.okafor',  'runbook',  6,    'The carrier escalation line is in the pinned document; ask for the senior engineer on the 24 hour desk.',      '2026-10-30 17:02', 'slack.messages', 0, 203),
 (4, '#eng-general',     'public',  1240, 'j.patel',   'chat',     NULL, 'Anyone free to review the retail PR before lunch?',                                                             '2026-11-19 11:48', 'slack.messages', 0, 204);

-- Step 8c: whether a system can be reached from the internet. Invented: the customer portal and the vendor-hosted HR suite are; everything else is internal or private-network only.
ALTER TABLE estate.systems ADD COLUMN internet_facing BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN estate.systems.internet_facing IS 'Whether the system can be reached from the internet. Invented values. A real estate would take it from the CMDB or an external attack-surface scan.';
UPDATE estate.systems SET internet_facing = TRUE WHERE system_id IN (8, 10);
