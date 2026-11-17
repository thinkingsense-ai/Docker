"""Reads a CSV or XLSX into a profile: columns with a guessed type, counts, a few preview rows. Standard library only; nothing is written anywhere.
Limits keep a hostile or huge file from using the container's memory: MAX_ROWS rows are read (the rest are counted as "not read"), MAX_COLS columns are kept."""
import csv, datetime, io, re, zipfile
import xml.etree.ElementTree as ET

MAX_ROWS, MAX_COLS, PREVIEW_ROWS, MAX_SHEET_BYTES = 100_000, 60, 10, 80_000_000
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
BUILTIN_DATE_FMTS = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}


class TableError(ValueError):
    pass


def decode(data):
    for enc in ("utf-8-sig", "cp1252"):
        try: return data.decode(enc), enc
        except UnicodeDecodeError: pass
    return data.decode("latin-1"), "latin-1"


def read_csv(data):
    text, enc = decode(data)
    if "\x00" in text[:4096]: raise TableError("That does not look like a text CSV file.")
    try: dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
    except csv.Error: dialect = csv.excel
    rows, total = [], 0
    for r in csv.reader(io.StringIO(text), dialect):
        if not any(c.strip() for c in r): continue
        total += 1
        if len(rows) < MAX_ROWS + 1: rows.append(r)
    return rows, total, {"encoding": enc, "delimiter": dialect.delimiter}


def col_letters_to_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0): n = n * 26 + ord(ch) - 64
    return n - 1


def excel_date(v):
    return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(v)))


def read_xlsx(data):
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: raise TableError("That is not a valid .xlsx file.")
    names = {i.filename: i for i in z.infolist()}
    if "xl/workbook.xml" not in names: raise TableError("That is not a valid .xlsx file.")

    def blob(name):
        i = names.get(name)
        if i is None: return None
        if i.file_size > MAX_SHEET_BYTES: raise TableError("A part of the workbook is too large to read safely.")
        b = z.read(name)
        if b"<!DOCTYPE" in b[:2000] or b"<!ENTITY" in b[:2000]: raise TableError("The workbook contains a DTD, which is refused.")
        return b

    shared = []
    sb = blob("xl/sharedStrings.xml")
    if sb:
        for si in ET.fromstring(sb).iter(NS + "si"): shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    date_xf = set()
    st = blob("xl/styles.xml")
    if st:
        root = ET.fromstring(st)
        custom = {int(n.get("numFmtId")): n.get("formatCode", "") for n in root.iter(NS + "numFmt")}
        xfs = root.find(NS + "cellXfs")
        for i, xf in enumerate(xfs if xfs is not None else []):
            fid = int(xf.get("numFmtId", "0"))
            code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fid, "")).lower()
            if fid in BUILTIN_DATE_FMTS or (fid in custom and re.search(r"[ymd]", code) and not re.search(r"[#0]", code)): date_xf.add(i)
    sheet = "xl/worksheets/sheet1.xml"
    if sheet not in names:
        found = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        if not found: raise TableError("The workbook has no sheets.")
        sheet = found[0]
    if names[sheet].file_size > MAX_SHEET_BYTES: raise TableError("The first sheet is too large to read safely.")
    rows, total = [], 0
    with z.open(sheet) as f:
        head = f.read(2000)
        if b"<!DOCTYPE" in head or b"<!ENTITY" in head: raise TableError("The workbook contains a DTD, which is refused.")
    with z.open(sheet) as f:
        for _, el in ET.iterparse(f):
            if el.tag != NS + "row": continue
            cells = {}
            for c in el.iter(NS + "c"):
                v, t = c.find(NS + "v"), c.get("t")
                if t == "inlineStr": val = "".join(x.text or "" for x in c.iter(NS + "t"))
                elif v is None or v.text is None: continue
                elif t == "s": val = shared[int(v.text)]
                elif t == "b": val = "true" if v.text == "1" else "false"
                elif t in ("str", "e"): val = v.text
                else:
                    val = v.text
                    if int(c.get("s", "0")) in date_xf:
                        try: d = excel_date(val); val = d.strftime("%Y-%m-%d") if d.time() == datetime.time() else d.strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, OverflowError): pass
                cells[col_letters_to_index(c.get("r", "A1"))] = val
            el.clear()
            if not cells: continue
            total += 1
            if len(rows) < MAX_ROWS + 1: rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows, total, {"sheet": sheet.rsplit("/", 1)[-1]}


def kind_of(v):
    s = v.strip()
    if re.fullmatch(r"[+-]?\d+", s) and len(s.lstrip("+-")) < 16: return "integer"
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", s): return "number"
    if s.lower() in ("true", "false"): return "boolean"
    for f in DATE_FORMATS:
        try: datetime.datetime.strptime(s, f); return "date"
        except ValueError: pass
    return "text"


def column_type(kinds):
    ks = set(kinds)
    if not ks: return "empty"
    if ks == {"integer", "number"} or ks == {"number"}: return "number"
    return ks.pop() if len(ks) == 1 else "text"


def num(v): return float(v.strip())


def profile(rows, total):
    if not rows: raise TableError("The file has no rows.")
    head, body = rows[0], rows[1:]
    names, seen = [], {}
    for i, h in enumerate(head[:MAX_COLS]):
        h = (h or "").strip() or "column_%d" % (i + 1)
        seen[h] = seen.get(h, 0) + 1
        names.append(h if seen[h] == 1 else "%s_%d" % (h, seen[h]))
    width = len(names)
    cols = []
    for i, name in enumerate(names):
        vals = [r[i].strip() if i < len(r) and r[i] is not None else "" for r in body]
        filled = [v for v in vals if v != ""]
        t = column_type([kind_of(v) for v in filled])
        c = {"name": name, "type": t, "nulls": len(vals) - len(filled), "distinct": len(set(filled))}
        if t in ("integer", "number") and filled: lo, hi = min(map(num, filled)), max(map(num, filled)); c["min"], c["max"] = (int(lo), int(hi)) if t == "integer" else (lo, hi)
        elif t == "date" and filled: c["min"], c["max"] = min(filled), max(filled)
        elif t == "text" and filled and c["distinct"] <= 12:
            counts = {}
            for v in filled: counts[v] = counts.get(v, 0) + 1
            c["top"] = [[k, n] for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
        cols.append(c)
    return {"columns": cols, "rowsRead": len(body[:MAX_ROWS]), "rowsInFile": max(total - 1, 0), "truncated": total - 1 > MAX_ROWS,
            "columnsDropped": max(len(head) - MAX_COLS, 0),
            "preview": [[(r[i] if i < len(r) else "") for i in range(width)] for r in body[:PREVIEW_ROWS]]}
