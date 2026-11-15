#!/usr/bin/env python3
"""Builds the sounds pack from ../multimodal-poc/manifest: seed-sounds.sql (schema `sounds`, with database comments), demo-questions-sounds.json
(approved questions with reference SQL) and sounds-knowledge.json (ontology descriptions). Deterministic. python3 build_pack.py"""
import csv, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); MAN = os.path.join(HERE, "..", "multimodal-poc", "manifest")
rec = list(csv.DictReader(open(os.path.join(MAN, "recordings.csv")))); spec = list(csv.DictReader(open(os.path.join(MAN, "usnm_specimens.csv"))))
q = lambda v: "NULL" if v in ("", None) else "'" + str(v).replace("'", "''") + "'"
FISH_CALLS = ["grunt", "drum", "growl", "knock", "chorus", "cough", "snitch", "moan", "gurgle", "chirp", "call"]
def call_type(r):
    b = (r["behavior"] or "").strip()
    if r["group"] == "bird": return b or "unspecified"
    toks = re.split(r"[ _]", re.sub(r"\d+", "", b.lower()))   # fish: the sound named in the source file name
    return next((t for t in toks if t in FISH_CALLS), "unspecified")
COMMENTS = {
 "sounds.species": "One row per species that has at least one recording, with the number of Smithsonian NMNH (USNM) specimens held for it.",
 "sounds.recordings": "One row per audio recording (a bird song or call, a fish sound), with who recorded it, where and when, the licence, and links to the audio file and its spectrogram image.",
 "sounds.licenses": "One row per licence found on the recordings, with what it permits.",
}
COLS = {
 "species.species": "Scientific name (genus species).", "species.group_name": "bird or fish.",
 "species.common_name": "English name, when the source gives one.",
 "species.usnm_specimens": "Number of specimen records for this species held by the Smithsonian NMNH (institution code USNM), from GBIF. Only filled for the bird species.",
 "species.usnm_with_coordinates": "How many of those specimen records have latitude and longitude. A subset of usnm_specimens.",
 "recordings.recording_id": "Recording id: xc<number> for Xeno-canto birds, fs<number> for FishSounds fish.",
 "recordings.group_name": "bird or fish.", "recordings.species": "Scientific name; joins to species.species.",
 "recordings.call_type": "What the animal is doing: for birds song, call, alarm call, imitation, uncertain and similar; for fish grunt, drum, growl, knock, chorus, cough, snitch, moan, call, read from the file name. 'unspecified' when the source names no particular sound.",
 "recordings.country": "Where it was recorded. Empty for fish: the fish sources give no country.",
 "recordings.latitude": "Decimal degrees; empty for fish.", "recordings.longitude": "Decimal degrees; empty for fish.",
 "recordings.recorded_on": "Date of the recording. Only birds have a full date; fish have only recorded_year.",
 "recordings.recorded_year": "Year of the recording (birds: the year of recorded_on; fish: the publication year in the source file name).",
 "recordings.recordist": "Person who made the recording (birds) or the first author of the study (fish).",
 "recordings.license": "Licence text, joins to licenses.license.", "recordings.source": "Where the recording comes from.",
 "recordings.source_ref": "Link to the source record (GBIF occurrence for birds, the data repository for fish).",
 "recordings.audio_url": "Link to the audio file.", "recordings.image_url": "Link to the spectrogram image of the recording.",
 "licenses.license": "Licence name, for example CC BY-NC 4.0.",
 "licenses.allows_commercial_use": "true when the licence allows commercial use. All licences on these recordings are non-commercial, so it is false for every row.",
 "licenses.allows_derivatives": "false when the licence forbids derived works (ND), true otherwise.",
 "licenses.requires_share_alike": "true when derived works must carry the same licence (SA).",
}
lic = {}
for r in rec:
    l = r["license"]; lic[l] = dict(nc="NC" in l, nd="-ND" in l, sa="-SA" in l)
sql = ["CREATE SCHEMA sounds;", """CREATE TABLE sounds.species (species text PRIMARY KEY, group_name text NOT NULL, common_name text, usnm_specimens integer, usnm_with_coordinates integer);
CREATE TABLE sounds.licenses (license text PRIMARY KEY, allows_commercial_use boolean NOT NULL, allows_derivatives boolean NOT NULL, requires_share_alike boolean NOT NULL);
CREATE TABLE sounds.recordings (recording_id text PRIMARY KEY, group_name text NOT NULL, species text NOT NULL REFERENCES sounds.species(species), call_type text NOT NULL,
  country text, latitude double precision, longitude double precision, recorded_on date, recorded_year integer, recordist text,
  license text NOT NULL REFERENCES sounds.licenses(license), source text, source_ref text, audio_url text, image_url text);"""]
sp = {}
for r in rec: sp.setdefault(r["species"], (r["group"], r["common_name"]))
us = {s["species"]: s for s in spec}
for s, (g, cn) in sorted(sp.items()):
    u = us.get(s); sql.append("INSERT INTO sounds.species VALUES (%s,%s,%s,%s,%s);" % (q(s), q(g), q(cn), u["usnm_specimens"] if u else "NULL", u["usnm_with_coordinates"] if u else "NULL"))
for l, f in sorted(lic.items()): sql.append("INSERT INTO sounds.licenses VALUES (%s,%s,%s,%s);" % (q(l), str(not f["nc"]).lower(), str(not f["nd"]).lower(), str(f["sa"]).lower()))
for r in rec:
    d = r["recorded_on"]; full = len(d) == 10
    sql.append("INSERT INTO sounds.recordings VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);" % (q(r["recording_id"]), q(r["group"]), q(r["species"]), q(call_type(r)),
        q(r["country"]), r["latitude"] or "NULL", r["longitude"] or "NULL", q(d) if full else "NULL", d[:4] or "NULL", q(r["recordist"]), q(r["license"]), q(r["source"]), q(r["source_ref"]), q(r["audio_url"]), q(r["image_url"])))
for t, c in COMMENTS.items(): sql.append("COMMENT ON TABLE %s IS %s;" % (t, q(c)))
for k, c in COLS.items(): sql.append("COMMENT ON COLUMN sounds.%s IS %s;" % (k, q(c)))
sql.append("""-- the app reads as a SELECT-only account
DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='omnigate_ro') THEN CREATE ROLE omnigate_ro LOGIN PASSWORD 'omnigate_ro'; END IF; END $$;
GRANT USAGE ON SCHEMA sounds TO omnigate_ro; GRANT SELECT ON ALL TABLES IN SCHEMA sounds TO omnigate_ro;""")
open(os.path.join(HERE, "seed-sounds.sql"), "w").write("\n".join(sql) + "\n")
json.dump({"entities": {"sounds:" + t: c for t, c in COMMENTS.items()}}, open(os.path.join(HERE, "sounds-knowledge.json"), "w"), indent=1)

Q = [
 ("How many recordings do we have for each bird species, most first?",
  "SELECT species, COUNT(*) AS recordings FROM sounds.recordings WHERE group_name = 'bird' GROUP BY species ORDER BY recordings DESC, species"),
 ("Which countries do the bird recordings come from, and how many from each?",
  "SELECT country, COUNT(*) AS recordings FROM sounds.recordings WHERE group_name = 'bird' GROUP BY country ORDER BY recordings DESC, country"),
 ("Which bird recordings are alarm calls?",
  "SELECT recording_id, species, country, recorded_on FROM sounds.recordings WHERE group_name = 'bird' AND call_type = 'alarm call' ORDER BY recording_id"),
 ("How many species and how many recordings do we have in each group, birds and fish?",
  "SELECT group_name, COUNT(DISTINCT species) AS species, COUNT(*) AS recordings FROM sounds.recordings GROUP BY group_name ORDER BY group_name"),
 ("Which fish recordings are grunts?",
  "SELECT recording_id, species, recorded_year FROM sounds.recordings WHERE group_name = 'fish' AND call_type = 'grunt' ORDER BY recording_id"),
 ("For each bird species with a recording, how many Smithsonian specimens does the NMNH hold, and how many of them have coordinates?",
  "SELECT s.species, s.usnm_specimens, s.usnm_with_coordinates FROM sounds.species s WHERE s.group_name = 'bird' AND EXISTS (SELECT 1 FROM sounds.recordings r WHERE r.species = s.species) ORDER BY s.usnm_specimens DESC"),
 ("Which bird species has the most Smithsonian specimens, and how many recordings do we have of it?",
  "SELECT s.species, s.usnm_specimens, COUNT(r.recording_id) AS recordings FROM sounds.species s LEFT JOIN sounds.recordings r ON r.species = s.species WHERE s.group_name = 'bird' GROUP BY s.species, s.usnm_specimens ORDER BY s.usnm_specimens DESC LIMIT 1"),
 ("What share of each bird species' Smithsonian specimens has coordinates, lowest first?",
  "SELECT species, ROUND(100.0 * usnm_with_coordinates / usnm_specimens, 1) AS pct_with_coordinates FROM sounds.species WHERE group_name = 'bird' ORDER BY pct_with_coordinates, species"),
 ("Which bird species have a recording but fewer than 1,500 Smithsonian specimens?",
  "SELECT species, usnm_specimens FROM sounds.species WHERE group_name = 'bird' AND usnm_specimens < 1500 ORDER BY usnm_specimens"),
 ("Which recordings carry a licence that forbids derived works?",
  "SELECT r.recording_id, r.species, r.license FROM sounds.recordings r JOIN sounds.licenses l ON l.license = r.license WHERE NOT l.allows_derivatives ORDER BY r.recording_id"),
 ("Which recordings can be used commercially?",
  "SELECT r.recording_id, r.species, r.license FROM sounds.recordings r JOIN sounds.licenses l ON l.license = r.license WHERE l.allows_commercial_use ORDER BY r.recording_id"),
 ("How many recordings do we have under each licence?",
  "SELECT license, COUNT(*) AS recordings FROM sounds.recordings GROUP BY license ORDER BY recordings DESC, license"),
 ("Who made the most bird recordings, and how many?",
  "SELECT recordist, COUNT(*) AS recordings FROM sounds.recordings WHERE group_name = 'bird' GROUP BY recordist ORDER BY recordings DESC, recordist LIMIT 1"),
 ("Which bird species were recorded in more than one country?",
  "SELECT species, COUNT(DISTINCT country) AS countries FROM sounds.recordings WHERE group_name = 'bird' GROUP BY species HAVING COUNT(DISTINCT country) > 1 ORDER BY countries DESC, species"),
 ("How many bird recordings were made in January 2026?",
  "SELECT COUNT(*) AS recordings FROM sounds.recordings WHERE group_name = 'bird' AND recorded_on >= DATE '2026-01-01' AND recorded_on < DATE '2026-02-01'"),
 ("Which fish species have more than one recording, and what call types do they have?",
  "SELECT species, COUNT(*) AS recordings, STRING_AGG(DISTINCT call_type, ', ' ORDER BY call_type) AS call_types FROM sounds.recordings WHERE group_name = 'fish' GROUP BY species HAVING COUNT(*) > 1 ORDER BY species"),
 ("Which recordings have no country, and what group are they in?",
  "SELECT group_name, COUNT(*) AS recordings FROM sounds.recordings WHERE country IS NULL GROUP BY group_name ORDER BY group_name"),
]
json.dump([{"question": a, "referenceSql": b, "category": "sounds"} for a, b in Q], open(os.path.join(HERE, "demo-questions-sounds.json"), "w"), indent=1)
print(len(rec), "recordings,", len(sp), "species,", len(Q), "questions")
