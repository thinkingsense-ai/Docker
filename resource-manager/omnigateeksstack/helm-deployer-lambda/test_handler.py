"""python3 -m unittest discover -s resource-manager/omnigateeksstack/helm-deployer-lambda   (boto3 is stubbed: only the pack choice is tested)"""
import os, sys, types, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
for name in ("boto3", "botocore", "botocore.exceptions", "botocore.session", "botocore.signers"):
    m = types.ModuleType(name); sys.modules.setdefault(name, m)
sys.modules["botocore.exceptions"].ClientError = Exception; sys.modules["botocore.signers"].RequestSigner = object
import handler


class T(unittest.TestCase):
    def test_nothing_chosen_means_the_single_dataset_rules(self):
        for raw in (None, "", [""], [], [" "], ["", ""]): self.assertIsNone(handler.pack_selection(raw), raw)

    def test_a_cloudformation_list_becomes_the_charts_list_syntax(self):
        self.assertEqual(handler.pack_selection(["bom", "treasury"]), "{bom,treasury}")
        self.assertEqual(handler.pack_selection(["bom"]), "{bom}")

    def test_a_plain_comma_separated_string_and_stray_spaces_are_accepted(self):
        self.assertEqual(handler.pack_selection("bom, treasury"), "{bom,treasury}"); self.assertEqual(handler.pack_selection([" bom ", "treasury "]), "{bom,treasury}")

    def test_repeats_are_dropped_and_order_is_kept(self):
        self.assertEqual(handler.pack_selection(["treasury", "bom", "treasury"]), "{treasury,bom}")

    def test_an_unknown_pack_fails_with_the_list_of_packs(self):
        with self.assertRaises(ValueError) as c: handler.pack_selection(["bom", "nope", "also-no"])
        self.assertIn("'nope'", str(c.exception)); self.assertIn("'also-no'", str(c.exception)); self.assertIn("supply-chain", str(c.exception))
        with self.assertRaises(ValueError): handler.pack_selection(["all-packs"])          # a dataset name is not a pack

    def test_smithsonian_needs_all_six(self):
        for sel in (["smithsonian"], ["bom", "smithsonian"], ["supply-chain", "it-risk", "bom", "treasury", "smithsonian"]):
            with self.assertRaises(ValueError, msg=sel): handler.pack_selection(sel)
        self.assertEqual(handler.pack_selection(list(handler.KNOWN_PACKS)), "{" + ",".join(handler.KNOWN_PACKS) + "}")
        self.assertEqual(handler.pack_selection(["manufacturing", "it-risk", "smithsonian", "bom", "treasury"]).count(","), 4)       # manufacturing brings supply-chain along: all six

    def test_the_known_packs_are_the_charts_packs(self):
        import json
        o = json.load(open(os.path.join(HERE, "..", "..", "..", "packs", "deploy-options.json")))
        self.assertEqual(sorted(handler.KNOWN_PACKS), sorted(p["id"] for p in o["packs"]))

    def test_agency_off_changes_nothing(self):
        self.assertEqual(handler.agency_values({}, None, "supply-chain"), {})
        self.assertEqual(handler.agency_values({"InstallAgency": "false"}, "{bom}", "supply-chain"), {})

    def test_agency_adds_its_pack_to_the_choice(self):
        on = {"InstallAgency": "true"}
        self.assertEqual(handler.agency_values(on, None, "supply-chain"), {"agency.enabled": "true", "demoDatasets": "{supply-chain,agency-risk}"})
        self.assertEqual(handler.agency_values(on, "{bom,treasury}", "supply-chain")["demoDatasets"], "{bom,treasury,agency-risk}")
        self.assertEqual(handler.agency_values(on, None, "all-packs")["demoDatasets"], "{" + ",".join(handler.SIX_PACKS) + ",agency-risk}")
        self.assertEqual(handler.agency_values(on, "{it-risk,agency-risk}", "x")["demoDatasets"], "{it-risk,agency-risk}")

    def test_agency_workflows_need_agency(self):
        self.assertEqual(handler.agency_values({"InstallAgency": "true", "AgencyWorkflows": "true"}, None, "it-risk")["agency.workflows.enabled"], "true")
        with self.assertRaises(ValueError): handler.agency_values({"AgencyWorkflows": "true"}, None, "it-risk")

    def test_secret_values_are_redacted_from_an_error_message(self):
        a = ["upgrade", "--set", "omnigate.llmApiKey=sk-ant-SECRET", "--set", "omnigate.adminApiToken=tok", "--set", "omnigate.appUsers=demo:hash::", "--set", "demoDataset=it-risk",
             "--set-file", "omnigate.license=/tmp/omnigate-license", "--set", "tls.httpsOnly=true"]
        r = " ".join(handler.redact_args(a))
        for secret in ("sk-ant-SECRET", "=tok", "demo:hash", "/tmp/omnigate-license"): self.assertNotIn(secret, r)
        for kept in ("demoDataset=it-risk", "tls.httpsOnly=true", "--set-file"): self.assertIn(kept, r)

    def test_agency_image_override(self):
        self.assertEqual(handler.agency_values({"InstallAgency": "true", "AgencyImage": " 123.dkr.ecr.us-east-1.amazonaws.com/agency:x "}, None, "it-risk")["agency.image"], "123.dkr.ecr.us-east-1.amazonaws.com/agency:x")
        self.assertNotIn("agency.image", handler.agency_values({"InstallAgency": "true", "AgencyImage": ""}, None, "it-risk"))


if __name__ == "__main__": unittest.main()
