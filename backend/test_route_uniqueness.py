import json
import subprocess
import sys
import unittest


class RouteUniquenessTests(unittest.TestCase):
    def test_main_app_has_no_exact_duplicate_api_routes(self):
        code = r'''
import json, main
seen = set()
duplicates = []
for route in main.app.routes:
    path = getattr(route, 'path', '')
    if not path.startswith('/api/'):
        continue
    methods = tuple(sorted(getattr(route, 'methods', set()) or set()))
    key = (path, methods)
    if key in seen:
        duplicates.append({'path': path, 'methods': methods})
    seen.add(key)
print(json.dumps(duplicates))
'''
        proc = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)
        duplicates = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(duplicates, [], f'Exact duplicate API routes remain: {duplicates}')


if __name__ == '__main__':
    unittest.main()
