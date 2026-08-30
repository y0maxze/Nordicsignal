import unittest

import opportunity_research_provenance_runtime as provenance


class ResearchProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {"id":"a","reversal_min":75.0,"volume_min":1.5,"insider_positive_required":False},
            {"id":"b","reversal_min":70.0,"volume_min":1.35,"insider_positive_required":True},
        ]
        self.snapshots = [
            {"id":2,"ticker":"BBB","market_date":"2026-08-02","reversal_score":76.0,"volume_ratio":1.6,"insider_label":"POSITIVE"},
            {"id":1,"ticker":"AAA","market_date":"2026-08-01","reversal_score":80.0,"volume_ratio":2.0,"insider_label":"STRONG"},
        ]
        self.returns = [
            {"snapshot_id":2,"horizon_days":10,"return_pct":3.0,"excess_return_pct":1.0},
            {"snapshot_id":1,"horizon_days":5,"return_pct":2.0,"excess_return_pct":0.5},
        ]

    def test_dataset_fingerprint_is_order_independent(self):
        first = provenance.dataset_fingerprint(self.snapshots, self.returns)
        second = provenance.dataset_fingerprint(list(reversed(self.snapshots)), list(reversed(self.returns)))
        self.assertEqual(first, second)

    def test_changed_feature_changes_dataset_fingerprint(self):
        first = provenance.dataset_fingerprint(self.snapshots, self.returns)
        changed = [dict(row) for row in self.snapshots]
        changed[0]["volume_ratio"] = 1.7
        self.assertNotEqual(first, provenance.dataset_fingerprint(changed, self.returns))

    def test_changed_return_changes_dataset_fingerprint(self):
        first = provenance.dataset_fingerprint(self.snapshots, self.returns)
        changed = [dict(row) for row in self.returns]
        changed[0]["excess_return_pct"] = 1.1
        self.assertNotEqual(first, provenance.dataset_fingerprint(self.snapshots, changed))

    def test_changed_candidate_changes_candidate_fingerprint(self):
        first = provenance.candidate_set_fingerprint(self.candidates)
        changed = [dict(row) for row in self.candidates]
        changed[0]["reversal_min"] = 74.0
        self.assertNotEqual(first, provenance.candidate_set_fingerprint(changed))

    def test_open_provenance_is_reproducible_and_stable(self):
        args = ("model-1", self.candidates, self.snapshots, self.returns, "2026-08-20", "2026-08-21", 0.30, 40)
        first = provenance.open_provenance(*args)
        second = provenance.open_provenance(*args)
        self.assertTrue(first["reproducible"])
        self.assertEqual(first["report_fingerprint"], second["report_fingerprint"])
        self.assertEqual(first["dataset_fingerprint"], second["dataset_fingerprint"])

    def test_locked_provenance_never_claims_reproducibility(self):
        item = provenance.locked_provenance("model-1", self.candidates)
        self.assertFalse(item["reproducible"])
        self.assertIsNone(item["dataset_fingerprint"])
        self.assertIsNone(item["report_fingerprint"])
        self.assertIsNotNone(item["candidate_set_fingerprint"])


if __name__ == "__main__":
    unittest.main()
