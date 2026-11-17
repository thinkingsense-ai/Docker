"""python3 -m unittest discover -s packs   (needs helm; skipped without it). Renders the AKS chart: the list form `demoDatasets` against the single `demoDataset`, selection errors, and what a mix puts in the stack."""
import collections, json, os, re, shutil, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import deploy_options as D

CHART = os.path.join(ROOT, D.CHARTS["azure"])
HAVE = shutil.which("helm") is not None


def render(*sets):
    args = ["helm", "template", "rel", CHART, "--set", D.USERS]
    for s in sets: args += ["--set", s]
    r = subprocess.run(args, capture_output=True, text=True); return r.returncode, r.stdout, r.stderr


def norm(t):          # the charts generate fresh passwords and keys on every render: mask them to compare two renders
    t = re.sub(r"[A-Za-z0-9]{32}", "R32", t); t = re.sub(r"(checksum/[a-z-]+): [0-9a-f]{64}", r"\1: X", t)
    return re.sub(r'(OMNIGATE_CONFIG_ENCRYPTION_KEY: ")[^"]+', r'\1K', t)


def questions(t):
    i = t.index("questions.json: |"); body = []
    for line in t[i:].split("\n")[1:]:
        if line.startswith("    "): body.append(line[4:])
        else: break
    return collections.Counter(q["category"] for q in json.loads("\n".join(body)))


@unittest.skipUnless(HAVE, "helm not installed")
class T(unittest.TestCase):
    def test_a_list_that_names_a_whole_configuration_renders_exactly_that_configuration(self):
        pairs = [("it-risk", "it-risk"), ("bom", "bom"), ("treasury", "treasury"), ("supply-chain,manufacturing", "supply-chain"), ("manufacturing", "supply-chain"),
                 ("supply-chain,manufacturing,it-risk,smithsonian,bom,treasury", "all-packs"), ("treasury,smithsonian,bom,it-risk,manufacturing,supply-chain", "all-packs")]
        for sel, legacy in pairs:
            a = render("demoDataset=" + legacy); b = render("demoDatasets={%s}" % sel)
            self.assertEqual((a[0], b[0]), (0, 0), (sel, b[2])); self.assertEqual(norm(a[1]), norm(b[1]), "[%s] is not identical to demoDataset=%s" % (sel, legacy))

    def test_no_list_means_the_single_dataset_rules_exactly_as_before(self):
        a, b = render("demoDataset=bom"), render("demoDataset=bom", "demoDatasets=null")
        self.assertEqual((a[0], b[0]), (0, 0)); self.assertEqual(norm(a[1]), norm(b[1]))

    def test_selection_errors_say_why(self):
        for sel, text in (("{nope}", "is not a pack the charts can deploy"), ("{bom,smithsonian}", "only deployed together with all six")):
            rc, _, err = render("demoDatasets=" + sel); self.assertNotEqual(rc, 0); self.assertIn(text, err)

    def test_a_mix_holds_only_the_chosen_packs(self):
        rc, t, err = render("demoDatasets={bom,treasury}", "seedDemoQuestions.enabled=true"); self.assertEqual(rc, 0, err)
        self.assertIn('OMNIGATE_FEDERATION_SCHEMA_INCLUDE: "bom,treasury,erp"', t)
        self.assertEqual(set(re.findall(r"(?m)^  (0\d-seed[\w.-]+): \|", t)) & {"03-seed-bom.sql", "04-seed-treasury-postgres.sql", "01-seed-supply-chain.sql", "02-seed-it-risk-postgres.sql"}, {"03-seed-bom.sql", "04-seed-treasury-postgres.sql"})
        self.assertRegex(t, r'OMNIGATE_BACKENDS: "pg=jdbc:postgresql://rel-postgres:5432/postgres\|omnigate_ro\|\w+;mdb=jdbc:mariadb://rel-mariadb:3306/\|omnigate_ro\|\w+"')   # no `files`
        self.assertEqual(questions(t), {"bom": 24, "treasury": 24}); self.assertIn("MARIADB_DATABASE", t); self.assertRegex(t, r"MARIADB_DATABASE\s*\n\s+value: erp")
        for absent in ("rel-packs-s3", "name: rel-packs-loader", "name: ensure-manufacturing-demo", "name: wait-for-packs-data"): self.assertNotIn(absent, t, absent)

    def test_a_mix_without_a_pack_that_needs_mariadb_or_the_embedding_model_has_neither(self):
        rc, t, err = render("demoDatasets={supply-chain,bom}", "seedDemoQuestions.enabled=true"); self.assertEqual(rc, 0, err)
        self.assertNotIn("rel-mariadb", t); self.assertIn("rel-packs-embed", t); self.assertNotIn("mdb=", t); self.assertRegex(t, r'OMNIGATE_BACKENDS: "pg=jdbc:postgresql')
        rc, t, err = render("demoDatasets={it-risk,supply-chain}"); self.assertEqual(rc, 0, err)
        self.assertNotIn("rel-packs-embed", t); self.assertNotIn("OMNIGATE_QUESTION_BANK_RETRIEVAL_ENABLED", t); self.assertIn("rel-mariadb", t)

    def test_the_manufacturing_tables_come_only_when_manufacturing_is_chosen(self):
        self.assertIn("name: ensure-manufacturing-demo", render("demoDatasets={manufacturing,bom}")[1])
        self.assertNotIn("name: ensure-manufacturing-demo", render("demoDatasets={supply-chain,bom}")[1])
        self.assertEqual(questions(render("demoDatasets={manufacturing,bom}", "seedDemoQuestions.enabled=true")[1]), {"supply-chain": 5, "manufacturing": 6, "bom": 24})

    def test_the_payment_workflow_add_on_needs_treasury_alone(self):
        self.assertEqual(render("demoDatasets={treasury}", "paymentWorkflow.enabled=true")[0], 0)
        rc, _, err = render("demoDatasets={treasury,bom}", "paymentWorkflow.enabled=true"); self.assertNotEqual(rc, 0); self.assertIn("Treasury pack on its own", err)


if __name__ == "__main__": unittest.main()
