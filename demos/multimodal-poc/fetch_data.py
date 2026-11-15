#!/usr/bin/env python3
"""Build the multimodal POC dataset from open sources. No API key needed.

Birds:  Xeno-canto recordings via GBIF (dataset b1047888-...): species, behaviour, place, date, licence, mp3 + spectrogram URL.
        Smithsonian NMNH specimen counts for the same species via GBIF (institution USNM).
Fish:   a subset of the FishSounds data repository (Borealis, doi:10.5683/SP2/TACOUX, CC BY-NC 4.0): wav + spectrogram, with
        species and call type read from the file name.

Audio and images are downloaded into ./cache (git-ignored: licences vary per recording, several are non-commercial), and only
metadata and URLs are written to ./manifest/*.csv, which is what gets committed.
Usage: python3 fetch_data.py [--birds-per-species 6] [--fish 24] [--no-audio]
"""
import argparse, csv, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache"); MAN = os.path.join(HERE, "manifest")
XC = "b1047888-ae52-4179-9dd5-5448ea342a24"
BIRDS = ["Turdus migratorius", "Cardinalis cardinalis", "Cyanocitta cristata", "Poecile atricapillus",
         "Zenaida macroura", "Melospiza melodia", "Sturnus vulgaris", "Corvus brachyrhynchos"]
BORE = "https://borealisdata.ca"; FISH_DOI = "doi:10.5683/SP2/TACOUX"

def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "omnigate-multimodal-poc/0.1"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r: b = r.read()
            return b if binary else json.loads(b)
        except Exception as e:
            if i == 2: raise
            time.sleep(2)

def save(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0: return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(get(url, binary=True))

def lic(u): 
    m = re.search(r"licenses/([a-z\-]+)/([0-9.]+)", u or ""); return ("CC " + m.group(1).upper() + " " + m.group(2)) if m else (u or "")

def birds(n, audio):
    rows, spec = [], []
    for sp in BIRDS:
        q = urllib.parse.urlencode({"datasetKey": XC, "scientificName": sp, "mediaType": "Sound", "limit": 60})
        d = get("https://api.gbif.org/v1/occurrence/search?" + q)
        seen, picked = set(), []
        for r in d["results"]:   # spread over behaviours first so the set is varied
            b = (r.get("behavior") or "").lower() or "unknown"
            if b in seen and len(picked) < n - 2: continue
            snd = next((m for m in r.get("media", []) if m["type"] == "Sound"), None)
            img = next((m for m in r.get("media", []) if m["type"] == "StillImage"), None)
            if not snd: continue
            seen.add(b); picked.append((r, snd, img))
            if len(picked) == n: break
        for r, snd, img in picked:
            rid = "xc%s" % r["catalogNumber"].replace("XC", "") if r.get("catalogNumber") else "gbif%s" % r["key"]
            rows.append({"recording_id": rid, "group": "bird", "species": r.get("species") or sp,
                "common_name": r.get("vernacularName") or "", "behavior": (r.get("behavior") or "").lower(),
                "country": r.get("country") or "", "latitude": r.get("decimalLatitude") or "", "longitude": r.get("decimalLongitude") or "",
                "recorded_on": (r.get("eventDate") or "")[:10], "recordist": r.get("recordedBy") or "",
                "license": lic(snd.get("license") or r.get("license")), "audio_url": snd["identifier"], "image_url": img["identifier"] if img else "",
                "source": "Xeno-canto via GBIF", "source_ref": "https://www.gbif.org/occurrence/%s" % r["key"]})
            if audio:
                save(snd["identifier"], os.path.join(CACHE, "audio", rid + ".mp3"))
                if img: save(img["identifier"], os.path.join(CACHE, "image", rid + ".png"))
        # Smithsonian specimen holdings for this species
        c = get("https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode({"scientificName": sp, "institutionCode": "USNM", "limit": 0}))["count"]
        c2 = get("https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode({"scientificName": sp, "institutionCode": "USNM", "hasCoordinate": "true", "limit": 0}))["count"]
        spec.append({"species": sp, "usnm_specimens": c, "usnm_with_coordinates": c2, "source": "NMNH Extant Specimen Records via GBIF"})
        print(sp, len(picked), "recordings;", c, "USNM specimens", file=sys.stderr)
    return rows, spec

def fish(n, audio):
    d = get(BORE + "/api/datasets/:persistentId/?persistentId=" + FISH_DOI)["data"]["latestVersion"]
    files = {f["dataFile"]["filename"]: f["dataFile"] for f in d["files"]}
    wavs = sorted(k for k in files if k.lower().endswith(".wav") and files[k]["filesize"] < 1_500_000)
    pngs = [k for k in files if k.lower().endswith(".png")]
    rows, species_seen = [], {}
    for w in wavs:
        m = re.match(r"^(?P<ref>[^_]+)_(?P<au>[^_]+)-(?P<yr>\d{4})_(?P<sp>[A-Z][a-z]+-[a-z]+)_(?P<call>.+)\.wav$", w)
        if not m: continue
        sp = m["sp"].replace("-", " ")
        if species_seen.get(sp, 0) >= 2: continue      # spread across species
        species_seen[sp] = species_seen.get(sp, 0) + 1
        stem = w[:-4]; png = next((p for p in pngs if p.startswith(stem)), None)
        rid = "fs%04d" % (len(rows) + 1)
        base = BORE + "/api/access/datafile/"
        rows.append({"recording_id": rid, "group": "fish", "species": sp, "common_name": "", "behavior": m["call"].replace("-", " ").lower(),
            "country": "", "latitude": "", "longitude": "", "recorded_on": m["yr"], "recordist": m["au"],
            "license": "CC BY-NC 4.0", "audio_url": base + str(files[w]["id"]), "image_url": base + str(files[png]["id"]) if png else "",
            "source": "FishSounds data repository", "source_ref": "https://doi.org/10.5683/SP2/TACOUX"})
        if audio:
            save(base + str(files[w]["id"]), os.path.join(CACHE, "audio", rid + ".wav"))
            if png: save(base + str(files[png]["id"]), os.path.join(CACHE, "image", rid + ".png"))
        if len(rows) == n: break
    print("fish", len(rows), "recordings,", len(species_seen), "species", file=sys.stderr)
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--birds-per-species", type=int, default=6)
    ap.add_argument("--fish", type=int, default=24); ap.add_argument("--no-audio", action="store_true"); a = ap.parse_args()
    os.makedirs(MAN, exist_ok=True)
    b, spec = birds(a.birds_per_species, not a.no_audio); f = fish(a.fish, not a.no_audio)
    rows = b + f
    with open(os.path.join(MAN, "recordings.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(MAN, "usnm_specimens.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(spec[0])); w.writeheader(); w.writerows(spec)
    print("wrote", len(rows), "recordings and", len(spec), "species rows to", MAN)
