#!/bin/bash
# Approves the five demo questions as trusted questions (needs the admin password and a running instance on :8110).
set -euo pipefail
JAR=/tmp/si-admin.txt; rm -f $JAR
curl -s -c $JAR -o /dev/null -d "username=admin&password=${ADMIN_PASSWORD:-Admin-SI-1}" http://localhost:8110/admin/login
python3 - <<'PY'
import json, subprocess
Q = [
 ("What do we hold on the American Civil War across all museums, and how much of it has an image?",
  "SELECT unit_code AS museum, COUNT(DISTINCT record_id) AS records, COUNT(DISTINCT record_id) FILTER (WHERE image_url IS NOT NULL) AS with_image FROM si_topics WHERE concept = 'American Civil War (1861-1865)' GROUP BY unit_code ORDER BY records DESC"),
 ("Which museums have the most records with no image?",
  "SELECT unit_code AS museum, COUNT(DISTINCT record_id) AS records, COUNT(DISTINCT record_id) FILTER (WHERE image_url IS NULL) AS without_image FROM si_topics GROUP BY unit_code ORDER BY without_image DESC"),
 ("Show me what the Smithsonian has about the Civil War",
  "SELECT DISTINCT title, unit_code AS museum, image_url, record_link FROM si_topics WHERE concept = 'American Civil War (1861-1865)' AND image_url IS NOT NULL ORDER BY title LIMIT 24"),
 ("Show me portraits from the National Portrait Gallery",
  "SELECT DISTINCT title, unit_code AS museum, image_url, record_link FROM si_topics WHERE unit_code = 'NPG' AND topic = 'Portraits' AND image_url IS NOT NULL ORDER BY title LIMIT 24"),
 ("How many records does each museum hold, with its full name and department?",
  "SELECT m.museum_name, m.department, COUNT(DISTINCT t.record_id) AS records FROM si.si_topics t JOIN museums.museums m ON t.unit_code = m.unit_code GROUP BY m.museum_name, m.department ORDER BY records DESC"),
]
def call(path, body):
    return subprocess.run(['curl','-s','-b','/tmp/si-admin.txt','-H','Content-Type: application/json','-d',json.dumps(body),'http://localhost:8110'+path],capture_output=True,text=True).stdout
for q, sql in Q:
    entry = json.loads(call('/api/question-bank', {"question": q, "referenceSql": sql, "category": "smithsonian"}))['entry']
    print(q[:60], json.loads(call('/api/question-bank/status', {"id": entry['id'], "status": "approved"})).get('success'))
PY
