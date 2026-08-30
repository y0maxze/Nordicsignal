import unittest

import opportunity_change_control_runtime as control


class OpportunityChangeControlTests(unittest.TestCase):
    def test_current_live_policy_matches_reviewed_contract(self):
        source = control._source()
        checks = control._source_invariants(source)
        self.assertTrue(all(checks.values()), [token for token, ok in checks.items() if not ok])
        status = control.change_control_status()
        self.assertEqual(status["status"], "PASS")
        self.assertTrue(status["live_policy_contract_ok"])
        self.assertFalse(status["research_can_modify_live_policy"])
        self.assertFalse(status["automatic_threshold_changes"])
        self.assertEqual(status["main_score_effect"], 0)

    def test_removed_threshold_token_forces_review(self):
        source = control._source().replace("volume_ratio >= 1.5", "volume_ratio >= 1.4")
        checks = control._source_invariants(source)
        self.assertFalse(checks["volume_ratio >= 1.5"])
        self.assertFalse(all(checks.values()))

    def test_removed_score_effect_zero_forces_review(self):
        source = control._source().replace('"score_effect": 0', '"score_effect": 5')
        checks = control._source_invariants(source)
        self.assertFalse(checks['"score_effect": 0'])

    def test_source_hash_is_deterministic_and_change_sensitive(self):
        source = control._source()
        self.assertEqual(control._source_sha256(source), control._source_sha256(source))
        self.assertNotEqual(control._source_sha256(source), control._source_sha256(source + "\n# changed"))


if __name__ == "__main__":
    unittest.main()
