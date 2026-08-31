import unittest

import opportunity_change_control_runtime as control


class OpportunityChangeControlTests(unittest.TestCase):
    def test_current_live_policy_and_bridge_match_reviewed_contracts(self):
        base = control._base_source()
        bridge = control._bridge_source()
        base_checks = control._source_invariants(base, control.REQUIRED_SOURCE_CONTRACT)
        bridge_checks = control._source_invariants(bridge, control.REQUIRED_BRIDGE_CONTRACT)
        self.assertTrue(all(base_checks.values()), [token for token, ok in base_checks.items() if not ok])
        self.assertTrue(all(bridge_checks.values()), [token for token, ok in bridge_checks.items() if not ok])
        status = control.change_control_status()
        self.assertEqual(status["status"], "PASS")
        self.assertTrue(status["live_policy_contract_ok"])
        self.assertTrue(status["canonical_insider_bridge_contract_ok"])
        self.assertFalse(status["research_can_modify_live_policy"])
        self.assertFalse(status["automatic_threshold_changes"])
        self.assertEqual(status["main_score_effect"], 0)

    def test_removed_threshold_token_forces_review(self):
        source = control._base_source().replace("volume_ratio >= 1.5", "volume_ratio >= 1.4")
        checks = control._source_invariants(source, control.REQUIRED_SOURCE_CONTRACT)
        self.assertFalse(checks["volume_ratio >= 1.5"])
        self.assertFalse(all(checks.values()))

    def test_removed_score_effect_zero_forces_review(self):
        source = control._base_source().replace('"score_effect": 0', '"score_effect": 5')
        checks = control._source_invariants(source, control.REQUIRED_SOURCE_CONTRACT)
        self.assertFalse(checks['"score_effect": 0'])

    def test_removed_canonical_purchase_policy_forces_bridge_review(self):
        source = control._bridge_source().replace("purchase_policy.strict_analyze", "legacy_analyze")
        checks = control._source_invariants(source, control.REQUIRED_BRIDGE_CONTRACT)
        self.assertFalse(checks["purchase_policy.strict_analyze"])

    def test_source_hash_is_deterministic_and_change_sensitive(self):
        source = control._base_source()
        self.assertEqual(control._source_sha256(source), control._source_sha256(source))
        self.assertNotEqual(control._source_sha256(source), control._source_sha256(source + "\n# changed"))


if __name__ == "__main__":
    unittest.main()
