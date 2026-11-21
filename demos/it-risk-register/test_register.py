"""Checks on the register vocabulary seed that need no database: the category tree is well formed, the rating scale is the four agreed values, and every approved question
names a table the seed creates. Run: python3 -m unittest demos/it-risk-register/test_register.py (from the repo root)."""
import json, os, re, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SQL = open(os.path.join(HERE, "seed-register-postgres.sql")).read()
QUESTIONS = json.load(open(os.path.join(HERE, "demo-questions-register.json")))


def taxonomy_rows():
    block = SQL.split("INSERT INTO register.taxonomy VALUES", 1)[1].split("CREATE TABLE register.rating_scale", 1)[0]
    # each row starts with ('NODE', PARENT|NULL, depth,
    return re.findall(r"^ \('([A-Z.]+)',\s*(NULL|'[A-Z.]+'),\s*(\d),", block, re.M)


class Taxonomy(unittest.TestCase):
    def test_every_parent_exists_and_depth_follows_the_id(self):
        rows = taxonomy_rows()
        self.assertGreaterEqual(len(rows), 30)
        ids = {r[0] for r in rows}
        self.assertEqual(len(ids), len(rows), "duplicate node id")
        for node, parent, depth in rows:
            self.assertEqual(int(depth), node.count(".") + 1, node)
            if parent == "NULL": self.assertEqual(depth, "1", node)
            else:
                self.assertIn(parent.strip("'"), ids, node)
                self.assertTrue(node.startswith(parent.strip("'") + "."), node)

    def test_the_five_notes_categories_are_there(self):
        for n in ("IRM", "INV", "LEG", "CAP", "PIA"): self.assertIn(f"CR.TMF.{n}", SQL)

    def test_every_status_is_one_of_the_three(self):
        block = SQL.split("INSERT INTO register.taxonomy VALUES", 1)[1].split("CREATE TABLE register.rating_scale", 1)[0]
        for s in re.findall(r"', '(notes|example|proposal)', ", block): self.assertIn(s, ("notes", "example", "proposal"))
        self.assertEqual(len(re.findall(r", '(?:notes|example|proposal)', ", block)), len(taxonomy_rows()))


class Scale(unittest.TestCase):
    def test_four_values_and_no_moderate(self):
        block = SQL.split("INSERT INTO register.rating_scale VALUES", 1)[1].split(");\n", 1)[0]
        self.assertEqual(re.findall(r"\('([A-Za-z]+)', (\d),", block), [("Low", "0"), ("Medium", "1"), ("High", "2"), ("Critical", "3")])
        self.assertNotIn("Moderate", SQL)


class Register(unittest.TestCase):
    def test_the_reload_drops_every_table_it_creates(self):
        drop = SQL.split("DROP TABLE IF EXISTS", 1)[1].split(";", 1)[0]
        for t in re.findall(r"CREATE TABLE (register\.\w+)", SQL): self.assertIn(t, drop, t)

    def test_assessments_is_append_only_and_inherent_only(self):
        self.assertIn("BEFORE UPDATE OR DELETE ON register.assessments", SQL)
        self.assertIn("BEFORE TRUNCATE ON register.assessments", SQL)
        self.assertIn("CHECK (inherent)", SQL)
        self.assertIn("CHECK (source = 'seed-example' OR (run_id IS NOT NULL AND evidence_digest IS NOT NULL))", SQL)

    def test_the_writer_role_can_only_insert(self):
        g = open(os.path.join(HERE, "grant-register.sql")).read()
        self.assertIn("GRANT INSERT ON register.assessments TO register_writer", g)
        self.assertNotRegex(g, r"GRANT[^;]*(UPDATE|DELETE|TRUNCATE)[^;]*register_writer")

    def test_every_seeded_category_and_rating_exists(self):
        ids = {r[0] for r in taxonomy_rows()}
        for node in re.findall(r"\('(?:event|candidate)','\w+','([A-Z.]+)'", SQL): self.assertIn(node, ids, node)
        for node in re.findall(r"^ \('(?:ai-[a-z-]+)',\s*'([A-Z.]+)'", SQL, re.M): self.assertIn(node, ids, node)
        for node, rating in re.findall(r"^ \('(?:case|system)','[^']*','([A-Z.]+)','(\w+)'", SQL, re.M):
            self.assertIn(node, ids); self.assertIn(rating, ("Low", "Medium", "High", "Critical"))


class Questions(unittest.TestCase):
    def test_each_question_reads_a_register_table_and_is_in_the_it_risk_category(self):
        for q in QUESTIONS:
            self.assertEqual(q["category"], "it-risk")
            tables = re.findall(r"pg\.register\.(\w+)", q["referenceSql"])
            self.assertTrue(tables, q["question"])
            for t in tables: self.assertIn(f"CREATE TABLE register.{t} (", SQL)

    def test_no_window_functions_until_server_139_is_fixed(self):
        for q in QUESTIONS: self.assertNotRegex(q["referenceSql"].upper(), r"\bOVER\s*\(")


if __name__ == "__main__":
    unittest.main()
