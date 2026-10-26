from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import course_progress  # noqa: E402


class TestProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(course_progress, 'COURSE', Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_start_load_list(self):
        self.assertEqual(course_progress.list_tokens(), [])
        first = course_progress.start()
        self.assertRegex(first, r'\Ac[0-9a-f]{8}\Z')
        progress = course_progress.load(first)
        self.assertEqual((progress['token'], progress['chapters']), (first, {}))
        second = course_progress.start()
        course_progress.save(first, dict(progress, created='2000-01-01T00:00:00+00:00'))
        self.assertEqual(course_progress.list_tokens(), [second, first])
        self.assertEqual(course_progress.container_dir(first), f'/shared/course/{first}/')
        with self.assertRaises(ValueError):
            course_progress.load('../x')

    def test_record_task_quiz_status(self):
        token = course_progress.start()
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1']), '未開始')
        course_progress.record(token, '02', 'note', 1)
        self.assertEqual(course_progress.load(token)['chapters']['02']['note'], 1)
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1']), '進行中')
        course_progress.mark_task(token, '02', 't1', {'passed': True, 'items': [{'項目': 'x'}]})
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1']), '進行中')
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1'], has_quiz=False), '完成')
        course_progress.mark_quiz(token, '02', {'correct': 2, 'total': 3})
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1']), '進行中')
        course_progress.mark_quiz(token, '02', {'correct': 3, 'total': 3})
        progress = course_progress.load(token)
        self.assertEqual(progress['chapters']['02']['tasks']['t1']['items'], [{'項目': 'x'}])
        self.assertEqual(course_progress.chapter_status(progress, '02', ['t1']), '完成')
        course_progress.mark_task(token, '02', 't2', {'passed': False, 'items': []})
        self.assertEqual(course_progress.chapter_status(course_progress.load(token), '02', ['t1', 't2']), '進行中')
        self.assertEqual(course_progress.chapter_status(None, '02', []), '未開始')

    def test_later_failed_check_does_not_revoke_a_pass(self):
        token = course_progress.start()
        course_progress.mark_task(token, '09', 't1-drain', {'passed': True, 'items': [{'結果': '✓'}]})
        course_progress.mark_task(token, '09', 't1-drain', {'passed': False, 'items': [{'結果': '✗'}]})
        entry = course_progress.load(token)['chapters']['09']['tasks']['t1-drain']
        self.assertTrue(entry['passed'])
        self.assertFalse(entry['last_check']['passed'])


if __name__ == '__main__':
    unittest.main()
