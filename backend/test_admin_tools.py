import base64
import unittest

from cryptography.hazmat.primitives.asymmetric import ec

import backup_verify
import generate_vapid_keys


def _decode(value):
    padding = '=' * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


class VapidGeneratorTests(unittest.TestCase):
    def test_generated_pair_is_valid_p256_raw_material(self):
        pair = generate_vapid_keys.generate_vapid_pair()
        private_raw = _decode(pair['private_key'])
        public_raw = _decode(pair['public_key'])
        self.assertEqual(len(private_raw), 32)
        self.assertEqual(len(public_raw), 65)
        self.assertEqual(public_raw[0], 4)
        value = int.from_bytes(private_raw, 'big')
        derived = ec.derive_private_key(value, ec.SECP256R1())
        numbers = derived.public_key().public_numbers()
        expected = b'\x04' + numbers.x.to_bytes(32, 'big') + numbers.y.to_bytes(32, 'big')
        self.assertEqual(public_raw, expected)


class BackupVerifyTests(unittest.TestCase):
    def test_equal_snapshots_are_ok(self):
        source = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        restored = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        result = backup_verify.compare_snapshots(source, restored)
        self.assertTrue(result['ok'])
        self.assertEqual(result['count_mismatches'], [])

    def test_missing_or_changed_table_fails(self):
        source = {'tables': {'stocks': {'rows': 24}, 'scores': {'rows': 100}}, 'count_fingerprint': 'a'}
        restored = {'tables': {'stocks': {'rows': 23}}, 'count_fingerprint': 'b'}
        result = backup_verify.compare_snapshots(source, restored)
        self.assertFalse(result['ok'])
        self.assertEqual(result['missing_tables'], ['scores'])
        self.assertEqual(result['count_mismatches'][0]['table'], 'stocks')


if __name__ == '__main__':
    unittest.main()
