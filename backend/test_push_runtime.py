import unittest

import push_runtime as push


class PushRuntimeTests(unittest.TestCase):
    def test_endpoint_hash_is_stable_and_non_reversible_shape(self):
        endpoint='https://push.example/subscription/abc'
        self.assertEqual(push._hash(endpoint), push._hash(endpoint))
        self.assertEqual(len(push._hash(endpoint)), 64)
        self.assertNotIn('subscription', push._hash(endpoint))

    def test_push_status_is_explicit_about_configuration(self):
        status=push.push_status()
        self.assertTrue(status['supported'])
        self.assertIn('delivery_ready', status)
        self.assertIn('public_key_configured', status)
        self.assertIn('private_key_configured', status)
        self.assertIn('backend_awake_required', status)


if __name__=='__main__':
    unittest.main()
