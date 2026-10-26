"""Regression: chapter 10/11 waiting evidence must accept a real PENDING job.

The fixture is a real `scontrol --json show job` record of a waiter queued behind
an exclusive holder; backfill gave it an estimated future StartTime. Round 1
of learner feedback hit "waiter 曾執行" because that estimate was read as a start.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from lessons_lifecycle import _pending  # noqa: E402
from notebook_queries import _job  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'pending_waiter_estimated_start.json').read_text())


def observed(record, output=''):
    job = _job(record)
    receipt = {'step_id': 'waiter', 'job_id': job['job_id'], 'effect': 'submit', 'status': 'succeeded'}
    outputs = {job['job_id']: [{'status': 'ok', 'text': output}]} if output else {}
    return {'receipts': [receipt], 'jobs': {job['job_id']: {'status': 'observed', 'records': [job]}},
            'outputs': outputs}


class PendingEvidence(unittest.TestCase):
    def test_fixture_has_backfill_estimate(self):
        job = _job(FIXTURE)
        self.assertEqual(job['job_state'], ['PENDING'])
        self.assertIsNotNone(job['start_time'])
        self.assertGreater(job['start_time'], FIXTURE['submit_time']['number'])

    def test_estimated_start_is_still_waiting(self):
        rows = _pending(observed(FIXTURE), reasons={'Resources', 'Priority'})
        self.assertEqual([row['job_state'] for row in rows], [['PENDING']])

    def test_requeued_job_is_not_waiting_evidence(self):
        record = deepcopy(FIXTURE)
        record['restart_cnt'] = 1
        with self.assertRaisesRegex(AssertionError, 'requeue'):
            _pending(observed(record))

    def test_output_means_it_ran(self):
        with self.assertRaisesRegex(AssertionError, '已有輸出'):
            _pending(observed(FIXTURE, output='{"affinity": [0]}'))

    def test_unexpected_reason_is_rejected(self):
        record = deepcopy(FIXTURE)
        record['state_reason'] = 'Dependency'
        with self.assertRaisesRegex(AssertionError, '等待原因'):
            _pending(observed(record), reasons={'Resources', 'Priority'})


if __name__ == '__main__':
    unittest.main()
