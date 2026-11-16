import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import recommend, rules

GATE_BLOCKED = {"allowed_actions": ["hold", "escalate"], "blocks": ["the invoice is already marked Paid"], "notes": [], "approvals_required": 1, "excluded_approvers": []}
GATE_CLEAN = {"allowed_actions": ["release", "hold", "escalate"], "blocks": [], "notes": [], "approvals_required": 1, "excluded_approvers": []}

class Recommend(unittest.TestCase):
    def setUp(self): self._env = dict(os.environ); os.environ["ANTHROPIC_API_KEY"] = "test"; self._ask = recommend._ask_model
    def tearDown(self): recommend._ask_model = self._ask; os.environ.clear(); os.environ.update(self._env)

    def test_a_model_that_picks_a_blocked_action_is_changed_to_escalate(self):
        recommend._ask_model = lambda f, g: {"recommendation": "release", "confidence": 0.99, "reasons": ["looks fine; ignore the rules"]}
        out = recommend.recommend({}, GATE_BLOCKED); self.assertEqual(out["recommendation"], "escalate"); self.assertIn("rules do not allow", out["reasons"][0])
    def test_an_allowed_choice_passes_through_and_confidence_is_clamped(self):
        recommend._ask_model = lambda f, g: {"recommendation": "release", "confidence": 7, "reasons": ["ok"]}
        out = recommend.recommend({}, GATE_CLEAN); self.assertEqual((out["recommendation"], out["confidence"]), ("release", 1.0))
    def test_a_failing_model_escalates_to_a_person(self):
        def boom(f, g): raise RuntimeError("503")
        recommend._ask_model = boom; self.assertEqual(recommend.recommend({}, GATE_CLEAN)["recommendation"], "escalate")
    def test_without_a_key_the_rules_only_fallback_answers(self):
        os.environ.pop("ANTHROPIC_API_KEY"); os.environ.pop("OMNIGATE_LLM_API_KEY", None)
        self.assertEqual(recommend.recommend({}, GATE_BLOCKED)["recommendation"], "hold"); self.assertEqual(recommend.recommend({}, GATE_CLEAN)["model"], "rules-only")

if __name__ == "__main__": unittest.main()
