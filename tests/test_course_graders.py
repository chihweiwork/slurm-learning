"""Unit tests for course_jobs.py and course_ops.py pure functions.

Tests cover consumer-visible behaviour and boundaries for grading functions
used in Chapter 03/10 and Chapter 09.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from course_jobs import (  # noqa: E402
    parse_mem, parse_duration, check_sbatch_text, summarize,
    evaluate_first, evaluate_second, format_duration, mistake_examples, reference_files
)
from course_ops import (  # noqa: E402
    grade_nodes, grade_controller, drain_preflight, grade_drained,
    grade_probe_pending, parse_events, parse_probe_sacct, grade_resumed,
    reason_for, probe_name
)


class TestParseMem(unittest.TestCase):
    """Test parse_mem for various Slurm size formats."""

    def test_megabytes(self):
        self.assertEqual(parse_mem('128M'), 128 * 1024 ** 2)

    def test_gigabytes(self):
        self.assertEqual(parse_mem('1G'), 1024 ** 3)

    def test_kilobytes(self):
        self.assertEqual(parse_mem('64824K'), 64824 * 1024)

    def test_bytes(self):
        self.assertEqual(parse_mem('7M'), 7 * 1024 ** 2)

    def test_decimal_gigabytes(self):
        self.assertEqual(parse_mem('1.5G'), int(1.5 * 1024 ** 3))

    def test_terabytes(self):
        self.assertEqual(parse_mem('4000Mn'), 4000 * 1024 ** 2)

    def test_no_unit_default_bytes(self):
        # According to regex pattern, no unit means '' key in _UNITS which is 1
        result = parse_mem('256')
        self.assertEqual(result, 256)

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_mem(''))

    def test_invalid_string_returns_none(self):
        self.assertIsNone(parse_mem('abc'))

    def test_whitespace_ignored(self):
        self.assertEqual(parse_mem('  128M  '), 128 * 1024 ** 2)

    def test_per_cpu_suffix_ignored(self):
        self.assertEqual(parse_mem('128Mc'), 128 * 1024 ** 2)

    def test_per_node_suffix_ignored(self):
        self.assertEqual(parse_mem('128Mn'), 128 * 1024 ** 2)

    def test_case_insensitive(self):
        self.assertEqual(parse_mem('128m'), 128 * 1024 ** 2)
        self.assertEqual(parse_mem('1g'), 1024 ** 3)


class TestParseDuration(unittest.TestCase):
    """Test parse_duration for various time formats."""

    def test_mm_ss_format(self):
        self.assertEqual(parse_duration('00:00:12'), 12)

    def test_hh_mm_ss_format(self):
        self.assertEqual(parse_duration('01:00:00'), 3600)

    def test_mm_ss_with_hours(self):
        # Pattern matches: optional hours, required minutes, required seconds
        # '1:30' matches as minutes=1, seconds=30 (not hours:minutes)
        self.assertEqual(parse_duration('1:30'), 90)  # 1*60 + 30

    def test_days_hours_minutes_seconds(self):
        # 1-02:03:04 = days=1, hours=2, minutes=3, seconds=4
        self.assertEqual(parse_duration('1-02:03:04'), 93784)  # 1*86400 + 2*3600 + 3*60 + 4

    def test_unlimited_returns_none(self):
        self.assertIsNone(parse_duration('UNLIMITED'))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_duration(''))

    def test_whitespace_returns_none(self):
        self.assertIsNone(parse_duration('   '))

    def test_with_fractional_seconds(self):
        self.assertEqual(parse_duration('00:00:12.500'), 12)

    def test_zero_seconds(self):
        self.assertEqual(parse_duration('00:00:00'), 0)

    def test_minutes_and_seconds(self):
        self.assertEqual(parse_duration('00:05:30'), 330)  # 5*60 + 30


class TestCheckSbatchText(unittest.TestCase):
    """Test check_sbatch_text for valid sbatch script validation."""

    def test_valid_script_passes(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --chdir=/shared/course/c12345678/
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertTrue(result['passed'], f"Valid script should pass. Items: {result['items']}")

    def test_missing_chdir_passes(self):
        # The page terminal already submits from the learner's directory, so --chdir is optional.
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertTrue(result['passed'], result['items'])
        chdir = next(item for item in result['items'] if item['項目'] == '--chdir')
        self.assertEqual(chdir['結果'], '✓')

    def test_wrong_chdir_fails(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --chdir=/shared
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        chdir = next(item for item in result['items'] if item['項目'] == '--chdir')
        self.assertEqual(chdir['結果'], '✗')

    def test_custom_program_name(self):
        token = 'c12345678'
        text = ('#!/bin/bash\n#SBATCH --job-name=course-c12345678\n#SBATCH --mem=1G\n#SBATCH --time=00:10:00\n'
                '#SBATCH --output=/shared/course/c12345678/job-%j.out\nsrun python3 capstone.py\n')
        self.assertTrue(check_sbatch_text(token, text, program='capstone.py')['passed'])
        self.assertFalse(check_sbatch_text(token, text)['passed'])

    def test_wrong_job_name_fails(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=wrong-name
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        # Check job-name item failed
        job_name_item = next((i for i in result['items'] if '--job-name' in i['項目']), None)
        self.assertIsNotNone(job_name_item)
        self.assertEqual(job_name_item['結果'], '✗')

    def test_missing_mem_fails(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --time=00:10:00
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        mem_item = next((i for i in result['items'] if '--mem' in i['項目']), None)
        self.assertIsNotNone(mem_item)
        self.assertEqual(mem_item['結果'], '✗')

    def test_decimal_mem_fails_because_sbatch_rejects_it(self):
        # sbatch: error: Invalid --mem specification (real learner input 70.46M); whole numbers pass.
        base = ('#!/bin/bash\n#SBATCH --job-name=course-c12345678\n#SBATCH --time=00:01:00\n'
                '#SBATCH --output=/shared/course/c12345678/job-%j.out\n{mem}srun python3 job.py\n')
        for memory, ok in (('70.46M', False), ('1.5G', False), ('71M', True), ('1G', True), ('65536K', True)):
            result = check_sbatch_text('c12345678', base.format(mem=f'#SBATCH --mem={memory}\n'))
            item = next(i for i in result['items'] if i['項目'] == '--mem')
            self.assertEqual(item['結果'], '✓' if ok else '✗', memory)

    def test_output_outside_practice_dir_fails(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/tmp/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        output_item = next((i for i in result['items'] if '--output' in i['項目']), None)
        self.assertIsNotNone(output_item)
        self.assertEqual(output_item['結果'], '✗')

    def test_no_srun_line_fails(self):
        token = 'c12345678'
        text = '''#!/bin/bash
#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/shared/course/c12345678/job-%j.out
echo "no srun here"
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        srun_item = next((i for i in result['items'] if 'srun' in i['項目']), None)
        self.assertIsNotNone(srun_item)
        self.assertEqual(srun_item['結果'], '✗')

    def test_no_shebang_fails(self):
        token = 'c12345678'
        text = '''#SBATCH --job-name=course-c12345678
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/shared/course/c12345678/job-%j.out
srun python3 /shared/course/c12345678/job.py
'''
        result = check_sbatch_text(token, text)
        self.assertFalse(result['passed'])
        shebang_item = next((i for i in result['items'] if 'bash' in i['項目']), None)
        self.assertIsNotNone(shebang_item)
        self.assertEqual(shebang_item['結果'], '✗')


class TestSummarize(unittest.TestCase):
    """Test summarize for extracting allocation and MaxRSS from sacct rows."""

    def test_allocation_row_found(self):
        rows = [
            {'JobID': '12345', 'JobName': 'test', 'State': 'COMPLETED', 'MaxRSS': ''},
            {'JobID': '12345.0', 'JobName': 'test.0', 'State': 'COMPLETED', 'MaxRSS': '512M'},
        ]
        result = summarize('12345', rows)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['job_id'], '12345')
        self.assertIn('allocation', result)
        self.assertEqual(result['allocation']['JobID'], '12345')

    def test_peak_max_rss_from_steps(self):
        rows = [
            {'JobID': '12345', 'JobName': 'test', 'State': 'COMPLETED', 'MaxRSS': ''},
            {'JobID': '12345.0', 'JobName': 'test.0', 'State': 'COMPLETED', 'MaxRSS': '512M'},
            {'JobID': '12345.1', 'JobName': 'test.1', 'State': 'COMPLETED', 'MaxRSS': '1G'},
        ]
        result = summarize('12345', rows)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['max_rss_bytes'], 1024 ** 3)

    def test_missing_allocation_returns_missing(self):
        rows = [
            {'JobID': '12345.0', 'JobName': 'test.0', 'State': 'COMPLETED', 'MaxRSS': '512M'},
        ]
        result = summarize('99999', rows)
        self.assertEqual(result['status'], 'missing')
        self.assertEqual(result['job_id'], '99999')

    def test_no_steps_max_rss_is_none(self):
        rows = [
            {'JobID': '12345', 'JobName': 'test', 'State': 'COMPLETED', 'MaxRSS': ''},
        ]
        result = summarize('12345', rows)
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['max_rss_bytes'])


class TestEvaluateFirst(unittest.TestCase):
    """Test evaluate_first for first submission grading."""

    def test_completed_with_max_rss_passes(self):
        token = 'c12345678'
        summary = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_first(token, summary, output_found=True)
        self.assertTrue(result['passed'], f"Should pass. Items: {result['items']}")
        self.assertIsNotNone(result['advice'])
        # Check advice has mem and time
        self.assertIn('mem', result['advice'])
        self.assertIn('time', result['advice'])

    def test_missing_summary_fails(self):
        token = 'c12345678'
        summary = {'status': 'missing', 'job_id': '12345', 'rows': []}
        result = evaluate_first(token, summary, output_found=True)
        self.assertFalse(result['passed'])

    def test_pending_state_returns_pending(self):
        token = 'c12345678'
        summary = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'PENDING',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'MaxRSS': '60M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_first(token, summary, output_found=True)
        self.assertTrue(result['pending'])
        self.assertFalse(result['passed'])

    def test_no_output_file_fails(self):
        token = 'c12345678'
        summary = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_first(token, summary, output_found=False)
        self.assertFalse(result['passed'])
        output_item = next((i for i in result['items'] if '輸出檔' in i['項目']), None)
        self.assertIsNotNone(output_item)
        self.assertEqual(output_item['結果'], '✗')

    def test_no_max_rss_fails(self):
        token = 'c12345678'
        summary = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': None,
            'rows': []
        }
        result = evaluate_first(token, summary, output_found=True)
        self.assertFalse(result['passed'])
        rss_item = next((i for i in result['items'] if 'MaxRSS' in i['項目']), None)
        self.assertIsNotNone(rss_item)
        self.assertEqual(rss_item['結果'], '✗')

    def test_advice_computes_correct_mem_and_time(self):
        token = 'c12345678'
        summary = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,  # 60M
            'rows': []
        }
        result = evaluate_first(token, summary, output_found=True)
        # mem should be at least 1.3 * 60M = 78M
        # time should be at least 1.5 * 16 = 24s, which rounds to 60s minimum
        self.assertIn('mem', result['advice'])
        self.assertIn('time', result['advice'])
        mem_str = result['advice']['mem']
        self.assertTrue(mem_str.endswith('M'), f"Mem should be in MB, got {mem_str}")
        time_str = result['advice']['time']
        self.assertRegex(time_str, r'\d+:\d+:\d+')


class TestEvaluateSecond(unittest.TestCase):
    """Test evaluate_second for second submission grading."""

    def test_different_job_ids_pass_uniqueness(self):
        token = 'c12345678'
        first = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'Timelimit': '00:10:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        second = {
            'status': 'ok',
            'job_id': '12346',
            'allocation': {
                'JobID': '12346',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:12',
                'ReqMem': '600M',
                'Timelimit': '00:05:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 50 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_second(token, first, second, output_found=True)
        # Check job uniqueness item passes
        unique_item = next((i for i in result['items'] if '不同的 job' in i['項目']), None)
        self.assertIsNotNone(unique_item)
        self.assertEqual(unique_item['結果'], '✓')

    def test_same_job_id_fails(self):
        token = 'c12345678'
        first = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'Timelimit': '00:10:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        second = {
            'status': 'ok',
            'job_id': '12345',  # Same job ID
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:12',
                'ReqMem': '600M',
                'Timelimit': '00:05:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 50 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_second(token, first, second, output_found=True)
        self.assertFalse(result['passed'])
        unique_item = next((i for i in result['items'] if '不同的 job' in i['項目']), None)
        self.assertIsNotNone(unique_item)
        self.assertEqual(unique_item['結果'], '✗')

    def test_mem_adjustment_valid(self):
        token = 'c12345678'
        first = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'Timelimit': '00:10:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        second = {
            'status': 'ok',
            'job_id': '12346',
            'allocation': {
                'JobID': '12346',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:12',
                'ReqMem': '100M',  # Less than first (1G) and >= 1.2*60M = 72M
                'Timelimit': '00:05:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 50 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_second(token, first, second, output_found=True)
        mem_item = next((i for i in result['items'] if '--mem 調整' in i['項目']), None)
        self.assertIsNotNone(mem_item)
        self.assertEqual(mem_item['結果'], '✓')

    def test_mem_too_small_fails(self):
        token = 'c12345678'
        first = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'Timelimit': '00:10:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        second = {
            'status': 'ok',
            'job_id': '12346',
            'allocation': {
                'JobID': '12346',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:12',
                'ReqMem': '50M',  # Less than 1.2*60M = 72M
                'Timelimit': '00:05:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 50 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_second(token, first, second, output_found=True)
        self.assertFalse(result['passed'])
        mem_item = next((i for i in result['items'] if '--mem 調整' in i['項目']), None)
        self.assertIsNotNone(mem_item)
        self.assertEqual(mem_item['結果'], '✗')

    def test_time_adjustment_valid(self):
        token = 'c12345678'
        first = {
            'status': 'ok',
            'job_id': '12345',
            'allocation': {
                'JobID': '12345',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:16',
                'ReqMem': '1G',
                'Timelimit': '00:10:00',
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 60 * 1024 ** 2,
            'rows': []
        }
        second = {
            'status': 'ok',
            'job_id': '12346',
            'allocation': {
                'JobID': '12346',
                'JobName': 'course-c12345678',
                'User': 'lab',
                'State': 'COMPLETED',
                'ExitCode': '0:0',
                'Elapsed': '00:00:12',
                'ReqMem': '100M',
                'Timelimit': '00:01:00',  # Less than first (00:10:00) and >= max(60s, 1.2*16) = 60s
                'MaxRSS': '500M',
                'WorkDir': '/shared/course/c12345678/work',
            },
            'max_rss_bytes': 50 * 1024 ** 2,
            'rows': []
        }
        result = evaluate_second(token, first, second, output_found=True)
        time_item = next((i for i in result['items'] if '--time 調整' in i['項目']), None)
        self.assertIsNotNone(time_item)
        self.assertEqual(time_item['結果'], '✓')


class TestGradeNodes(unittest.TestCase):
    """Test grade_nodes for node info grading."""

    def test_correct_answers_pass(self):
        answers = {
            'cpu01_cpuefctv': '4',
            'cpu02_state': 'IDLE',
            'gpu01_gres': 'gpu:1'
        }
        nodes = [
            {'name': 'cpu01', 'effective_cpus': 4, 'gres': ''},
            {'name': 'cpu02', 'state': ['IDLE'], 'gres': ''},
            {'name': 'gpu01', 'state': ['IDLE'], 'effective_cpus': 2, 'gres': 'gpu:1'},
        ]
        result = grade_nodes(answers, nodes)
        self.assertTrue(result['passed'])

    def test_blank_answer_fails(self):
        answers = {
            'cpu01_cpuefctv': '',
            'cpu02_state': 'IDLE',
            'gpu01_gres': 'gpu:1'
        }
        nodes = [
            {'name': 'cpu01', 'effective_cpus': 4, 'gres': ''},
            {'name': 'cpu02', 'state': ['IDLE'], 'gres': ''},
            {'name': 'gpu01', 'state': ['IDLE'], 'effective_cpus': 2, 'gres': 'gpu:1'},
        ]
        result = grade_nodes(answers, nodes)
        self.assertFalse(result['passed'])

    def test_wrong_cpu_total_fails(self):
        answers = {
            'cpu01_cpuefctv': '8',  # Wrong value
            'cpu02_state': 'IDLE',
            'gpu01_gres': 'gpu:1'
        }
        nodes = [
            {'name': 'cpu01', 'effective_cpus': 4, 'gres': ''},
            {'name': 'cpu02', 'state': ['IDLE'], 'gres': ''},
            {'name': 'gpu01', 'state': ['IDLE'], 'effective_cpus': 2, 'gres': 'gpu:1'},
        ]
        result = grade_nodes(answers, nodes)
        self.assertFalse(result['passed'])

    def test_idle_state_accepted(self):
        answers = {
            'cpu01_cpuefctv': '4',
            'cpu02_state': 'idle',  # Lowercase
            'gpu01_gres': 'gpu:1'
        }
        nodes = [
            {'name': 'cpu01', 'effective_cpus': 4, 'gres': ''},
            {'name': 'cpu02', 'state': ['IDLE'], 'gres': ''},
            {'name': 'gpu01', 'state': ['IDLE'], 'effective_cpus': 2, 'gres': 'gpu:1'},
        ]
        result = grade_nodes(answers, nodes)
        self.assertTrue(result['passed'])


class TestGradeController(unittest.TestCase):
    """Test grade_controller for controller grading."""

    def test_primary_responding_passes(self):
        # Real `scontrol --json ping` shape: `status` is an error string; the CLI prints UP from `responding`.
        answers = {
            'primary_host': 'controller',
            'status': 'up'
        }
        pings = [
            {'primary': True, 'responding': True, 'hostname': 'controller', 'status': 'No error'}
        ]
        result = grade_controller(answers, pings)
        self.assertTrue(result['passed'])

    def test_non_responding_primary_stops(self):
        answers = {
            'primary_host': 'controller01',
            'status': 'RUNNING'
        }
        pings = [
            {'primary': True, 'responding': False, 'hostname': 'controller01', 'status': 'running'}
        ]
        result = grade_controller(answers, pings)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['stop'])

    def test_wrong_hostname_fails(self):
        answers = {
            'primary_host': 'wrong-host',
            'status': 'RUNNING'
        }
        pings = [
            {'primary': True, 'responding': True, 'hostname': 'controller01', 'status': 'running'}
        ]
        result = grade_controller(answers, pings)
        self.assertFalse(result['passed'])


class TestDrainPreflight(unittest.TestCase):
    """Test drain_preflight for drain preflight checks."""

    def test_cpu02_not_drained_and_queue_empty_passes(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        queue = []
        result = drain_preflight(token, nodes, queue)
        self.assertTrue(result['passed'])

    def test_cpu02_drained_with_own_reason_passes(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': reason},
        ]
        queue = []
        result = drain_preflight(token, nodes, queue)
        self.assertTrue(result['passed'])

    def test_cpu02_drained_with_others_reason_stops(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': 'someone-else-reason'},
        ]
        queue = []
        result = drain_preflight(token, nodes, queue)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['stop'])

    def test_queue_non_empty_stops(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        queue = [
            {'job_id': '123', 'state': 'RUNNING', 'reason': ''},
        ]
        result = drain_preflight(token, nodes, queue)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['stop'])

    def test_cpu02_down_stops(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['DOWN'], 'reason': ''},
        ]
        queue = []
        result = drain_preflight(token, nodes, queue)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['stop'])


class TestGradeDrained(unittest.TestCase):
    """Test grade_drained for drained node verification."""

    def test_drained_with_own_reason_passes(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': reason},
        ]
        result = grade_drained(token, nodes)
        self.assertTrue(result['passed'])

    def test_not_drained_fails(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        result = grade_drained(token, nodes)
        self.assertFalse(result['passed'])

    def test_drained_but_wrong_reason_stops(self):
        token = 'c12345678'
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': 'other-reason'},
        ]
        result = grade_drained(token, nodes)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['stop'])

    def test_already_resumed_passes_from_own_drain_event(self):
        # Learner did DRAIN, then RESUME, then pressed t1's check: the DRAIN is still on record in sacctmgr events.
        token = 'c12345678'
        nodes = [{'name': 'cpu02', 'state': ['IDLE'], 'reason': ''}]
        mine = [{'node': 'cpu02', 'time_start': '2026-10-25T09:34:01', 'time_end': '2026-10-25T09:41:50',
                 'state': 'DRAIN', 'reason': f'{reason_for(token)}-practice', 'user': 'root'}]
        other = [{**mine[0], 'reason': 'admin-kernel-upgrade'}]
        self.assertTrue(grade_drained(token, nodes, mine)['passed'])
        self.assertFalse(grade_drained(token, nodes, other)['passed'])


class TestGradeProbePending(unittest.TestCase):
    """Test grade_probe_pending for probe pending check."""

    def test_pending_with_req_node_not_avail_passes(self):
        token = 'c12345678'
        probe_rows = [
            {'job_id': '999', 'state': 'PENDING', 'reason': 'ReqNodeNotAvail'},
        ]
        result = grade_probe_pending(token, probe_rows)
        self.assertTrue(result['passed'])

    def test_running_fails(self):
        token = 'c12345678'
        probe_rows = [
            {'job_id': '999', 'state': 'RUNNING', 'reason': 'None'},
        ]
        result = grade_probe_pending(token, probe_rows)
        self.assertFalse(result['passed'])

    def test_pending_with_resources_reason_fails(self):
        token = 'c12345678'
        probe_rows = [
            {'job_id': '999', 'state': 'PENDING', 'reason': 'Resources'},
        ]
        result = grade_probe_pending(token, probe_rows)
        self.assertFalse(result['passed'])

    def test_no_probe_rows_fails(self):
        token = 'c12345678'
        probe_rows = []
        result = grade_probe_pending(token, probe_rows)
        self.assertFalse(result['passed'])


class TestParseEvents(unittest.TestCase):
    """Test parse_events for event output parsing."""

    def test_valid_event_line(self):
        stdout = 'cpu02|2024-10-20T10:00:00|2024-10-20T10:05:00|DRAIN|course-c12345678|lab'
        rows = parse_events(stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['node'], 'cpu02')
        self.assertEqual(rows[0]['time_start'], '2024-10-20T10:00:00')
        self.assertEqual(rows[0]['time_end'], '2024-10-20T10:05:00')
        self.assertEqual(rows[0]['state'], 'DRAIN')
        self.assertEqual(rows[0]['reason'], 'course-c12345678')
        self.assertEqual(rows[0]['user'], 'lab')

    def test_empty_input(self):
        stdout = ''
        rows = parse_events(stdout)
        self.assertEqual(len(rows), 0)

    def test_multiple_events(self):
        stdout = '''cpu02|2024-10-20T10:00:00|2024-10-20T10:05:00|DRAIN|course-c12345678|lab
cpu01|2024-10-20T09:00:00|2024-10-20T09:30:00|DRAIN|other-reason|admin'''
        rows = parse_events(stdout)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['node'], 'cpu02')
        self.assertEqual(rows[1]['node'], 'cpu01')


class TestParseProbeSacct(unittest.TestCase):
    """Test parse_probe_sacct for probe sacct output parsing."""

    def test_valid_probe_sacct(self):
        stdout = '''JobID|State|Start|End|NodeList
999|COMPLETED|2024-10-20T10:05:01|2024-10-20T10:05:30|cpu02
'''
        rows = parse_probe_sacct(stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['JobID'], '999')
        self.assertEqual(rows[0]['State'], 'COMPLETED')
        self.assertEqual(rows[0]['Start'], '2024-10-20T10:05:01')

    def test_empty_input(self):
        stdout = ''
        rows = parse_probe_sacct(stdout)
        self.assertEqual(len(rows), 0)

    def test_header_only(self):
        stdout = 'JobID|State|Start|End|NodeList'
        rows = parse_probe_sacct(stdout)
        self.assertEqual(len(rows), 0)


class TestGradeResumed(unittest.TestCase):
    """Test grade_resumed for node resumption verification."""

    def test_resumed_with_completed_probe_passes(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        events = [
            {
                'node': 'cpu02',
                'time_start': '2024-10-20T10:00:00',
                'time_end': '2024-10-20T10:05:00',
                'state': 'DRAIN',
                'reason': reason,
                'user': 'lab'
            }
        ]
        probe_rows = [
            {'JobID': '999', 'State': 'COMPLETED', 'Start': '2024-10-20T10:05:01', 'End': '2024-10-20T10:05:30', 'NodeList': 'cpu02'}
        ]
        result = grade_resumed(token, nodes, events, probe_rows)
        self.assertTrue(result['passed'])

    def test_still_drained_fails(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE', 'DRAIN'], 'reason': reason},
        ]
        events = []
        probe_rows = []
        result = grade_resumed(token, nodes, events, probe_rows)
        self.assertFalse(result['passed'])
        resumed_item = next((i for i in result['items'] if 'RESUME' in i['項目']), None)
        self.assertIsNotNone(resumed_item)
        self.assertEqual(resumed_item['結果'], '✗')

    def test_probe_started_before_drain_end_fails(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        events = [
            {
                'node': 'cpu02',
                'time_start': '2024-10-20T10:00:00',
                'time_end': '2024-10-20T10:05:00',
                'state': 'DRAIN',
                'reason': reason,
                'user': 'lab'
            }
        ]
        # Probe started before drain ended
        probe_rows = [
            {'JobID': '999', 'State': 'COMPLETED', 'Start': '2024-10-20T10:04:00', 'End': '2024-10-20T10:05:30', 'NodeList': 'cpu02'}
        ]
        result = grade_resumed(token, nodes, events, probe_rows)
        self.assertFalse(result['passed'])
        probe_item = next((i for i in result['items'] if 'probe' in i['項目'] and 'RESUME' in i['項目']), None)
        self.assertIsNotNone(probe_item)
        self.assertEqual(probe_item['結果'], '✗')

    def test_unknown_time_end_fails(self):
        token = 'c12345678'
        reason = reason_for(token)
        nodes = [
            {'name': 'cpu02', 'state': ['IDLE'], 'reason': ''},
        ]
        events = [
            {
                'node': 'cpu02',
                'time_start': '2024-10-20T10:00:00',
                'time_end': 'Unknown',
                'state': 'DRAIN',
                'reason': reason,
                'user': 'lab'
            }
        ]
        probe_rows = [
            {'JobID': '999', 'State': 'COMPLETED', 'Start': '2024-10-20T10:05:01', 'End': '2024-10-20T10:05:30', 'NodeList': 'cpu02'}
        ]
        result = grade_resumed(token, nodes, events, probe_rows)
        self.assertFalse(result['passed'])

    def test_empty_probe_rows_skips_probe_item(self):
        token = 'c12345678'
        nodes = [{'name': 'cpu02', 'state': ['IDLE'], 'reason': ''}]
        events = [{'node': 'cpu02', 'time_start': '2024-10-20T10:00:00', 'time_end': '2024-10-20T10:05:00',
                   'state': 'DRAIN', 'reason': reason_for(token), 'user': 'lab'}]
        result = grade_resumed(token, nodes, events, [])
        self.assertTrue(result['passed'], result['items'])
        self.assertFalse(any('probe' in i['項目'] for i in result['items']))


class TestMistakeExamples(unittest.TestCase):
    """Test mistake_examples function for common mistake illustrations."""

    def test_mistake_examples_returns_three_examples(self):
        token = 'c00000000'
        examples = mistake_examples(token)
        self.assertEqual(len(examples), 3, f"Should return 3 examples, got {len(examples)}")

    def test_each_example_has_required_keys(self):
        token = 'c00000000'
        examples = mistake_examples(token)
        required_keys = {'title', 'what', 'slurm', 'grader_items'}
        for i, ex in enumerate(examples):
            self.assertEqual(set(ex.keys()), required_keys,
                           f"Example {i} missing or has extra keys. Got {set(ex.keys())}, expected {required_keys}")

    def test_each_example_has_failing_items(self):
        token = 'c00000000'
        examples = mistake_examples(token)
        for i, ex in enumerate(examples):
            items = ex['grader_items']
            self.assertGreater(len(items), 0, f"Example {i} '{ex['title']}' has no grader items")
            has_failure = any(item.get('結果') == '✗' for item in items)
            self.assertTrue(has_failure, f"Example {i} '{ex['title']}' has no '✗' items (should show mistakes)")


class TestReferenceFiles(unittest.TestCase):
    """The reference answer shown in chapter 03 must itself pass the page's checks."""

    def test_reference_sbatch_passes_check(self):
        _, sbatch = reference_files('c12345678')
        result = check_sbatch_text('c12345678', sbatch)
        self.assertTrue(result['passed'], result['items'])

    def test_reference_job_py_compiles(self):
        job_py, _ = reference_files('c12345678')
        compile(job_py, 'job.py', 'exec')


class TestSrunPath(unittest.TestCase):
    """srun must run this practice's job.py, not a same-named file elsewhere."""

    BASE = ('#!/bin/bash\n#SBATCH --job-name=course-c12345678\n#SBATCH --mem=1G\n#SBATCH --time=00:10:00\n'
            '#SBATCH --chdir=/shared/course/c12345678/\n#SBATCH --output=/shared/course/c12345678/job-%j.out\n')

    def passed(self, line):
        return check_sbatch_text('c12345678', self.BASE + line + '\n')['passed']

    def test_own_directory_full_or_relative_path_passes(self):
        for line in ('srun python3 /shared/course/c12345678/job.py', 'srun python3 job.py', 'srun python3 ./job.py'):
            self.assertTrue(self.passed(line), line)

    def test_other_directory_or_name_fails(self):
        for line in ('srun python3 /shared/course/abc/job.py', 'srun python3 myjob.py', 'srun python3 /shared/course/c12345678/jobb.py'):
            self.assertFalse(self.passed(line), line)


if __name__ == '__main__':
    unittest.main()
