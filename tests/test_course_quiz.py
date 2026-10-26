from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from course_quiz import grade  # noqa: E402

QUESTIONS = [
    {'id': 'q1', 'prompt': 'p1', 'options': ['a', 'b'], 'answer': 1, 'explain': 'e1'},
    {'id': 'q2', 'prompt': 'p2', 'options': ['a', 'b', 'c'], 'answer': 0, 'explain': 'e2'},
]


class TestGrade(unittest.TestCase):
    def test_all_correct(self):
        result = grade(QUESTIONS, {'q1': 1, 'q2': 0})
        self.assertEqual((result['correct'], result['total']), (2, 2))
        self.assertTrue(all(item['correct'] for item in result['items']))

    def test_partial(self):
        result = grade(QUESTIONS, {'q1': 0, 'q2': 0})
        self.assertEqual(result['correct'], 1)
        self.assertEqual([item['correct'] for item in result['items']], [False, True])
        self.assertEqual(result['items'][0]['explain'], 'e1')

    def test_unanswered(self):
        result = grade(QUESTIONS, {'q1': None})
        self.assertEqual(result['correct'], 0)
        self.assertEqual([item['chosen'] for item in result['items']], [None, None])
        self.assertFalse(any(item['correct'] for item in result['items']))


if __name__ == '__main__':
    unittest.main()
