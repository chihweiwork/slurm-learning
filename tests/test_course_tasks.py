from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from course_jobs import parse_sacct  # noqa: E402
from course_tasks import (combine, grade_array, grade_command_used, grade_completed_job,  # noqa: E402
                          grade_dependency, grade_gpu_job, grade_state, submitted_ids)

DIR = '/shared/course/c12345678'
SACCT = f"""JobID|JobName|State|ExitCode|Elapsed|Timelimit|ReqMem|MaxRSS|NCPUS|ReqTRES|Partition|WorkDir|Submit|NodeList
123_0|course-array|COMPLETED|0:0|00:00:01|00:30:00|1G||1|billing=1,cpu=1,mem=1G,node=1|cpu|{DIR}|2026-10-24T10:00:00|cpu01
123_0.batch|batch|COMPLETED|0:0|00:00:01||||1|||||cpu01
123_1|course-array|COMPLETED|0:0|00:00:01|00:30:00|1G||1|billing=1,cpu=1,mem=1G,node=1|cpu|{DIR}|2026-10-24T10:00:00|cpu02
123_2|course-array|COMPLETED|0:0|00:00:01|00:30:00|1G||1|billing=1,cpu=1,mem=1G,node=1|cpu|{DIR}|2026-10-24T10:00:00|cpu01
127|wrap|COMPLETED|0:0|00:00:01|00:30:00|1G||1|billing=1,cpu=1,mem=1G,node=1|cpu|{DIR}|2026-10-24T10:01:00|cpu01
130|course-oom|FAILED|1:0|00:00:02|00:30:00|50M||1|billing=1,cpu=1,mem=50M,node=1|cpu|{DIR}|2026-10-24T10:02:00|cpu01
130.batch|batch|OUT_OF_MEMORY|0:125|00:00:02|||50M|1|||||cpu01
140|course-gpu|COMPLETED|0:0|00:00:03|00:30:00|512M||1|billing=1,cpu=1,gres/gpu=1,mem=512M,node=1|gpu|{DIR}|2026-10-24T10:03:00|gpu01
"""
ROWS = parse_sacct(SACCT)
ALLOCATIONS = [r for r in ROWS if '.' not in r['JobID']]


def entry(line, returncode=0, stdout=''):
    import shlex
    return {'at': '2026-10-24T10:00:00+00:00', 'command': line, 'argv': shlex.split(line), 'user': 'lab',
            'returncode': returncode, 'stdout': stdout, 'stderr': '', 'seconds': 0.1, 'denied': None}


class TestCommandUsed(unittest.TestCase):
    def test_basic_and_failure(self):
        self.assertTrue(grade_command_used([entry('sinfo')], 'sinfo')['passed'])
        self.assertFalse(grade_command_used([entry('sinfo', returncode=1)], 'sinfo')['passed'])
        self.assertFalse(grade_command_used([], 'sinfo')['passed'])

    def test_must_include_and_alternatives(self):
        transcript = [entry('squeue -u lab')]
        self.assertFalse(grade_command_used(transcript, 'squeue', must_include=['--me'])['passed'])
        self.assertTrue(grade_command_used(transcript, 'squeue', must_include=[('--me', '-u lab')])['passed'])

    def test_job_ids(self):
        transcript = [entry('sacct -j 1270')]
        self.assertFalse(grade_command_used(transcript, 'sacct', job_ids={'127'})['passed'])
        transcript.append(entry('sacct -j 127'))
        self.assertTrue(grade_command_used(transcript, 'sacct', job_ids={'127'})['passed'])


class TestGraders(unittest.TestCase):
    def test_completed_job(self):
        self.assertTrue(grade_completed_job(ALLOCATIONS)['passed'])
        self.assertTrue(grade_completed_job(ALLOCATIONS, partition='gpu', tres_contains='gres/gpu=1')['passed'])
        self.assertFalse(grade_completed_job(ALLOCATIONS, name_prefix='nope')['passed'])
        running = [dict(ALLOCATIONS[0], JobID='200', State='RUNNING')]
        self.assertTrue(grade_completed_job(running)['pending'])

    def test_array(self):
        self.assertTrue(grade_array(ALLOCATIONS)['passed'])
        self.assertFalse(grade_array([r for r in ALLOCATIONS if r['JobID'] != '123_2'])['passed'])

    def test_state(self):
        self.assertTrue(grade_state(ALLOCATIONS, ROWS, 'OUT_OF_MEMORY')['passed'])
        self.assertFalse(grade_state(ALLOCATIONS, ROWS, 'TIMEOUT')['passed'])
        self.assertFalse(grade_state([], ROWS, 'OUT_OF_MEMORY')['passed'])

    def test_gpu_job(self):
        self.assertTrue(grade_gpu_job(ALLOCATIONS, {'140': 'GPU 0: Tesla T4 (UUID: x)\n'})['passed'])
        self.assertFalse(grade_gpu_job(ALLOCATIONS, {'140': None})['passed'])
        self.assertFalse(grade_gpu_job([r for r in ALLOCATIONS if r['Partition'] != 'gpu'], {})['passed'])

    def test_dependency(self):
        ok = [entry('sbatch --dependency=afterok:123 --wrap "echo done"', stdout='Submitted batch job 127\n')]
        self.assertTrue(grade_dependency(ok, ALLOCATIONS)['passed'])
        short = [entry('sbatch -d afterok:123 --wrap "echo done"', stdout='Submitted batch job 127\n')]
        self.assertTrue(grade_dependency(short, ALLOCATIONS)['passed'])
        foreign = [entry('sbatch --dependency=afterok:999 --wrap "echo done"', stdout='Submitted batch job 127\n')]
        self.assertFalse(grade_dependency(foreign, ALLOCATIONS)['passed'])
        unknown = [entry('sbatch --dependency=afterok:123 --wrap "echo done"', stdout='Submitted batch job 555\n')]
        verdict = grade_dependency(unknown, ALLOCATIONS)
        self.assertFalse(verdict['passed'])
        self.assertTrue(verdict['pending'])
        self.assertFalse(grade_dependency([], ALLOCATIONS)['passed'])

    def test_combine_and_submitted_ids(self):
        good = grade_command_used([entry('sinfo')], 'sinfo')
        bad = grade_command_used([], 'squeue')
        self.assertTrue(combine(good, good)['passed'])
        self.assertFalse(combine(good, bad)['passed'])
        self.assertEqual(len(combine(good, bad)['items']), 2)
        refused = {'at': '2026-10-25T08:00:00+00:00', 'command': 'squeue | grep lab', 'argv': [], 'user': None,
                   'returncode': None, 'stdout': '', 'stderr': '', 'seconds': None, 'denied': '不支援管線'}
        transcript = [entry('sbatch x.sbatch', stdout='Submitted batch job 5\n'),
                      refused,  # a refused line has empty argv; it must not break the graders
                      entry('sbatch y.sbatch', returncode=1, stdout='Submitted batch job 6\n'),
                      entry('squeue', stdout='Submitted batch job 7\n'),
                      entry('sbatch z.sbatch', stdout='Submitted batch job 8\n')]
        self.assertEqual(submitted_ids(transcript), ['5', '8'])


if __name__ == '__main__':
    unittest.main()
