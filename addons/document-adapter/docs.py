"""Reads a PDF, DOCX, Markdown or text file into plain text and describes it. Nothing is written anywhere. Only PDF needs a library (pypdf, BSD-3-Clause);
DOCX is read with the standard library. No OCR: a PDF that is only page images has no text and is reported as such."""
import io, re, zipfile
import xml.etree.ElementTree as ET

MAX_PAGES, MAX_CHARS, MAX_PART_BYTES, CHUNK_CHARS, PREVIEW_CHARS = 300, 2_000_000, 40_000_000, 800, 1200
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STOP = set("""about above after again also another because been before being between both could does done each from have having here into just like many more most much must only other over said same should some such than that their them then there these they this those through under very want were what when where which while will with would your""".split())


class DocError(ValueError):
    pass


def read_text(data):
    for enc in ("utf-8-sig", "cp1252"):
        try: return data.decode(enc), enc
        except UnicodeDecodeError: pass
    return data.decode("latin-1"), "latin-1"


def read_plain(data, name):
    text, enc = read_text(data)
    if "\x00" in text[:4096]: raise DocError("That does not look like a text file.")
    heads = []
    if name.lower().endswith((".md", ".markdown")):
        heads = [(len(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(#{1,4})\s+(.+)$", text, re.M)]
    return {"pages": [text], "headings": heads, "extra": {"encoding": enc}}


def read_docx(data):
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: raise DocError("That is not a valid .docx file.")
    try: info = z.getinfo("word/document.xml")
    except KeyError: raise DocError("That is not a valid .docx file.")
    if info.file_size > MAX_PART_BYTES: raise DocError("The document is too large to read safely.")
    xml = z.read("word/document.xml")
    if b"<!DOCTYPE" in xml[:2000] or b"<!ENTITY" in xml[:2000]: raise DocError("The document contains a DTD, which is refused.")
    paras, heads = [], []
    for p in ET.fromstring(xml).iter(W + "p"):
        t = "".join((n.text or "") if n.tag == W + "t" else "\t" if n.tag == W + "tab" else "\n" if n.tag == W + "br" else "" for n in p.iter()).strip()
        if not t: continue
        st = p.find("%spPr/%spStyle" % (W, W))
        m = re.match(r"(?:heading|Heading)\s*(\d)$", st.get(W + "val", "")) if st is not None else None
        if m: heads.append((int(m.group(1)), t))
        paras.append(t)
    return {"pages": ["\n\n".join(paras)], "headings": heads, "extra": {}}


def read_pdf(data):
    try: import pypdf
    except ImportError: raise DocError("PDF reading is not installed in this adapter.")
    try:
        r = pypdf.PdfReader(io.BytesIO(data))
        if r.is_encrypted: raise DocError("The PDF is password-protected.")
        n = len(r.pages)
        pages = [(r.pages[i].extract_text() or "") for i in range(min(n, MAX_PAGES))]
    except DocError: raise
    except Exception: raise DocError("That is not a PDF this adapter can read.")
    return {"pages": pages, "headings": [], "extra": {"pagesInFile": n}}


def chunks(text):
    out, cur = [], ""
    for para in re.split(r"\n\s*\n|\n(?=[A-Z0-9•-])", text):
        para = para.strip()
        if not para: continue
        if cur and len(cur) + len(para) > CHUNK_CHARS: out.append(cur); cur = ""
        cur = (cur + "\n" + para).strip()
        while len(cur) > CHUNK_CHARS * 2: out.append(cur[:CHUNK_CHARS]); cur = cur[CHUNK_CHARS:]
    if cur: out.append(cur)
    return out


def describe(doc):
    pages = doc["pages"]
    text = "\n\n".join(pages)[:MAX_CHARS]
    words = re.findall(r"[A-Za-zÀ-ɏ]{2,}", text)
    counts = {}
    for w in words:
        w = w.lower()
        if len(w) >= 4 and w not in STOP: counts[w] = counts.get(w, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {"pages": len(pages), "words": len(words), "characters": len(text), "chunks": len(chunks(text)),
            "headings": [{"level": l, "text": t[:120]} for l, t in doc["headings"][:30]],
            "topTerms": [[w, n] for w, n in top], "preview": re.sub(r"\n{3,}", "\n\n", text[:PREVIEW_CHARS]).strip(), "truncated": len("\n\n".join(pages)) > MAX_CHARS}
