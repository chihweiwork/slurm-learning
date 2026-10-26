"""Regression: a manual refresh during an automatic one must not degrade the page.

Round 1: Dashboard cards turned STALE with "A snapshot refresh is already
running" when 15 s auto refresh and a manual refresh overlapped.
"""
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import notebook_queries  # noqa: E402


class SnapshotCoalescing(unittest.TestCase):
    def test_overlapping_refreshes_share_one_collection(self):
        calls = []
        started = threading.Event()

        def slow_collect():
            calls.append(threading.get_ident())
            started.set()
            time.sleep(0.3)
            return {'status': 'ok', 'observed_at': 'now', 'sources': {}, 'history': [], 'counts': {}}

        results = []
        with mock.patch.object(notebook_queries, '_collect_snapshot', slow_collect):
            leader = threading.Thread(target=lambda: results.append(notebook_queries.read_snapshot()))
            leader.start()
            started.wait(2)
            follower = notebook_queries.read_snapshot()
            leader.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(follower['status'], 'ok')
        self.assertTrue(follower['coalesced'])
        self.assertEqual(results[0]['status'], 'ok')

    def test_next_refresh_after_completion_queries_again(self):
        with mock.patch.object(notebook_queries, '_collect_snapshot',
                               side_effect=[{'status': 'ok', 'n': 1}, {'status': 'ok', 'n': 2}]):
            self.assertEqual(notebook_queries.read_snapshot()['n'], 1)
            self.assertEqual(notebook_queries.read_snapshot()['n'], 2)


if __name__ == '__main__':
    unittest.main()
