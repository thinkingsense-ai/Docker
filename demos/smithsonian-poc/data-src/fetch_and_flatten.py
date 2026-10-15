import json, csv, sys, urllib.request

# Scaled up: more units (adds NMNHANTHRO and SIL per the brief's own taxonomy table, §4),
# more shards per unit, higher per-unit cap -- aiming for a more representative coverage number
# than Phase 1's small 612-label sample.
UNITS_AND_SHARDS = {
    "npg": [f"{i:02x}" for i in range(16)],
    "saam": [f"{i:02x}" for i in range(16)],
    "nmnhbotany": ["00", "01"],
    "nmnhanthro": [f"{i:02x}" for i in range(8)],
    "sil": [f"{i:02x}" for i in range(8)],
}
MAX_RECORDS_PER_UNIT = 2000
BASE = "https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan/{unit}/{shard}.txt"

rows = []
for unit, shards in UNITS_AND_SHARDS.items():
    count = 0
    for shard in shards:
        if count >= MAX_RECORDS_PER_UNIT:
            break
        url = BASE.format(unit=unit, shard=shard)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                for line in resp:
                    if count >= MAX_RECORDS_PER_UNIT:
                        break
                    line = line.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = d.get("content", {})
                    if not isinstance(content, dict) or d.get("type") != "edanmdm":
                        continue
                    desc = content.get("descriptiveNonRepeating", {})
                    usage = desc.get("metadata_usage", {}) or {}
                    if usage.get("access") != "CC0":
                        continue
                    record_id = desc.get("record_ID", d.get("id", ""))
                    title = (desc.get("title") or {}).get("content", d.get("title", ""))
                    unit_code = desc.get("unit_code", d.get("unitCode", ""))
                    record_link = desc.get("record_link", "")
                    topics = content.get("indexedStructured", {}).get("topic", []) or ["(no topic)"]
                    media = (desc.get("online_media") or {}).get("media", [])
                    image_url = media[0].get("content", "") if media else ""
                    for topic in topics:
                        rows.append({
                            "record_id": record_id,
                            "title": title,
                            "unit_code": unit_code,
                            "topic": topic,
                            "cc0": "true",
                            "image_url": image_url,
                            "record_link": record_link,
                        })
                    count += 1
        except Exception as e:
            print(f"skip {url}: {e}", file=sys.stderr)
    print(f"{unit}: {count} CC0 records", file=sys.stderr)

out_path = "/Users/kumarrajamani/Projects/ThinkingSense/Smithsonian-POC/data/si_open_access_sample.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["record_id","title","unit_code","topic","cc0","image_url","record_link"])
    w.writeheader()
    w.writerows(rows)

print(f"TOTAL topic-rows written: {len(rows)}", file=sys.stderr)
