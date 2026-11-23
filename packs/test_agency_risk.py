"""python3 -m unittest packs.test_agency_risk   (needs helm; skipped without it). The chart-only `agency-risk` pack: what it adds to a selection, and that the older selections do not change."""
import json, os, re, shutil, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D
HAVE = shutil.which("helm") is not None
SIX = "supply-chain,manufacturing,it-risk,smithsonian,bom,treasury"

def render(chart, sel, only=None):
    args = ["helm", "template", "rel", os.path.join(ROOT, chart), "--set", D.USERS, "--set", "seedDemoQuestions.enabled=true", "--set", "demoDatasets={%s}" % sel]
    if only: args += ["--show-only", only]
    r = subprocess.run(args, capture_output=True, text=True); return r.returncode, r.stdout, r.stderr

def questions(chart, sel):
    out = render(chart, sel, "templates/seed-questions.yaml")[1]
    m = re.search(r"  questions.json: \|\n((?:    .*\n|\n)+)", out); return json.loads("\n".join(l[4:] for l in m.group(1).split("\n")))

@unittest.skipUnless(HAVE, "helm is not installed")
class AgencyRisk(unittest.TestCase):
    def test_each_chart_adds_the_schemas_seeds_and_questions(self):
        for name, chart in D.CHARTS.items():
            with self.subTest(chart=name):
                rc, out, err = render(chart, "agency-risk"); self.assertEqual(rc, 0, err)
                self.assertIn('OMNIGATE_FEDERATION_SCHEMA_INCLUDE: "risk,security,rca,estate,register"', out)       # it-risk came in with it
                for f in ("05-seed-agency-rca.sql", "06-seed-agency-estate.sql", "07-seed-agency-register.sql", "02-seed-it-risk-postgres.sql"): self.assertIn(f + ": |", out)
                q = questions(chart, "agency-risk"); self.assertEqual(len(q), 39); self.assertEqual(len({x["question"] for x in q}), 39)
                self.assertIn("llama.cpp", out)                                                                      # the embedding model, so approved questions are answered from the bank
    def test_it_risk_alone_and_all_packs_do_not_gain_the_data(self):
        for name, chart in D.CHARTS.items():
            with self.subTest(chart=name):
                for sel in ("it-risk", SIX):
                    out = render(chart, sel)[1]; m = re.search(r"OMNIGATE_FEDERATION_SCHEMA_INCLUDE: \"([^\"]*)\"", out)          # a single pack has no schema list
                    if m: self.assertNotIn("rca", m.group(1).split(","))
                    self.assertNotIn("05-seed-agency-rca.sql", out)
                out = subprocess.run(["helm", "template", "rel", os.path.join(ROOT, chart), "--set", D.USERS, "--set", "demoDataset=all-packs"], capture_output=True, text=True).stdout
                self.assertNotIn("05-seed-agency-rca.sql", out)
    def test_it_mixes_with_other_packs_and_with_all_six(self):
        chart = D.CHARTS["azure"]
        out = render(chart, "agency-risk,treasury")[1]; self.assertIn("treasury,erp,rca,estate,register", out)
        self.assertEqual(len(questions(chart, "agency-risk,treasury")), 63)
        rc, out, err = render(chart, SIX + ",agency-risk"); self.assertEqual(rc, 0, err); self.assertIn("erp,rca,estate,register", out)
    def test_smithsonian_still_needs_all_six(self):
        rc, _, err = render(D.CHARTS["azure"], "smithsonian,agency-risk"); self.assertNotEqual(rc, 0); self.assertIn("Smithsonian", err)

if __name__ == "__main__": unittest.main()
