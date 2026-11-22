import json, os, re, unittest
HERE = os.path.dirname(__file__)
SEED = open(os.path.join(HERE, "seed-estate-postgres.sql")).read()
QUESTIONS = json.load(open(os.path.join(HERE, "demo-questions-estate.json")))
QUESTIONS = QUESTIONS if isinstance(QUESTIONS, list) else QUESTIONS["questions"]

class EstateFields(unittest.TestCase):
    def test_cmdb_names_present(self):
        for col in ("business_criticality", "owned_by", "support_group", "install_status", "end_of_support", "last_discovered", "loss_event", "known_exploited", "epss", "cvss_score"):
            self.assertIn(col, SEED)
    def test_old_column_names_gone_from_questions(self):
        for q in QUESTIONS:
            self.assertNotRegex(q["referenceSql"], r"\bs\.tier\b|\bs\.owner_team\b")
    def test_questions_keep_output_names(self):
        sql = " ".join(q["referenceSql"] for q in QUESTIONS)
        self.assertIn("AS tier", sql); self.assertIn("AS owner_team", sql)
    def test_invented_cves_only(self):
        for cve in re.findall(r"CVE-\d{4}-\d+", SEED): self.assertTrue(cve.startswith("CVE-2026-9"), cve)

if __name__ == "__main__": unittest.main()
