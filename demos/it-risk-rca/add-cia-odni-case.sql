
-- A third case, added 2026-11-25: the CIA and ODNI breach of an unclassified open-source intelligence system, reported 24 to 25 November 2026. NOT part of the November outage cluster (it is a breach, not an outage).
-- What is known comes from news coverage relaying an ODNI representative and unnamed officials; the ODNI page itself was NOT read (two news pages and a search summary were), and the Washington Post and Forbes pages
-- returned 403 to our fetch. The only AI claim is a vendor blog's speculation, so the driver link is inferred and the claim has insufficient evidence. checked_on is the day we looked, not an official check.
INSERT INTO rca.events VALUES
 (8, 'cia-odni-nov-2026', 'CIA / ODNI', 'CIA and ODNI open-source system breach', 'Reported 24 Nov 2026', NULL, 'Breach of an unclassified open-source intelligence analysis system');
INSERT INTO rca.signals VALUES
 (10, 'France 24', 'https://www.france24.com/en/americas/20261125-cyberattack-exposes-unclassified-information-from-cia-system-us-media-reports', 'news', 'ODNI representative', 'operator',
     'An ODNI representative says there were no disruptions to critical capabilities or classified systems.', '2026-11-25', 'News page relaying an ODNI statement (read as search summary). The CIA declined to comment. No cause or attacker named.'),
 (11, 'MindStudio', 'https://www.mindstudio.ai/blog/cia-hack-ai-agents-data-breach', 'reference', 'MindStudio blog (a vendor)', 'reference',
     'Says there is no official confirmation AI tools carried out the attack and calls the AI link speculation.', '2026-11-25', 'A vendor marketing blog, read in full. Anonymous sources only; context, not evidence.');
INSERT INTO rca.links VALUES
 (19, 'cia-odni-nov-2026', 8, 'symptom', 'An unclassified open-source intelligence system used by the CIA and ODNI was breached; other agencies'' data is believed exposed.', 'confirmed', 'Acknowledged by an ODNI representative; scope details come from unnamed officials.'),
 (20, 'cia-odni-nov-2026', 8, 'cause',   'No cause or attacker has been named. ODNI says classified systems were not affected; the CIA declined to comment.', 'not_named', 'The official source names no cause.'),
 (21, 'cia-odni-nov-2026', NULL, 'driver', 'AI-assisted attackers were involved.', 'inferred', 'Only a vendor blog suggests it, as speculation; no operator or regulator links this breach to AI.');
INSERT INTO rca.link_sources (link_id, signal_id, relation, asserts) VALUES
 (19, 10, 'states',  'breach-disclosed'),
 (20, 10, 'silent',  NULL),
 (21, 11, 'context', NULL);
INSERT INTO rca.claims VALUES
 (3, 'cia-odni-nov-2026', 'The CIA and ODNI breach was an AI-driven attack.', 'insufficient_evidence', 1,
     'The breach is acknowledged but no cause or attacker is named, and no official source mentions AI. The AI idea comes from a vendor blog calling it speculation.');
INSERT INTO rca.candidates VALUES
 (3, 'cia-odni-nov-2026', 3, 'CIA and ODNI breached, said to involve AI', 'ai-attack-claimed', 'traced', '2026-11-24',
     'An unclassified open-source intelligence system was breached, reported 24 November 2026. ODNI says classified systems were unaffected; no source with standing names a cause or says AI was involved.');
INSERT INTO rca.candidate_items VALUES (3, 10), (3, 11);
