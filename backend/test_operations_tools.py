import base64
import unittest

import backup_verify
import generate_vapid_keys


def _decode(value):
    padding = '=' * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


class OperationsToolsTests(unittest.TestCase):
    def test_vapid_pair_has_valid_p256_shapes(self):
        pair = generate_vapid_keys.generate_vapid_pair()
        public = _decode(pair['public_key'])
        private = _decode(pair['private_key'])
        self.assertEqual(len(public), 65)
        self.assertEqual(public[0], 4)
        self.assertEqual(len(private), 32)
        self.assertNotIn('=', pair['public_key'])
        self.assertNotIn('=', pair['private_key'])

    def test_vapid_generation_is_not_deterministic(self):
        first = generate_vapid_keys.generate_vapid_pair()
        second = generate_vapid_keys.generate_vapid_pair()
        self.assertNotEqual(first['private_key'], second['private_key'])
        self.assertNotEqual(first['public_key'], second['public_key'])

    def test_backup_compare_accepts_matching_counts(self):
        source = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        restored = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        result = backup_verify.compare_snapshots(source, restored)
        self.assertTrue(result['ok'])
        self.assertEqual(result['missing_tables'], [])
        self.assertEqual(result['count_mismatches'], [])

    def test_backup_compare_rejects_missing_or_mismatched_tables(self):
        source = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        restored = {'tables': {'stocks': {'rows': 23}}, 'count_fingerprint': 'b'}
        result = backup_verify.compare_snapshots(source, restored)
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing_tables'], ['scores'])
        self.assertEqual(result['count_mismatches'][0]['table'], 'stocks')


if __name__ == '__main__':
    unittest.main()
