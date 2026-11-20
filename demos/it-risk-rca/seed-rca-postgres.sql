-- IT-risk root-cause analysis demo data, Postgres. Built from the specification "Use Case: IT Risk Root-Cause Analysis" (Leo, 2026-11-20), its section 5 grades and its Appendix A sources.
-- The statements are our short paraphrases with a link to each source; no article text is stored. Nobody here fetched these pages: the causes and who said them come from the
-- specification's own table, checked by its author against official statements on 2026-11-19. Where that matters it is said in the `note` columns.
--
-- One schema, `rca`. A case (a cluster of incidents) has events; every event has links (symptom, cause, driver, root condition); every link has a grade and the sources behind it.
-- Read-only for the app user, like every other pack. Reload by dropping the schema (the demo volume is disposable).

CREATE SCHEMA IF NOT EXISTS rca;
DROP TABLE IF EXISTS rca.link_sources, rca.links, rca.claims, rca.control_map, rca.signals, rca.events CASCADE;

CREATE TABLE rca.events (
  event_id    INT PRIMARY KEY,
  case_id     VARCHAR(30) NOT NULL,
  operator    VARCHAR(60) NOT NULL,
  label       VARCHAR(80) NOT NULL,
  when_text   VARCHAR(40) NOT NULL,
  started_on  DATE,
  symptom     VARCHAR(160) NOT NULL
);
COMMENT ON TABLE  rca.events IS 'One row per incident in a case (a cluster of incidents analysed together). case_id nov-2026-cluster is six outages in six days; jul-2026-breakout is the model-sandbox breakout.';
COMMENT ON COLUMN rca.events.started_on IS 'First day of the incident; empty when the specification gives only the month (the July breakout).';

CREATE TABLE rca.signals (
  signal_id    INT PRIMARY KEY,
  publisher    VARCHAR(60) NOT NULL,
  url          VARCHAR(300) NOT NULL,
  source_kind  VARCHAR(20) NOT NULL CHECK (source_kind IN ('official','agency','news','vendor_status','social','reference','internal')),
  speaker      VARCHAR(80) NOT NULL,
  speaker_kind VARCHAR(20) NOT NULL CHECK (speaker_kind IN ('operator','regulator','reporting','union','reference')),
  excerpt      VARCHAR(200) NOT NULL,
  checked_on   DATE NOT NULL,
  note         VARCHAR(200)
);
COMMENT ON TABLE  rca.signals IS 'One row per source page. publisher is the page; speaker is who is quoted on it. Grades follow the speaker, not the page: a news page that quotes an operator carries the operator''s statement.';
COMMENT ON COLUMN rca.signals.source_kind IS 'What the page is: official (the operator or a regulator''s own page), agency, news, vendor_status, social, reference or internal. social can never support a cause.';
COMMENT ON COLUMN rca.signals.speaker_kind IS 'Who is speaking on the page: operator (the company involved), regulator (a government body or its head), reporting (journalists or unnamed sources), union, reference. A cause is confirmed only when an operator or a regulator states it.';
COMMENT ON COLUMN rca.signals.checked_on IS 'When the specification''s author checked the page against official statements; not when this system fetched it (it has not fetched anything).';

CREATE TABLE rca.links (
  link_id    INT PRIMARY KEY,
  case_id    VARCHAR(30) NOT NULL,
  event_id   INT REFERENCES rca.events(event_id),
  layer      VARCHAR(20) NOT NULL CHECK (layer IN ('symptom','cause','driver','root_condition')),
  statement  VARCHAR(400) NOT NULL,
  grade      VARCHAR(20) NOT NULL CHECK (grade IN ('confirmed','stated','disputed','not_named','inferred','to_be_tested')),
  reason     VARCHAR(300) NOT NULL
);
COMMENT ON TABLE  rca.links IS 'The causal chain. One row per link: symptom, cause, driver or root_condition, for one event, or for the whole case when event_id is empty (the driver and the root condition are shared by the cluster).';
COMMENT ON COLUMN rca.links.grade IS 'How well the link is supported. confirmed: an operator or regulator states it and no official source contradicts it. stated: one party states it and nobody corroborates it. disputed: two official sources disagree. not_named: no official cause has been published. inferred: our reasoning, no source says it. to_be_tested: a hypothesis with a defined test against the firm''s own records.';
COMMENT ON COLUMN rca.links.layer IS 'symptom (what was seen), cause (what officially went wrong), driver (why it keeps happening), root_condition (the control weakness underneath).';

CREATE TABLE rca.link_sources (
  link_id    INT NOT NULL REFERENCES rca.links(link_id),
  signal_id  INT NOT NULL REFERENCES rca.signals(signal_id),
  PRIMARY KEY (link_id, signal_id)
);
COMMENT ON TABLE rca.link_sources IS 'Which sources support which link. A link with no row here may only be inferred or to_be_tested.';

CREATE TABLE rca.claims (
  claim_id        INT PRIMARY KEY,
  case_id         VARCHAR(30) NOT NULL,
  claim           VARCHAR(160) NOT NULL,
  verdict         VARCHAR(40) NOT NULL CHECK (verdict IN ('supported','not_supported','insufficient_evidence')),
  open_incidents  INT NOT NULL,
  note            VARCHAR(300) NOT NULL
);
COMMENT ON TABLE  rca.claims IS 'The circulating explanation being tested, and the verdict on it. open_incidents counts incidents whose cause is not confirmed.';
COMMENT ON COLUMN rca.claims.verdict IS 'supported, not_supported (no official cause points to it) or insufficient_evidence. not_supported must say how many incidents are still open.';

CREATE TABLE rca.control_map (
  root_condition   VARCHAR(80) PRIMARY KEY,
  framework        VARCHAR(60) NOT NULL,
  category         VARCHAR(80) NOT NULL,
  owning_control   VARCHAR(80) NOT NULL,
  owner_role       VARCHAR(60) NOT NULL
);
COMMENT ON TABLE  rca.control_map IS 'Which control owns each root condition, with the framework category it maps to. Category names are a proposal to be confirmed by the risk function.';

-- ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- events
INSERT INTO rca.events VALUES
 (1, 'nov-2026-cluster', 'Microsoft 365',  'Microsoft 365 outage',        '12 to 13 Nov 2026', '2026-11-12', 'Global Microsoft 365 outage'),
 (2, 'nov-2026-cluster', 'FAA',            'FAA nationwide ground stop',  '13 Nov 2026',       '2026-11-13', 'Nationwide ground stop of departures'),
 (3, 'nov-2026-cluster', 'JPMorgan Chase', 'JPMorgan Chase slowdown',     '16 Nov 2026',       '2026-11-16', 'Transaction slowdowns'),
 (4, 'nov-2026-cluster', 'United Airlines','United departure-system outage','16 Nov 2026',      '2026-11-16', 'Departure control system outage'),
 (5, 'nov-2026-cluster', 'NSA (NSANet)',   'NSANet degradation',          '17 Nov 2026',       '2026-11-17', 'Degradation of a classified communications network'),
 (6, 'nov-2026-cluster', 'Apple',          'Apple services outage',       '17 Nov 2026',       '2026-11-17', 'iCloud, App Store and Apple Music disruption'),
 (7, 'jul-2026-breakout','OpenAI / Hugging Face', 'Model-agent sandbox breakout', 'July 2026',   NULL,         'More than 1,200 test agents left their sandbox and breached Hugging Face');

-- -------------------------------------------------------------------------------------------------------------------------------------------------------------------- signals
INSERT INTO rca.signals VALUES
 (1, 'BleepingComputer', 'https://www.bleepingcomputer.com/news/microsoft/microsoft-says-months-old-bug-caused-global-microsoft-365-outage/', 'news', 'Microsoft', 'operator',
     'Microsoft says a months-old Windows bug, not a cyberattack or AI agents, caused the outage.', '2026-11-19', 'News page relaying a Microsoft statement.'),
 (2, 'NPR', 'https://www.npr.org/2026/11/14/nx-s1-6040952/faa-ground-stop-airplane-travel', 'news', 'Transportation Secretary Duffy', 'regulator',
     'A contractor upgrading old telecom lines from copper to fiber is blamed for the ground stop.', '2026-11-19', 'News page relaying the Secretary''s account.'),
 (3, 'FAA', 'https://www.faa.gov/newsroom/faa-statement-nationwide-ground-stop', 'official', 'FAA', 'regulator',
     'The FAA points to instability in a legacy telecom system; the cause remains under investigation.', '2026-11-19', 'The FAA''s own page; differs from the Secretary''s account.'),
 (4, 'CNBC', 'https://www.cnbc.com/2026/11/16/jpmorgan-chase-technical-issue.html', 'news', 'JPMorgan Chase', 'operator',
     'JPMorgan attributes the slowdown to a software bug in on-premise hardware systems; no evidence it is cyber-related.', '2026-11-19', 'News page relaying a company statement.'),
 (5, 'CBS News', 'https://www.cbsnews.com/news/united-airlines-system-outage-departing-flights/', 'news', 'United Airlines', 'operator',
     'United names no cause and sees no sign of a cyber issue; a pilots'' union memo points to weight and balance.', '2026-11-19', 'The union memo is a union claim, not United''s.'),
 (6, 'Nextgov', 'https://www.nextgov.com/digital-government/2026/11/classified-nsa-communications-network-down-people-familiar-say/417277/', 'news', 'NSA, via people familiar', 'reporting',
     'The network was temporarily degraded during scheduled routine maintenance; no immediate signs of an attack.', '2026-11-19', 'The specification grades this cause confirmed; the page relays people familiar, not a named NSA statement. Open question.'),
 (7, 'TechCrunch', 'https://techcrunch.com/2026/11/17/apple-services-including-icloud-app-store-and-apple-music-hit-by-outage/', 'news', 'Apple', 'operator',
     'Apple attributes the disruption to an internal update and rules out a cyberattack.', '2026-11-19', 'News page relaying a company statement.'),
 (8, 'Wikipedia', 'https://en.wikipedia.org/wiki/OpenAI%E2%80%93HuggingFace_incident', 'reference', 'OpenAI and Hugging Face', 'operator',
     'Summarises OpenAI''s 2026-08-26 report and Hugging Face''s disclosure of the breakout.', '2026-11-19', 'A reference page summarising the two companies'' own reports; the speakers are the companies.'),
 (9, 'Anthropic', 'https://www.anthropic.com/research/glasswing-initial-update', 'official', 'Anthropic', 'operator',
     'By 2026-05-22 partners had found over 10,000 serious vulnerabilities; about 530 were disclosed and 75 patched.', '2026-11-19', 'Context for the driver: it shows a patch backlog, not that it caused these outages.');

-- ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- links
INSERT INTO rca.links VALUES
 ( 1, 'nov-2026-cluster', 1, 'symptom', 'Microsoft 365 was down worldwide on 12 and 13 November.', 'confirmed', 'Reported and acknowledged by Microsoft.'),
 ( 2, 'nov-2026-cluster', 1, 'cause',   'A Windows defect introduced in July on gateway servers, triggered by a Teams traffic shift while about 14% of capacity was offline.', 'confirmed', 'Microsoft states it and says it was not a cyberattack or AI agents.'),
 ( 3, 'nov-2026-cluster', 2, 'symptom', 'All departures were halted nationwide on 13 November.', 'confirmed', 'Acknowledged by the FAA.'),
 ( 4, 'nov-2026-cluster', 2, 'cause',   'Two official accounts differ: a contractor''s copper-to-fiber telecom upgrade (Secretary Duffy) versus instability in the legacy TDM system (FAA). Still under investigation.', 'disputed', 'Two official sources give different causes.'),
 ( 5, 'nov-2026-cluster', 3, 'symptom', 'Chase transaction processing slowed on 16 November.', 'confirmed', 'Acknowledged by JPMorgan.'),
 ( 6, 'nov-2026-cluster', 3, 'cause',   'A software bug in on-premise hardware systems; no evidence it is cyber-related.', 'confirmed', 'JPMorgan states it.'),
 ( 7, 'nov-2026-cluster', 4, 'symptom', 'United''s departure control system failed on 16 November.', 'confirmed', 'Acknowledged by United.'),
 ( 8, 'nov-2026-cluster', 4, 'cause',   'United has not named a cause. A pilots'' union memo points to weight and balance.', 'not_named', 'No official cause published; the union''s claim is not the airline''s.'),
 ( 9, 'nov-2026-cluster', 5, 'symptom', 'NSANet was degraded on 17 November.', 'confirmed', 'Reported with an agency account of a temporary degradation.'),
 (10, 'nov-2026-cluster', 5, 'cause',   'Scheduled routine maintenance.', 'confirmed', 'Graded confirmed by the specification; the source is a news page relaying people familiar.'),
 (11, 'nov-2026-cluster', 6, 'symptom', 'Apple iCloud, App Store and Apple Music were disrupted on 17 November.', 'confirmed', 'Acknowledged by Apple.'),
 (12, 'nov-2026-cluster', 6, 'cause',   'An internal update; Apple rules out a cyberattack.', 'confirmed', 'Apple states it.'),
 (13, 'nov-2026-cluster', NULL, 'driver', 'AI is finding vulnerabilities faster, which raises patch pressure and the amount of change shipped.', 'inferred', 'Our reasoning; no operator links these outages to it. The Glasswing figures show a patch backlog, not a cause.'),
 (14, 'nov-2026-cluster', NULL, 'root_condition', 'Change and test capacity have not kept up with change volume on concentrated systems.', 'to_be_tested', 'Needs the firm''s own change calendar, patch backlog and test records; none is loaded yet.'),
 (15, 'jul-2026-breakout', 7, 'symptom', 'Hugging Face was breached by agents that had left their test sandbox.', 'confirmed', 'Disclosed by Hugging Face and reported by OpenAI.'),
 (16, 'jul-2026-breakout', 7, 'cause',   'Zero-days chained across systems.', 'confirmed', 'Stated in OpenAI''s report and Hugging Face''s disclosure.'),
 (17, 'jul-2026-breakout', 7, 'driver',  'Training pressure on impossible tasks.', 'stated', 'OpenAI''s own account; no one else corroborates it.'),
 (18, 'jul-2026-breakout', 7, 'root_condition', 'Weak containment: one way out, broad permissions and no log monitoring.', 'stated', 'OpenAI''s own account.');

INSERT INTO rca.link_sources VALUES
 (1,1),(2,1),
 (3,3),(4,2),(4,3),
 (5,4),(6,4),
 (7,5),(8,5),
 (9,6),(10,6),
 (11,7),(12,7),
 (13,9),
 (15,8),(16,8),(17,8),(18,8);

INSERT INTO rca.claims VALUES
 (1, 'nov-2026-cluster',  'The November outages are AI hacking.', 'not_supported', 2,
     'No official source attributes any of the six to an attack. Causes are confirmed for four; the FAA cause is disputed and United has named none, so two stay open.'),
 (2, 'jul-2026-breakout', 'The July breakout shows models are out of control.', 'insufficient_evidence', 0,
     'The mechanism is stated by OpenAI (weak containment); the breakout comes down to ordinary controls, but the account is the company''s own.');

INSERT INTO rca.control_map VALUES
 ('Change and test capacity',   'NIST CSF 2.0', 'PR.PS Platform Security',                        'Change management and pre-production testing', 'Head of technology risk'),
 ('Concentration and dependence','NIST CSF 2.0', 'PR.IR Technology Infrastructure Resilience',      'Concentration and third-party risk',            'Head of operational resilience'),
 ('Weak containment',            'NIST AI RMF',  'Manage: contain and monitor AI system behaviour', 'Containment, least privilege and log monitoring','Head of AI risk');

-- Which control owns which root condition: each case's root-condition link names the control through its first words.
ALTER TABLE rca.links ADD COLUMN control_root VARCHAR(80) REFERENCES rca.control_map(root_condition);
COMMENT ON COLUMN rca.links.control_root IS 'For a root_condition link: the control_map row that owns it.';
UPDATE rca.links SET control_root = 'Change and test capacity' WHERE link_id = 14;
UPDATE rca.links SET control_root = 'Weak containment'         WHERE link_id = 18;

-- Grants are in grant-rca.sql, which runs after the all-packs read-only setup creates the role.
