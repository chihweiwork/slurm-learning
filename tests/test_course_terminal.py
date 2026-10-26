from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from course_terminal import Denied, check, parse  # noqa: E402

TOKEN = 'c12345678'


def run(line, mode='user'):
    return check(TOKEN, parse(line), mode=mode)


class TestParse(unittest.TestCase):
    def test_rejects_shell_syntax(self):
        for line in ['squeue | grep lab', 'echo > x', 'squeue; sinfo', 'sinfo && squeue', 'cat $(ls)', 'ls `pwd`', '', '   ']:
            with self.subTest(line=line), self.assertRaises(Denied):
                parse(line)

    def test_quoted_metachar_allowed(self):
        self.assertEqual(parse('sbatch --wrap "a; b"'), ['sbatch', '--wrap', 'a; b'])


class TestCheck(unittest.TestCase):
    def test_allowed(self):
        cases = [
            ('scancel 123', 'user', ('lab', 10)),
            ('scancel 12_3', 'user', ('lab', 10)),
            ('sbatch /opt/lab/examples/cpu.sbatch', 'user', ('lab', 15)),
            ('sbatch --wrap "a; b"', 'user', ('lab', 15)),
            ('scontrol update NodeName=cpu02 State=DRAIN Reason=course-c12345678-x', 'ops', ('root', 15)),
            ('sacctmgr add account name=course-c12345678-a', 'accounting', ('root', 20)),
            ('sacctmgr show assoc', 'user', ('lab', 10)),
            ('sinfo', 'user', ('lab', 10)),
        ]
        for line, mode, expected in cases:
            with self.subTest(line=line, mode=mode):
                self.assertEqual(run(line, mode), expected)

    def test_denied(self):
        cases = [
            ('scancel -u lab', 'user'),
            ('scancel --me', 'user'),
            ('sbatch ../x.sbatch', 'user'),
            ('sbatch --chdir=/tmp x', 'user'),
            ('scontrol update NodeName=cpu02 State=DRAIN Reason=course-c12345678-x', 'user'),
            ('scontrol update NodeName=cpu02 State=DRAIN', 'ops'),
            ('scontrol update NodeName=cpu01 State=DRAIN Reason=course-c12345678-x', 'ops'),
            ('sacctmgr add account name=course-c12345678-a', 'user'),
            ('sacctmgr add account name=other', 'accounting'),
            ('rm job.py', 'user'),
            ('cat ../../etc/passwd', 'user'),
            ('srun --pty bash', 'user'),
        ]
        for line, mode in cases:
            with self.subTest(line=line, mode=mode), self.assertRaises(Denied):
                run(line, mode)


if __name__ == '__main__':
    unittest.main()
