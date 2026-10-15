#!/bin/bash
# After the vocabulary build (POST /api/ontology/vocabulary/build), adds each record's concept to si_topics from the
# downloaded concepts CSV (vocabulary-concepts.csv). Labels that were not auto-merged keep their own label as the concept.
set -euo pipefail
cd "$(dirname "$0")"
psql -h 127.0.0.1 -d si_poc -q <<SQL
CREATE TEMP TABLE cm(canonical_concept text, member_label text, source_units text, occurrence_count int, confidence float, status text);
\copy cm FROM 'vocabulary-concepts.csv' CSV HEADER
ALTER TABLE si_topics ADD COLUMN IF NOT EXISTS concept text;
UPDATE si_topics t SET concept = COALESCE((SELECT canonical_concept FROM cm WHERE member_label = t.topic AND status='AUTO_ACCEPTED' LIMIT 1), t.topic);
SQL
