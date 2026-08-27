import unittest

import performance_runtime as perf


class PerformanceRuntimeTests(unittest.TestCase):
    def test_section_failures_do_not_drop_successful_sections(self):
        tasks = {
            'fast': lambda: {'ok': True},
            'broken': lambda: (_ for _ in ()).throw(RuntimeError('provider down')),
        }
        sections, errors, timings = perf._call_sections(tasks)
        self.assertEqual(sections['fast'], {'ok': True})
        self.assertIn('broken', errors)
        self.assertIn('fast', timings)
        self.assertIn('broken', timings)

    def test_route_stats_keep_average_and_errors(self):
        with perf._STATS_LOCK:
            perf._STATS.clear()
        perf._record('/api/example', 10.0, 200)
        perf._record('/api/example', 30.0, 500)
        with perf._STATS_LOCK:
            row = dict(perf._STATS['/api/example'])
        self.assertEqual(row['count'], 2)
        self.assertEqual(row['errors'], 1)
        self.assertEqual(row['avg_ms'], 20.0)
        self.assertEqual(row['max_ms'], 30.0)


if __name__ == '__main__':
    unittest.main()
