"""python3 -m unittest discover -s packs   (from the repository root)"""
import json, os, re, subprocess, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import aws_form as F
TEMPLATE = open(F.TEMPLATE).read()
O = json.load(open(os.path.join(HERE, "deploy-options.json")))


class T(unittest.TestCase):
    def test_the_generated_blocks_are_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "aws_form.py"), "check"], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_rules_list_exactly_the_packs_the_charts_can_deploy(self):
        m = re.search(r'Fn::EachMemberIn:\n\s+- !Ref DemoPacks\n\s+- \[(.*?)\]', TEMPLATE); known = [x.strip().strip('"') for x in m.group(1).split(",")]
        self.assertEqual(sorted(k for k in known if k), sorted(p["id"] for p in O["packs"])); self.assertIn("", known)          # empty is allowed: the default

    def test_the_smithsonian_rule_asks_for_every_other_pack(self):
        block = TEMPLATE[TEMPLATE.index("SmithsonianNeedsAllPacks:"):TEMPLATE.index("PacksOrDemoDataNotBoth:")]
        asked = set(re.findall(r"- !Ref DemoPacks\n\s+- ([a-z-]+)", block)) - {"smithsonian"}
        self.assertEqual(asked, {p["id"] for p in O["packs"]} - {"smithsonian"})

    def test_the_form_parameter_fits_cloudformations_limits_and_is_off_by_default(self):
        m = re.search(r'DemoPacks:\n    Type: CommaDelimitedList\n    Default: ""\n    Description: (".*")\n', TEMPLATE)
        self.assertTrue(m); text = json.loads(m.group(1)); self.assertLess(len(text), 4000)                                     # CloudFormation's parameter description limit
        for p in O["packs"]: self.assertIn(p["id"], text)
        self.assertIn("t4g.medium", text); self.assertIn("Known issue", text)

    def test_the_old_dropdown_still_exists_and_the_template_stays_under_the_inline_size_limit(self):
        self.assertIn("AllowedValues: [supply-chain, it-risk, bom, treasury, all-packs]", TEMPLATE); self.assertLess(len(TEMPLATE.encode()), 51200)

    def test_the_custom_resource_passes_the_list_to_the_deployer(self):
        self.assertIn("DemoPacks: !Ref DemoPacks", TEMPLATE); self.assertIn("demoDataset: !Ref DemoDataset", TEMPLATE)
        self.assertEqual(TEMPLATE.count("          - DemoPacks\n          - DemoDataset\n"), 1)                                   # shown in the Advanced group, before the old dropdown


if __name__ == "__main__": unittest.main()
