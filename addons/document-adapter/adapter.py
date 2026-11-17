"""A document (PDF, DOCX, Markdown, text) seen as a thinking-layer adapter (docs/agency-spec.md section 4). Reads and describes the file; keeps nothing."""
import docs

EXTS = [".pdf", ".docx", ".md", ".markdown", ".txt"]
MIMES = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/markdown", "text/plain"]
MAX_BYTES = 25_000_000
MANIFEST = {
    "id": "document-pdf-docx-text", "title": "Documents (PDF, DOCX, Markdown, text)", "kind": "document", "version": "1",
    "accepts": {"extensions": EXTS, "mime": MIMES}, "maxBytes": MAX_BYTES, "nonCommercial": False,
    "licence": "The text is read with pypdf (BSD-3-Clause) and the Python standard library, and described; nothing is sent anywhere.",
    "notes": "No OCR: scanned PDFs have no text to read. First 300 PDF pages. The document is not loaded into any data source or search index, so the Server cannot answer questions about its text yet.",
}


def accepts(name, mime=None):
    n = (name or "").lower()
    return any(n.endswith(e) for e in EXTS) or (mime or "").split(";")[0].strip().lower() in MIMES


def record(data, name):
    n = (name or "").lower()
    if n.endswith(".pdf") or data[:5] == b"%PDF-": doc, kind = docs.read_pdf(data), "pdf"
    elif n.endswith(".docx") or data[:2] == b"PK": doc, kind = docs.read_docx(data), "docx"
    else: doc, kind = docs.read_plain(data, n), "text"
    d = docs.describe(doc); d.update(doc["extra"]); d["format"] = kind; d["name"] = name
    notes = ["The document was read and described only. It is not in any Server data source or search index, so questions about its text cannot be answered yet."]
    if d["words"] == 0 or (kind == "pdf" and d["words"] < 20 * max(d["pages"], 1)):
        notes.append("Very little text was found. A scanned PDF holds page images, and this adapter does not do OCR.")
    if d.get("pagesInFile", 0) > d["pages"]: notes.append("Only the first %d of %d pages were read." % (d["pages"], d["pagesInFile"]))
    if d["truncated"]: notes.append("Only the first %s characters were read." % format(docs.MAX_CHARS, ","))
    if kind == "pdf": notes.append("PDF text comes out in reading order as best it can; columns, tables and headings are not reconstructed.")
    if d.get("encoding") not in (None, "utf-8-sig"): notes.append("The file is not UTF-8; it was read as %s, so accented characters may be wrong." % d["encoding"])
    notes.append("Top terms are plain word counts and assume English; they are not a summary.")
    return {"result": d, "notes": notes, "licence": MANIFEST["licence"], "askPrompts": []}
