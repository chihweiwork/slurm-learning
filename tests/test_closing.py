import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import closing  # noqa: E402
import course_progress  # noqa: E402
from closing import evaluate, load_runs  # noqa: E402

IDLE = [{'name': 'cpu01', 'state': ['IDLE'], 'reason': ''}, {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''}]


def clean(**overrides):
    data = {'queue': [], 'nodes': IDLE, 'accounts': ['lab', 'root'],
            'runs': [{'run_id': 'r1', 'acted': True, 'report': 'passed', 'cleaned': True}]}
    data.update(overrides)
    return data


def result(items, number):
    return next(i for i in items if i['項目'].startswith(f'{number} '))['結果']


class TestEvaluate(unittest.TestCase):
    def test_clean_state_has_no_warning(self):
        self.assertNotIn('⚠', [i['結果'] for i in evaluate(clean())])

    def test_own_active_job_warns_but_foreign_job_alone_does_not(self):
        own = {'job_id': '9', 'name': 'demo-x-holder', 'user': 'lab', 'state': 'RUNNING', 'reason': 'None'}
        foreign = {'job_id': '8', 'name': 'train', 'user': 'alice', 'state': 'RUNNING', 'reason': 'None'}
        self.assertEqual(result(evaluate(clean(queue=[own])), 1), '⚠')
        self.assertEqual(result(evaluate(clean(queue=[foreign])), 1), '✓')

    def test_drained_node_warns_with_ownership(self):
        for reason, phrase in (('course-c12345678', '你的維護'), ('admin-upgrade', '別人的維護')):
            nodes = [{'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': reason}]
            item = evaluate(clean(nodes=nodes))[1]
            self.assertEqual(item['結果'], '⚠')
            self.assertIn(phrase, item['說明'])

    def test_down_node_warns(self):
        nodes = [{'name': 'cpu01', 'state': ['DOWN', 'NOT_RESPONDING'], 'reason': 'Not responding'}]
        self.assertEqual(result(evaluate(clean(nodes=nodes)), 2), '⚠')

    def test_leftover_demo_account_warns(self):
        self.assertEqual(result(evaluate(clean(accounts=['lab', 'demo-abc'])), 3), '⚠')

    def test_query_failure_is_unknown_not_ok(self):
        items = evaluate(clean(queue=None, queue_error='timeout', nodes=None, accounts=None))
        self.assertEqual([result(items, n) for n in (1, 2, 3)], ['—', '—', '—'])

    def test_uncleaned_run_warns_and_empty_run_does_not(self):
        runs = [{'run_id': 'r1', 'acted': True, 'report': 'running', 'cleaned': False}]
        self.assertEqual(result(evaluate(clean(runs=runs)), 4), '⚠')
        empty = [{'run_id': 'r2', 'acted': False, 'report': 'running', 'cleaned': False}]
        self.assertEqual(result(evaluate(clean(runs=empty)), 4), '✓')

    def test_failed_report_warns_but_cleaned_unverified_is_info(self):
        failed = [{'run_id': 'r1', 'acted': True, 'report': 'failed', 'cleaned': True}]
        self.assertEqual(result(evaluate(clean(runs=failed)), 5), '⚠')
        unverified = [{'run_id': 'r1', 'acted': True, 'report': 'running', 'cleaned': True}]
        self.assertEqual(result(evaluate(clean(runs=unverified)), 5), '—')

    def test_chapter_without_demos_has_no_run_checks(self):
        # Chapters 00/01/03/10 have no demo runs: no "本章還沒有建立 run" rows that look like unfinished work.
        items = evaluate(clean(runs=None))
        self.assertEqual([i['項目'][0] for i in items], ['1', '2', '3'])
        self.assertNotIn('⚠', [i['結果'] for i in items])

    def test_demo_chapter_before_any_click_is_clean(self):
        untouched = [{'run_id': 'r1', 'acted': False, 'report': 'running', 'cleaned': False, 'verified': False}]
        self.assertEqual([result(evaluate(clean(runs=untouched)), n) for n in (4, 5)], ['✓', '✓'])


class TestLoaders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_dir(self, name, chapter, report, actions):
        directory = self.root / name
        (directory / 'actions').mkdir(parents=True)
        (directory / 'run.json').write_text(json.dumps({'chapter': chapter}))
        (directory / 'report.json').write_text(json.dumps(report))
        if actions:
            (directory / 'actions' / 'holder.json').write_text('{}')

    def test_load_runs_filters_chapter_and_reads_cleanup(self):
        self.run_dir('a', '05-csv', {'status': 'passed', 'cleanup_attempts': [{'errors': []}]}, True)
        self.run_dir('b', '05-csv', {'status': 'running', 'cleanup_attempts': [{'errors': ['x']}]}, True)
        self.run_dir('c', '05-csv', {'status': 'running'}, False)
        self.run_dir('d', '09-drain', {'status': 'passed'}, True)
        runs = {r['run_id']: r for r in load_runs('05', demos=self.root)}
        self.assertEqual(set(runs), {'a', 'b', 'c'})
        self.assertTrue(runs['a']['cleaned'])
        self.assertFalse(runs['b']['cleaned'])
        self.assertFalse(runs['c']['acted'])

    def test_course_owned_runs_only_include_current_and_retired_runs(self):
        # Old-course runs reuse chapter prefixes (old 10-drain vs new chapter 10); only runs a learning
        # record created (or retired via 重新開始示範) may appear in a chapter's closing checklist.
        self.run_dir('old', '02-submit', {'status': 'running'}, True)
        self.run_dir('current', '02-submit', {'status': 'passed'}, True)
        self.run_dir('retired', '02-submit', {'status': 'running'}, True)
        course = self.root / 'course'
        original = course_progress.COURSE
        course_progress.COURSE = course
        try:
            token = course_progress.start()
            course_progress.record(token, '02', 'runs', {'02-submit': 'current'})
            course_progress.record(token, '02', 'retired_runs', ['retired'])
            allowed = closing.course_run_ids()
        finally:
            course_progress.COURSE = original
        self.assertEqual({r['run_id'] for r in load_runs('02', demos=self.root, allowed=allowed)}, {'current', 'retired'})


if __name__ == '__main__':
    unittest.main()
