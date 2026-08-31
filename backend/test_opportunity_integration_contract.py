import unittest
from unittest.mock import patch

import sitecustomize
import opportunity_confluence_runtime as opportunity
import opportunity_insider_policy_bridge_runtime as bridge
import opportunity_shadow_smart_money_runtime as shadow_smart


class OpportunityIntegrationContractTests(unittest.TestCase):
    def _row(self, person, value, role="", day="2026-08-30"):
        return {
            "person": person,
            "transaction_type": "buy",
            "transaction_value": value,
            "display_transaction_value": value,
            "trade_date": day,
            "shares": value / 10 if value else 0,
            "price": 10,
            "role": role,
        }

    def test_runtime_order_keeps_canonical_policy_before_tracking_and_shadow(self):
        order = list(sitecustomize.RUNTIME_MODULES)
        expected = [
            "insider_signal_v2_runtime",
            "insider_purchase_threshold_runtime",
            "insider_smart_money_runtime",
            "opportunity_confluence_runtime",
            "opportunity_insider_policy_bridge_runtime",
            "opportunity_tracking_runtime",
        ]
        indexes = [order.index(name) for name in expected]
        self.assertEqual(indexes, sorted(indexes))
        self.assertLess(order.index("opportunity_shadow_dataset_runtime"), order.index("opportunity_shadow_smart_money_runtime"))
        self.assertLess(order.index("opportunity_shadow_smart_money_runtime"), order.index("opportunity_shadow_quality_runtime"))

    def test_opportunity_uses_canonical_insider_policy_not_base_analyzer(self):
        self.assertIs(opportunity.analyze_insider, bridge.analyze_insider_policy)
        result = opportunity.analyze_insider({"items": [
            self._row("Tiny Buyer", 36_000, "Board Member"),
            self._row("Chief Buyer", 600_000, "CEO"),
        ]})
        signal = result["insider_signal_v2"]
        self.assertEqual(signal["buy_count"], 1)
        self.assertEqual(signal["independent_buyers"], 1)
        self.assertEqual(signal["ignored_small_buy_count"], 1)
        self.assertEqual(signal["buy_value_nok"], 600_000)
        self.assertEqual(signal["smart_money"]["meaningful_actors_500k_plus"], 1)
        self.assertEqual(signal["smart_money"]["senior_actors"], 1)

    def test_repeated_actor_never_becomes_independent_cluster(self):
        result = opportunity.analyze_insider({"items": [
            self._row("Same Buyer", 300_000, "Board Member", "2026-08-29"),
            self._row("Same Buyer", 300_000, "Board Member", "2026-08-30"),
        ]})
        signal = result["insider_signal_v2"]
        self.assertEqual(signal["independent_buyers"], 1)
        self.assertEqual(signal["smart_money"]["independent_qualified_actors"], 1)
        self.assertEqual(signal["smart_money"]["repeated_same_actor_trades"], 1)

    def test_smart_money_metadata_flows_to_opportunity_components_without_score_effect(self):
        strict = opportunity.analyze_insider({"items": [self._row("Chief Buyer", 750_000, "CEO")]})
        signal = strict["insider_signal_v2"]
        result = opportunity.calculate_opportunity({
            "score": 55,
            "regime": "BOTTOMING",
            "metrics": {"bullish_volume_ratio": 1.1},
        }, signal)
        components = result["components"]
        self.assertEqual(components["smart_money_quality"], signal["smart_money"]["quality"])
        self.assertEqual(components["meaningful_actors_500k_plus"], 1)
        self.assertEqual(components["senior_actors"], 1)
        self.assertEqual(result["score_effect"], 0)

    def test_shadow_sidecar_extracts_same_opportunity_metadata(self):
        result = {
            "opportunity": {"components": {
                "smart_money_quality": "HIGH",
                "smart_money_points": 6,
                "meaningful_actors_500k_plus": 2,
                "million_plus_actors": 1,
                "senior_actors": 2,
                "role_adjusted_qualified_value_nok": 2_350_000,
            }}
        }
        smart = shadow_smart._smart_from_result(result)
        self.assertEqual(smart["quality"], "HIGH")
        self.assertEqual(smart["points"], 6)
        self.assertEqual(smart["meaningful"], 2)
        self.assertEqual(smart["million"], 1)
        self.assertEqual(smart["senior"], 2)
        self.assertEqual(smart["role_adjusted"], 2_350_000)

    def test_sidecar_is_written_only_with_new_first_observed_snapshot(self):
        result = {"opportunity": {"components": {"smart_money_quality": "HIGH"}}}
        with patch.object(shadow_smart, "_BASE_CAPTURE", return_value={"captured": True, "snapshot_id": 7}), \
             patch.object(shadow_smart, "_persist", return_value=True) as persist:
            shadow_smart.capture_snapshot_with_smart_money(result)
            persist.assert_called_once()
        with patch.object(shadow_smart, "_BASE_CAPTURE", return_value={"captured": False, "reason": "already_captured", "snapshot_id": 7}), \
             patch.object(shadow_smart, "_persist") as persist:
            shadow_smart.capture_snapshot_with_smart_money(result)
            persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
