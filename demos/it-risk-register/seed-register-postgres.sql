-- IT-risk register vocabulary, Postgres (docs/agency-risk-register-plan.md, step 8a). Schema `register`: the category tree (L1 to L3), the four-value rating scale and the terms the screens use.
-- Everything here is our reading of the meeting notes with Leo and of public frameworks. The framework columns (NIST CSF 2.0, ITIL 4, CIS Controls v8) are OUR mapping from general knowledge,
-- NOT checked clause by clause: a risk partner should correct them. `status` says where each category came from: notes (the meeting tree), example (a public L1 to L3 example Leo pointed to),
-- proposal (ours, for Leo to accept or move). Later steps add assessments (8b) to this schema. Read-only for the app user. Reload by dropping the schema.

CREATE SCHEMA IF NOT EXISTS register;
DROP TABLE IF EXISTS register.assessments, register.item_categories, register.claim_type_category, register.taxonomy, register.rating_scale, register.definitions CASCADE;

CREATE TABLE register.taxonomy (
  node_id     VARCHAR(20) PRIMARY KEY,
  parent_id   VARCHAR(20) REFERENCES register.taxonomy(node_id),
  depth       INT NOT NULL CHECK (depth IN (1,2,3)),
  name        VARCHAR(90) NOT NULL,
  definition  VARCHAR(240) NOT NULL,
  status      VARCHAR(10) NOT NULL CHECK (status IN ('notes','example','proposal')),
  nist_csf    VARCHAR(80),
  itil_practice VARCHAR(60),
  cis_control VARCHAR(120),
  note        VARCHAR(240)
);
COMMENT ON TABLE  register.taxonomy IS 'The category tree for IT and operational risk: depth 1 (L1), 2 (L2), 3 (L3). A category answers "what kind of risk is this?". It is not a rating and not the organisational owner chain.';
COMMENT ON COLUMN register.taxonomy.status IS 'notes = from the meeting notes with Leo; example = from a public L1 to L3 example; proposal = ours, to be accepted or moved.';
COMMENT ON COLUMN register.taxonomy.nist_csf IS 'Nearest NIST CSF 2.0 category. Our mapping, unchecked.';
COMMENT ON COLUMN register.taxonomy.itil_practice IS 'Nearest ITIL 4 practice. Our mapping, unchecked.';
COMMENT ON COLUMN register.taxonomy.cis_control IS 'Nearest CIS Controls v8 control. Our mapping, unchecked.';

INSERT INTO register.taxonomy VALUES
 ('CR',     NULL,  1, 'Compliance and Risk', 'The top of the notes'' register tree. A firm may split compliance from technology and cyber risk; Leo to say which.', 'notes', 'GV.RM Risk Management Strategy', 'Risk management', NULL, 'The public example treats Compliance as a peer L1; the meeting notes place Technology Management Failure under it.'),
 ('CR.TMF', 'CR',  2, 'Technology Management Failure', 'The firm did not manage its technology well enough: it is old, undersized, unlisted, unprotected or badly operated.', 'notes', 'ID, PR, RS', 'Service management', NULL, NULL),
 ('CR.TMF.IRM', 'CR.TMF', 3, 'Incident Response Management Deficiency', 'Detection, escalation, communication or recovery of an incident was missing, slow or untested.', 'notes', 'RS.MA, RS.AN, RS.CO, RS.MI, DE.AE', 'Incident management', 'CIS 17 Incident Response Management', NULL),
 ('CR.TMF.INV', 'CR.TMF', 3, 'Technology Asset Inventory', 'The firm does not know what it runs, who owns it or what state it is in.', 'notes', 'ID.AM Asset Management', 'IT asset management', 'CIS 1 Inventory and Control of Enterprise Assets', NULL),
 ('CR.TMF.LEG', 'CR.TMF', 3, 'Legacy Tech', 'Technology past or near the end of vendor support, or too old to patch or recover reliably.', 'notes', 'ID.AM, PR.PS Platform Security', 'IT asset management', 'CIS 2 Inventory and Control of Software Assets', NULL),
 ('CR.TMF.CAP', 'CR.TMF', 3, 'Technology Capacity Management', 'A system or the people who run it cannot absorb the load, including the load of changes and tests.', 'notes', 'PR.IR Technology Infrastructure Resilience', 'Capacity and performance management', NULL, 'No direct CIS Control. The November 2026 root condition (change and test capacity) belongs here or under CR.TMF.CHG; Leo to say.'),
 ('CR.TMF.PIA', 'CR.TMF', 3, 'Inadequate Protection, Identity and Access', 'Data or systems can be reached by people or software that should not reach them.', 'notes', 'PR.AA, PR.DS, PR.PS', 'Information security management', 'CIS 5 Account Management, CIS 6 Access Control Management', 'Overlaps CR.AVM.PRIV; Leo to say which one wins.'),
 ('CR.TMF.VPM', 'CR.TMF', 3, 'Vulnerability and patch management', 'Known weaknesses stay unpatched, or are patched in a hurry without safe testing.', 'proposal', 'ID.RA Risk Assessment, PR.PS', 'Information security management', 'CIS 7 Continuous Vulnerability Management', 'Proposed for AI-accelerated threats: vulnerabilities are found faster than they are fixed.'),
 ('CR.TMF.CHG', 'CR.TMF', 3, 'Change management and pre-production testing', 'A change or release reached production without approval or without being tested first (the rushed-patch risk).', 'example', 'PR.PS Platform Security', 'Change enablement', 'CIS 4 Secure Configuration of Enterprise Assets and Software', 'Appears in the public example as "unapproved change or release" and in the proposal as the rushed-patch risk.'),
 ('CR.TMF.TPC', 'CR.TMF', 3, 'Third-party and concentration risk', 'A supplier or one shared provider is a single point of failure for many services.', 'proposal', 'GV.SC Supply Chain Risk Management', 'Supplier management', 'CIS 15 Service Provider Management', 'Proposed for AI-accelerated threats.'),
 ('CR.TMF.RRT', 'CR.TMF', 3, 'Resilience and recovery testing', 'Recovery has not been tested recently, or a test missed its target.', 'proposal', 'RC.RP Incident Recovery Plan Execution', 'Service continuity management', 'CIS 11 Data Recovery', 'Proposed. The Exposure screen already asks when each system was last tested for recovery.'),
 ('CR.TMF.DEC', 'CR.TMF', 3, 'Data exposure in collaboration tools', 'Credentials, runbooks or restricted data sit in SharePoint, Slack or similar tools where too many people can see them.', 'proposal', 'PR.DS Data Security', 'Information security management', 'CIS 3 Data Protection', 'Proposed. The Exposure screen already asks where credentials and runbooks sit.'),
 ('CR.TMF.ARC', 'CR.TMF', 3, 'Architecture or integration defect', 'A design or interface flaw that lets one fault spread, or that surprises the teams on either side.', 'example', 'PR.PS Platform Security', 'Infrastructure and platform management', 'CIS 16 Application Software Security', NULL),
 ('CR.SID', 'CR',  2, 'System and Infrastructure Disruption', 'A service stopped or degraded because something in its technology failed.', 'example', 'PR.IR, RS', 'Incident management', NULL, 'The Basel event type "business disruption and system failures" is the nearest operational-risk class.'),
 ('CR.SID.HW',  'CR.SID', 3, 'Hardware failure', 'A physical component failed.', 'example', 'PR.IR', 'Infrastructure and platform management', NULL, NULL),
 ('CR.SID.SW',  'CR.SID', 3, 'Software defect or crash', 'A bug in software the firm or a vendor runs (the Microsoft 365 and JPMorgan Chase outages of November 2026 are of this kind, per their operators).', 'example', 'PR.PS', 'Software development and management', 'CIS 16', NULL),
 ('CR.SID.NET', 'CR.SID', 3, 'Network or telecom outage', 'A network, carrier or telecom service failed (the FAA case, where two official accounts of the cause differ).', 'example', 'PR.IR', 'Infrastructure and platform management', 'CIS 12 Network Infrastructure Management', NULL),
 ('CR.SID.CLD', 'CR.SID', 3, 'Cloud or hosting disruption', 'A hosting provider or cloud region failed.', 'example', 'PR.IR, GV.SC', 'Supplier management', 'CIS 15', NULL),
 ('CR.DBF', 'CR',  2, 'Data and Backup Failure', 'Data was lost, damaged or could not be restored.', 'example', 'PR.DS, RC.RP', 'Service continuity management', 'CIS 3, CIS 11', NULL),
 ('CR.DBF.COR', 'CR.DBF', 3, 'Data corruption or loss', 'Data was damaged or lost.', 'example', 'PR.DS', 'Service continuity management', 'CIS 3 Data Protection', NULL),
 ('CR.DBF.RST', 'CR.DBF', 3, 'Backup or restore failure', 'A backup was missing or a restore did not work.', 'example', 'PR.DS, RC.RP', 'Service continuity management', 'CIS 11 Data Recovery', NULL),
 ('CR.DBF.RET', 'CR.DBF', 3, 'Data retention or deletion error', 'Data was kept too long or deleted too early.', 'example', 'PR.DS', 'Information security management', 'CIS 3', NULL),
 ('CR.AVM', 'CR',  2, 'Access and Vulnerability Management Failure', 'Access rights or known weaknesses were not kept under control.', 'example', 'PR.AA, ID.RA', 'Information security management', 'CIS 5, CIS 6, CIS 7', NULL),
 ('CR.AVM.PRIV', 'CR.AVM', 3, 'Excessive or stale privileges', 'People or accounts hold more access than their job needs, or keep it after they should not.', 'example', 'PR.AA', 'Information security management', 'CIS 5, CIS 6', 'Overlaps CR.TMF.PIA.'),
 ('CR.AVM.MFA', 'CR.AVM', 3, 'Missing multi-factor authentication', 'A sign-in path that does not need a second factor.', 'example', 'PR.AA', 'Information security management', 'CIS 6', NULL),
 ('CR.AVM.PATCH', 'CR.AVM', 3, 'Unpatched vulnerability', 'A known flaw with an available fix that has not been applied.', 'example', 'ID.RA, PR.PS', 'Information security management', 'CIS 7', 'Overlaps CR.TMF.VPM.'),
 ('CR.SIB', 'CR',  2, 'Security Incident or Breach', 'An attacker or malicious software acted on the firm''s systems or data.', 'example', 'DE.AE, RS', 'Incident management', 'CIS 13, CIS 17', NULL),
 ('CR.SIB.MAL', 'CR.SIB', 3, 'Malware or ransomware', 'Malicious software ran in the estate.', 'example', 'DE.AE', 'Incident management', 'CIS 10 Malware Defenses', NULL),
 ('CR.SIB.EXF', 'CR.SIB', 3, 'Unauthorised data exfiltration', 'Data left the firm without permission; also a loss event if it creates legal risk.', 'example', 'DE.AE, RS.CO', 'Incident management', 'CIS 3', NULL),
 ('CR.SIB.MCE', 'CR.SIB', 3, 'Misconfigured exposure', 'A system or store was reachable from outside when it should not have been.', 'example', 'PR.PS', 'Information security management', 'CIS 4', NULL),
 ('CR.ITC', 'CR',  2, 'IT Control and Regulatory Non-Compliance', 'A required control, report or record was missing.', 'example', 'GV.PO Policy', 'Risk management', NULL, NULL),
 ('CR.ITC.RPT', 'CR.ITC', 3, 'Failed mandatory reporting', 'A regulator or customer was not told in time (the notification clocks in the plan, step 8e).', 'example', 'RS.CO', 'Incident management', 'CIS 17', NULL),
 ('CR.ITC.EVD', 'CR.ITC', 3, 'Missing or outdated policy or audit evidence', 'A policy or the evidence for a control is absent or stale.', 'example', 'GV.PO', 'Risk management', NULL, NULL),
 ('CR.ITC.PRV', 'CR.ITC', 3, 'Non-adherence to privacy or security rules', 'A rule was not followed.', 'example', 'GV.PO', 'Risk management', NULL, NULL);

CREATE TABLE register.rating_scale (
  rating     VARCHAR(10) PRIMARY KEY,
  rank       INT NOT NULL UNIQUE CHECK (rank BETWEEN 0 AND 3),
  meaning    VARCHAR(200) NOT NULL
);
COMMENT ON TABLE register.rating_scale IS 'The one rating scale on every screen: Critical, High, Medium, Low. It answers "how bad is this for us?". It is not an incident priority and not a CVSS severity.';
INSERT INTO register.rating_scale VALUES
 ('Low', 0, 'Little concern. Record it; no action needed now.'),
 ('Medium', 1, 'Worth watching or fixing in the normal cycle.'),
 ('High', 2, 'Needs action soon and a named owner.'),
 ('Critical', 3, 'Needs action now; a senior person should know today.');

CREATE TABLE register.definitions (
  term        VARCHAR(40) PRIMARY KEY,
  meaning     VARCHAR(300) NOT NULL,
  source      VARCHAR(120) NOT NULL,
  status      VARCHAR(20) NOT NULL CHECK (status IN ('given','ours','not confirmed','deferred'))
);
COMMENT ON TABLE register.definitions IS 'The words the screens use and what each means. status: given = Leo or Kumar said it; ours = our wording; not confirmed = reported from the notes but not found in a standard; deferred = to be defined later.';
INSERT INTO register.definitions VALUES
 ('Loss event', 'Something that loses a bank money; or a denial of service to a large set of customers; or an attack that breaches data and creates legal risk.', 'Leo, answer in the report, 2026-11-21', 'given'),
 ('Rating', 'The four-value scale in rating_scale. The only thing the screens call a level.', 'Leo, 2026-11-21', 'given'),
 ('Category', 'A position in the taxonomy (L1, L2 or L3): what kind of risk this is.', 'Meeting notes', 'ours'),
 ('Event under review', 'A story or signal the feed raised that a person has not yet traced. Called a candidate in earlier builds.', 'ITIL 4 monitoring and event management (our reading)', 'ours'),
 ('Problem record', 'The root-cause write-up for a cluster of incidents: symptom, cause, driver, root condition, each graded by its evidence. Called a brief in earlier builds.', 'ITIL 4 problem management (our reading)', 'ours'),
 ('Exposure', 'A weakness that is present and reachable in our estate, rated on one scale.', 'Our term, Exposure screen', 'ours'),
 ('Inherent risk', 'Risk before controls. Shown from outside evidence and the estate.', 'Three lines practice', 'given'),
 ('Residual risk', 'Risk after controls. Never computed here: we show inherent risk plus the control evidence and the second line judges.', 'Leo, 2026-11-21', 'given'),
 ('Control evidence', 'The facts a person weighs to judge how well a control works: a test result, a patch date, a recovery test.', 'Our wording', 'ours'),
 ('TRP', 'Technology Risk Prioritization: a ranked list from likelihood, impact, asset criticality, dependencies and remediation effort, where escalation triggers override the score. A method, not a standard.', 'Public article Leo pointed to, read 2026-11-21', 'given'),
 ('BRP', 'Business Risk Prioritization: the business-impact view of the same list. Stays empty until a firm supplies its business services.', 'Meeting notes; not found in a standard', 'not confirmed'),
 ('RAS', 'Appears in the notes as "Risk Assessment Structure".', 'Meeting notes', 'not confirmed'),
 ('Material', 'An incident that would reach the press as bad news, decided by named people. The test is not yet defined.', 'Leo, 2026-11-21 ("later")', 'deferred');


-- ------------------------------------------------------------------------------------------------------------------------------------------------ step 8b: categories and the register
-- Which category each seeded incident, case and watched story falls under. A category follows the CAUSE the operator stated, so where no cause is named the category stops at depth 2.
CREATE TABLE register.item_categories (
  item_type  VARCHAR(12) NOT NULL CHECK (item_type IN ('event','candidate')),
  item_ref   VARCHAR(40) NOT NULL,
  node_id    VARCHAR(20) NOT NULL REFERENCES register.taxonomy(node_id),
  basis      VARCHAR(200) NOT NULL,
  PRIMARY KEY (item_type, item_ref)
);
COMMENT ON TABLE register.item_categories IS 'The category of a seeded incident (item_ref = rca.events.event_id) or watched story (rca.candidates.candidate_id). Ours, from the cause each operator stated; a person should confirm it.';
INSERT INTO register.item_categories VALUES
 ('event','1','CR.SID.SW',  'Microsoft states a Windows defect on gateway servers.'),
 ('event','2','CR.SID.NET', 'Network or telecom, though two official accounts of the cause differ.'),
 ('event','3','CR.SID.SW',  'JPMorgan states a software bug in on-premise hardware systems.'),
 ('event','4','CR.SID',     'No cause named, so the category stops at the family.'),
 ('event','5','CR.SID',     'Routine maintenance reported by people familiar; no finer category is supported.'),
 ('event','6','CR.SID',     'Apple states an internal update; whether it was a failed change is not stated.'),
 ('event','7','CR.SIB',     'Agents chained zero-days to breach a third party; no finer category is supported.'),
 ('candidate','1','CR.SID', 'The six outages; the AI-attack claim is separate and untested.'),
 ('candidate','2','CR.SIB', 'An agent escaped its sandbox and breached another firm.');

CREATE TABLE register.claim_type_category (
  claim_type VARCHAR(30) PRIMARY KEY,
  node_id    VARCHAR(20) NOT NULL REFERENCES register.taxonomy(node_id),
  note       VARCHAR(200) NOT NULL
);
COMMENT ON TABLE register.claim_type_category IS 'A PROVISIONAL category for a watched story the feed found and nobody has traced yet: what the story CLAIMS, not what is established. It is replaced by item_categories once a person traces it.';
INSERT INTO register.claim_type_category VALUES
 ('ai-attack-claimed',   'CR.SIB', 'As claimed: someone says an attack caused it. Untested.'),
 ('ai-attack-confirmed', 'CR.SIB', 'As reported: an official source says an attack caused it.'),
 ('ai-adjacent',         'CR.SID', 'As reported: an outage or weakness that mentions AI, with no attack claimed.');

-- The register. Every change is a new row; a rating is never edited. The current rating of an item is its newest row.
CREATE TABLE register.assessments (
  assessment_id   BIGSERIAL PRIMARY KEY,
  item_type       VARCHAR(12) NOT NULL CHECK (item_type IN ('case','event','system','vulnerability')),
  item_ref        VARCHAR(60) NOT NULL,
  node_id         VARCHAR(20) NOT NULL REFERENCES register.taxonomy(node_id),
  rating          VARCHAR(10) NOT NULL REFERENCES register.rating_scale(rating),
  likelihood_band VARCHAR(10) REFERENCES register.rating_scale(rating),
  impact_band     VARCHAR(10) REFERENCES register.rating_scale(rating),
  likelihood_inputs VARCHAR(300),
  impact_inputs   VARCHAR(300),
  inherent        BOOLEAN NOT NULL DEFAULT TRUE CHECK (inherent),
  control_evidence VARCHAR(400),
  set_by          VARCHAR(120) NOT NULL,
  role            VARCHAR(10) NOT NULL CHECK (role IN ('second')),
  assessed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id          VARCHAR(80),
  evidence_digest VARCHAR(80),
  source          VARCHAR(12) NOT NULL DEFAULT 'workflow' CHECK (source IN ('workflow','seed-example')),
  CHECK (source = 'seed-example' OR (run_id IS NOT NULL AND evidence_digest IS NOT NULL))
);
COMMENT ON TABLE  register.assessments IS 'The risk register: one row per approved rating, appended, never edited or deleted (a trigger refuses both). The current view of an item is its newest row. Rows are written only by the worker after the second line approved the run in the Server''s workflow API; set_by and role come from that approval, run_id and evidence_digest point at the run and the exact evidence approved.';
COMMENT ON COLUMN register.assessments.inherent IS 'Always true. The register holds inherent risk (before controls) next to the control evidence; residual risk is judged by the second line and is never computed or stored here.';
COMMENT ON COLUMN register.assessments.role IS 'Who set the rating: the second line, by approving. The first line proposes through the workflow and the third line only reads.';
COMMENT ON COLUMN register.assessments.source IS 'workflow = written by the worker after an approval (needs run_id and evidence_digest). seed-example = invented demo row, no run behind it.';

CREATE UNIQUE INDEX assessments_one_per_run ON register.assessments (run_id) WHERE run_id IS NOT NULL;
COMMENT ON INDEX register.assessments_one_per_run IS 'A workflow run writes at most one row, so a retried write does not duplicate it.';

CREATE OR REPLACE FUNCTION register.refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'register.assessments is append-only: add a new row instead of changing or deleting one'; END $$;
CREATE TRIGGER assessments_append_only BEFORE UPDATE OR DELETE ON register.assessments FOR EACH ROW EXECUTE FUNCTION register.refuse_change();
CREATE TRIGGER assessments_no_truncate BEFORE TRUNCATE ON register.assessments FOR EACH STATEMENT EXECUTE FUNCTION register.refuse_change();

-- Invented example rows so the register is not empty: the November cluster rated High, then raised to Critical once the Exposure screen read Critical; one system. People are invented.
INSERT INTO register.assessments (item_type, item_ref, node_id, rating, likelihood_band, impact_band, likelihood_inputs, impact_inputs, control_evidence, set_by, role, assessed_at, source) VALUES
 ('case','nov-2026-cluster','CR.TMF.CHG','High','Medium','High','Four of six causes confirmed as defects or routine change; the driver is inferred.','Six large services affected in six days.','Change and test capacity not yet tested against the firm''s own change calendar.','raj.second','second','2026-11-20 10:00+00','seed-example'),
 ('case','nov-2026-cluster','CR.TMF.CHG','Critical','High','Critical','The Exposure rating read Critical (patch overdue on tier-1 domain controllers, 212 days since a gateway recovery test).','Tier-1 payment gateway and domain controllers.','Recovery test 212 days old on the gateway; one change untested.','raj.second','second','2026-11-21 09:30+00','seed-example'),
 ('system','Domain controllers','CR.AVM.PATCH','High','High','Medium','Known-exploited flaw patched 16 days late.','Tier 1, production, many dependants.','Patch overdue by 16 days; one untested change.','mei.second','second','2026-11-21 11:00+00','seed-example');
