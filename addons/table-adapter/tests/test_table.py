"""python3 -m unittest discover -s addons/table-adapter/tests"""
import io, os, sys, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import adapter, tables

CSV = "id,name,amount,when,paid\n1,Acme,10.5,2026-01-02,true\n2,Beta,20,2026-02-03,false\n3,Acme,,2026-03-04,true\n".encode()
M = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def xlsx(rows_xml, styles=True, extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook %s/>" % M)
        z.writestr("xl/sharedStrings.xml", '<sst %s><si><t>city</t></si><si><t>day</t></si><si><t>Oslo</t></si></sst>' % M)
        if styles: z.writestr("xl/styles.xml", '<styleSheet %s><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>' % M)
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet %s><sheetData>%s</sheetData></worksheet>" % (M, rows_xml))
        for k, v in (extra or {}).items(): z.writestr(k, v)
    return b.getvalue()


ROWS = ('<row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="inlineStr"><is><t>n</t></is></c></row>'
        '<row><c r="A2" t="s"><v>2</v></c><c r="B2" s="1"><v>46023</v></c><c r="C2"><v>7</v></c></row>'
        '<row><c r="A3" t="s"><v>2</v></c><c r="C3"><v>9</v></c></row>')


class T(unittest.TestCase):
    def test_csv_profile(self):
        r = adapter.record(CSV, "pay.csv")["result"]
        t = {c["name"]: c for c in r["columns"]}
        self.assertEqual((r["rowsRead"], r["rowsInFile"], r["truncated"]), (3, 3, False))
        self.assertEqual((t["id"]["type"], t["amount"]["type"], t["when"]["type"], t["paid"]["type"], t["name"]["type"]), ("integer", "number", "date", "boolean", "text"))
        self.assertEqual((t["amount"]["nulls"], t["amount"]["min"], t["amount"]["max"]), (1, 10.5, 20.0))
        self.assertEqual(t["name"]["top"][0], ["Acme", 2]); self.assertEqual(r["preview"][0][1], "Acme")

    def test_semicolon_and_latin1(self):
        r = adapter.record("a;b\nx;é\n".encode("cp1252"), "x.csv")
        self.assertEqual(r["result"]["delimiter"], ";"); self.assertTrue(any("not UTF-8" in n for n in r["notes"]))

    def test_binary_is_refused(self):
        with self.assertRaises(tables.TableError): adapter.record(b"%PDF\x00\x01\x02" * 50, "x.csv")

    def test_xlsx_strings_numbers_and_dates(self):
        r = adapter.record(xlsx(ROWS), "w.xlsx")["result"]
        t = {c["name"]: c for c in r["columns"]}
        self.assertEqual((r["rowsRead"], t["city"]["type"], t["n"]["type"], t["day"]["type"]), (2, "text", "integer", "date"))
        self.assertEqual(t["day"]["min"], "2026-01-01"); self.assertEqual(t["day"]["nulls"], 1)      # gap cell kept as empty

    def test_xlsx_rejects_dtd_and_junk(self):
        with self.assertRaises(tables.TableError): adapter.record(xlsx("<row/>", extra={"xl/sharedStrings.xml": '<!DOCTYPE x [<!ENTITY a "b">]><sst/>'}), "x.xlsx")
        with self.assertRaises(tables.TableError): adapter.record(b"PK not really", "x.xlsx")

    def test_row_cap_is_reported(self):
        old = tables.MAX_ROWS; tables.MAX_ROWS = 5
        try:
            r = adapter.record(("a\n" + "\n".join(str(i) for i in range(20))).encode(), "big.csv")
            self.assertTrue(r["result"]["truncated"]); self.assertEqual(r["result"]["rowsRead"], 5); self.assertTrue(any("first 5 of 20" in n for n in r["notes"]))
        finally: tables.MAX_ROWS = old

    def test_duplicate_and_blank_headers_are_named(self):
        r = adapter.record(b"a,a,\n1,2,3\n", "d.csv")["result"]
        self.assertEqual([c["name"] for c in r["columns"]], ["a", "a_2", "column_3"])

    def test_honest_about_not_being_queryable(self):
        r = adapter.record(CSV, "pay.csv")
        self.assertEqual(r["askPrompts"], []); self.assertTrue(any("not in any Server data source" in n for n in r["notes"]))
        self.assertFalse(adapter.MANIFEST["nonCommercial"])

    def test_accepts(self):
        self.assertTrue(adapter.accepts("A.XLSX")); self.assertTrue(adapter.accepts("x", "text/csv; charset=utf-8")); self.assertFalse(adapter.accepts("a.pdf", "application/pdf"))


if __name__ == "__main__": unittest.main()
