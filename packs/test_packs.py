"""python3 -m unittest discover -s packs   (from the repository root)"""
import json, os, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import packs


class PackTests(unittest.TestCase):
    def test_generated_files_are_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "packs.py"), "check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_pack_directory_has_a_manifest_named_for_it(self):
        for d in os.listdir(HERE):
            if os.path.isdir(os.path.join(HERE, d)) and not d.startswith("__"):
                self.assertEqual(json.load(open(os.path.join(HERE, d, "pack.json")))["id"], d)

    def test_all_packs_question_file_is_fully_covered(self):
        cats = {}
        for q in json.load(open(os.path.join(ROOT, "demos/all-packs/demo-questions-all-packs.json"))):
            cats[q["category"]] = cats.get(q["category"], 0) + 1
        got = {e["id"]: e["questions"]["approved"] for e in json.load(open(os.path.join(HERE, "catalogue.json")))["packs"] if e["inAllPacks"]}
        self.assertEqual(got, cats)

    def test_a_question_using_an_undeclared_schema_is_reported(self):
        p = {"id": "x", "title": "x", "summary": "x", "sources": [{"id": "pg", "schemas": ["a"]}], "questions": {"file": "f", "category": None},
             "modalities": [], "inAllPacks": False, "editions": [], "licence": {}}
        self.assertTrue(packs.problems(p, [{"question": "q", "referenceSql": "SELECT 1 FROM pg.b.t"}]))

    def test_workspace_entries_only_name_declared_backends(self):
        for p in packs.load_manifests():
            ids = {s["id"] for s in p["sources"]}
            self.assertTrue(ids <= {"pg", "mdb", "files"})

    def test_it_risk_is_listed_first_and_all_data_last(self):
        ids = [l.split(": ")[1].strip() for l in open(os.path.join(HERE, "workspaces.yaml")) if l.startswith("  - id: ")]
        self.assertEqual(ids[0], "it-risk"); self.assertEqual(ids[-1], "all-data"); self.assertIn("treasury", ids)

    def test_workspaces_yaml_parses_when_pyyaml_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        d = yaml.safe_load(open(os.path.join(HERE, "workspaces.yaml")))
        self.assertTrue(all({"id", "name", "backends"} <= set(n) for n in d["namespaces"]))


if __name__ == "__main__":
    unittest.main()
