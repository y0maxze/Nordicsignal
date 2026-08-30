import unittest

import opportunity_walkforward_gate_runtime as gate_runtime
import opportunity_walkforward_runtime as walkforward


def rows_for(horizon, count=40, fail_last_holdout=False, same_time=False):
    rows = []
    for index in range(count):
        bad = fail_last_holdout and index >= 30
        rows.append({
            "event_id": index + 1,
            "horizon_days": horizon,
            "observed_at": "2026-01-01T10:00:00+00:00" if same_time else f"2026-01-{(index // 2) + 1:02d}T{index % 2:02d}:00:00+00:00",
            "return_pct": -2.0 if bad else 2.0,
            "excess_return_pct": -1.0 if bad else 1.0,
        })
    return rows


class OpportunityWalkForwardTests(unittest.TestCase):
    def test_rows_are_sorted_chronologically_and_same_time_uses_event_id(self):
        rows = list(reversed(rows_for(5, 40, same_time=True)))
        ordered = walkforward._ordered_horizon_rows(rows, 5)
        self.assertEqual([row["event_id"] for row in ordered[:3]], [1, 2, 3])
        first = walkforward._horizon_report(rows, 5)["folds"][0]
        self.assertEqual(first["training"]["last_event_id"], 20)
        self.assertEqual(first["holdout"]["first_event_id"], 21)
        self.assertTrue(first["leakage_guard"]["training_ends_before_holdout_starts"])

    def test_thirty_observations_have_only_one_fold_and_cannot_pass(self):
        result = walkforward._horizon_report(rows_for(5, 30), 5)
        self.assertEqual(result["eligible_folds"], 1)
        self.assertEqual(result["passing_folds"], 1)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "COLLECTING_DATA")
        self.assertEqual(result["observations_needed_for_two_scheduled_folds"], 10)

    def test_two_strong_chronological_holdouts_pass_horizon(self):
        result = walkforward._horizon_report(rows_for(10, 40), 10)
        self.assertTrue(result["ready"])
        self.assertEqual(result["eligible_folds"], 2)
        self.assertEqual(result["passing_folds"], 2)
        self.assertEqual(result["holdout_pass_rate_pct"], 100.0)
        self.assertTrue(result["latest_eligible_holdout_pass"])

    def test_recent_holdout_failure_blocks_horizon_despite_old_success(self):
        result = walkforward._horizon_report(rows_for(20, 40, fail_last_holdout=True), 20)
        self.assertFalse(result["ready"])
        self.assertEqual(result["eligible_folds"], 2)
        self.assertEqual(result["passing_folds"], 1)
        self.assertFalse(result["latest_eligible_holdout_pass"])
        self.assertEqual(result["status"], "REVIEW")

    def test_gate_needs_two_of_three_horizons(self):
        rows = rows_for(5, 40) + rows_for(10, 40) + rows_for(20, 40, fail_last_holdout=True)
        result = walkforward.walkforward_gate(rows, (5, 10, 20))
        self.assertTrue(result["ready"])
        self.assertEqual(result["passing_horizons"], [5, 10])
        self.assertEqual(result["status"], "PASS")

    def test_learning_policy_changes_without_resetting_signal_model(self):
        previous = gate_runtime._BASE_IDENTITY()
        current = gate_runtime._current_identity()
        self.assertEqual(current["signal_model_id"], previous["signal_model_id"])
        self.assertNotEqual(current["learning_policy_id"], previous["learning_policy_id"])
        self.assertEqual(current["learning_policy_version"], gate_runtime.LEARNING_POLICY_VERSION)
        self.assertIn("chronological_walk_forward_policy", current["identity_scope"])


if __name__ == "__main__":
    unittest.main()
