"""A table (CSV or XLSX) seen as a thinking-layer adapter (docs/agency-spec.md section 4). Reads and describes the file; keeps nothing."""
import tables

EXTS = [".csv", ".tsv", ".xlsx"]
MIMES = ["text/csv", "text/tab-separated-values", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
MAX_BYTES = 10_000_000
MANIFEST = {
    "id": "table-csv-xlsx", "title": "Tables (CSV, XLSX)", "kind": "table", "version": "1",
    "accepts": {"extensions": EXTS, "mime": MIMES}, "maxBytes": MAX_BYTES, "nonCommercial": False,
    "licence": "No third-party model or data: the file is read with the Python standard library and described, nothing is sent anywhere.",
    "notes": "First sheet only, first 100,000 rows and 60 columns. Column types are guesses from the values. The table is not loaded into any data source, so the Server cannot answer questions about it yet.",
}


def accepts(name, mime=None):
    n = (name or "").lower()
    return any(n.endswith(e) for e in EXTS) or (mime or "").split(";")[0].strip().lower() in MIMES


def record(data, name):
    n = (name or "").lower()
    if n.endswith(".xlsx") or data[:2] == b"PK": rows, total, info = tables.read_xlsx(data)
    else: rows, total, info = tables.read_csv(data)
    p = tables.profile(rows, total)
    p.update(info); p["name"] = name
    notes = ["The table was read and described only. It is not in any Server data source, so questions about its rows cannot be answered yet."]
    if p["truncated"]: notes.append("Only the first %d of %d rows were read." % (p["rowsRead"], p["rowsInFile"]))
    if p["columnsDropped"]: notes.append("%d columns beyond the first %d were ignored." % (p["columnsDropped"], tables.MAX_COLS))
    if info.get("encoding") not in (None, "utf-8-sig"): notes.append("The file is not UTF-8; it was read as %s, so accented characters may be wrong." % info["encoding"])
    if any(c["type"] == "text" and c["distinct"] == p["rowsRead"] and p["rowsRead"] > 20 for c in p["columns"]):
        notes.append("A text column where every value differs may be an identifier or free text.")
    return {"result": p, "notes": notes, "licence": MANIFEST["licence"], "askPrompts": []}
