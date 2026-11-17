"""python3 -m unittest discover -s addons/document-adapter/tests     (PDF tests need pypdf and are skipped without it)"""
import io, os, sys, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import adapter, docs
try: import pypdf; HAVE = True
except ImportError: HAVE = False

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(body, extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", "<w:document %s><w:body>%s</w:body></w:document>" % (W, body))
        for k, v in (extra or {}).items(): z.writestr(k, v)
    return b.getvalue()


def para(t, style=None):
    s = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return "<w:p>%s<w:r><w:t>%s</w:t></w:r></w:p>" % (s, t)


def pdf(pages):
    """A minimal valid PDF, one line of Helvetica text per page (empty string = a page with no text)."""
    objs = ["<</Type/Catalog/Pages 2 0 R>>", None, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    kids = []
    for t in pages:
        content = ("BT /F1 12 Tf 72 700 Td (%s) Tj ET" % t) if t else ""
        objs.append("<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 3 0 R>>>>/Contents %d 0 R>>" % (len(objs) + 2))
        kids.append("%d 0 R" % len(objs))
        objs.append("<</Length %d>>\nstream\n%s\nendstream" % (len(content), content))
    objs[1] = "<</Type/Pages/Kids[%s]/Count %d>>" % (" ".join(kids), len(pages))
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs):
        offs.append(len(out)); out += ("%d 0 obj\n%s\nendobj\n" % (i + 1, o)).encode()
    x = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode() + b"".join(("%010d 00000 n \n" % o).encode() for o in offs)
    return out + ("trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)).encode()


class T(unittest.TestCase):
    def test_markdown_headings_and_terms(self):
        md = b"# Supplier policy\n\nSuppliers must hold insurance. Insurance certificates expire yearly.\n\n## Audits\n\nAudits happen yearly; insurance is checked.\n"
        r = adapter.record(md, "p.md")["result"]
        self.assertEqual([h["text"] for h in r["headings"]], ["Supplier policy", "Audits"]); self.assertEqual(r["headings"][1]["level"], 2)
        self.assertEqual(r["topTerms"][0][0], "insurance"); self.assertEqual(r["format"], "text"); self.assertGreaterEqual(r["chunks"], 1)

    def test_docx_text_and_heading_styles(self):
        r = adapter.record(docx(para("Contract", "Heading1") + para("The buyer pays within thirty days.") + para("Terms", "Heading2")), "c.docx")["result"]
        self.assertEqual([(h["level"], h["text"]) for h in r["headings"]], [(1, "Contract"), (2, "Terms")])
        self.assertIn("buyer pays", r["preview"]); self.assertEqual(r["format"], "docx")

    def test_docx_dtd_and_junk_refused(self):
        with self.assertRaises(docs.DocError): adapter.record(docx("", {"word/document.xml": '<!DOCTYPE x [<!ENTITY a "b">]><w:document/>'}), "x.docx")
        with self.assertRaises(docs.DocError): adapter.record(b"PK not a zip", "x.docx")
        with self.assertRaises(docs.DocError): adapter.record(docx("").replace(b"word/document.xml", b"word/other.xml"), "x.docx")

    def test_binary_text_refused(self):
        with self.assertRaises(docs.DocError): adapter.record(b"abc\x00\x01" * 100, "x.txt")

    @unittest.skipUnless(HAVE, "pypdf not installed")
    def test_pdf_pages_and_text(self):
        r = adapter.record(pdf(["Insurance certificate for Acme", "Second page about audits"]), "a.pdf")
        d = r["result"]; self.assertEqual((d["pages"], d["format"]), (2, "pdf")); self.assertIn("Insurance certificate", d["preview"])
        self.assertTrue(any("not reconstructed" in n for n in r["notes"]))

    @unittest.skipUnless(HAVE, "pypdf not installed")
    def test_pdf_without_text_is_called_out(self):
        r = adapter.record(pdf(["", ""]), "scan.pdf")
        self.assertEqual(r["result"]["words"], 0); self.assertTrue(any("OCR" in n for n in r["notes"]))

    @unittest.skipUnless(HAVE, "pypdf not installed")
    def test_pdf_page_cap_and_junk(self):
        old = docs.MAX_PAGES; docs.MAX_PAGES = 2
        try:
            r = adapter.record(pdf(["one two three four"] * 5), "big.pdf"); self.assertEqual(r["result"]["pages"], 2); self.assertTrue(any("first 2 of 5" in n for n in r["notes"]))
        finally: docs.MAX_PAGES = old
        with self.assertRaises(docs.DocError): adapter.record(b"%PDF-1.4 garbage", "bad.pdf")

    def test_honest_about_not_being_searchable(self):
        r = adapter.record(b"hello world again", "a.txt")
        self.assertEqual(r["askPrompts"], []); self.assertTrue(any("not in any Server data source" in n for n in r["notes"])); self.assertFalse(adapter.MANIFEST["nonCommercial"])

    def test_chunks_respect_size(self):
        c = docs.chunks("\n\n".join("word " * 60 for _ in range(10)))
        self.assertTrue(all(len(x) <= docs.CHUNK_CHARS * 2 for x in c)); self.assertGreater(len(c), 1)

    def test_accepts(self):
        self.assertTrue(adapter.accepts("A.PDF")); self.assertTrue(adapter.accepts("x", "text/markdown")); self.assertFalse(adapter.accepts("a.csv", "text/csv"))


if __name__ == "__main__": unittest.main()
