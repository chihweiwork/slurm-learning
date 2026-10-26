"""第 03／10 章練習：學員自己寫、自己提交；本模組只負責檢查。

解析與評分是純函式（可單元測試）。I/O 只讀：以 lab 身分查 sacct、讀 shared/course/<token>/ 裡的檔案。
"""
import math
import re

import course_progress
from notebook_queries import ROOT
from slurm_cli import compose_argv, run_command

_JOB = re.compile(r'[0-9]+\Z')
_UNITS = {'': 1, 'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3, 'T': 1024 ** 4}
MIN_TIME = 60
_token = course_progress._token
container_dir = course_progress.container_dir


def job_name(token):
    return f'course-{_token(token)}'


def _directory(token):
    path = course_progress.host_dir(token)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f'練習目錄不安全：{path}')
    return path


# ---- pure parsers ---------------------------------------------------------------------

def parse_mem(value):
    """Bytes for Slurm sizes like 128M, 1G, 64824K, 7M ('n'/'c' per-node/cpu suffixes ignored)."""
    match = re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)([KMGT]?)[nc]?\s*', value or '', re.IGNORECASE)
    if not match:
        return None
    return int(float(match.group(1)) * _UNITS[match.group(2).upper()])


def parse_duration(value):
    """Seconds for MM:SS, HH:MM:SS, D-HH:MM:SS (and MM:SS.fff); None for blank or unlimited."""
    value = (value or '').strip()
    match = re.fullmatch(r'(?:([0-9]+)-)?(?:([0-9]+):)?([0-9]+):([0-9]+)(?:\.[0-9]+)?', value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(part) if part else 0 for part in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def format_duration(seconds):
    return f'{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


def parse_sacct(stdout):
    lines = [line for line in (stdout or '').splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split('|')
    return [dict(zip(header, line.split('|'))) for line in lines[1:] if len(line.split('|')) == len(header)]


def summarize(job_id, rows):
    """Allocation row plus peak step MaxRSS (bytes); allocation rows carry no MaxRSS."""
    allocation = next((row for row in rows if row.get('JobID') == job_id), None)
    if allocation is None:
        return {'status': 'missing', 'job_id': job_id, 'rows': rows}
    steps = [parse_mem(row.get('MaxRSS', '')) for row in rows if row.get('JobID', '').startswith(job_id + '.')]
    steps = [value for value in steps if value is not None]
    return {'status': 'ok', 'job_id': job_id, 'allocation': allocation,
            'max_rss_bytes': max(steps) if steps else None, 'rows': rows}


def _item(name, ok, detail):
    return {'項目': name, '結果': '✓' if ok else '✗', '說明': detail}


def _verdict(items, advice=None, pending=False):
    return {'passed': bool(items) and all(i['結果'] == '✓' for i in items) and not pending,
            'items': items, 'advice': advice, 'pending': pending}


def _mib(value):
    return f'{value / 1024 ** 2:.1f} MiB'


def check_sbatch_text(token, text, program='job.py'):
    """Grade job.sbatch content: shebang and required #SBATCH directives."""
    lines = text.splitlines()
    directives = {}
    for line in lines:
        match = re.match(r'\s*#SBATCH\s+(--[a-z-]+)(?:[= ](\S+))?', line)
        if match:
            directives[match.group(1)] = match.group(2) or ''
    items = [_item('第一行 #!/bin/bash', bool(lines) and lines[0].startswith('#!'), '' if lines and lines[0].startswith('#!') else 'batch script 第一行要寫直譯器，例如 #!/bin/bash')]
    name = directives.get('--job-name')
    items.append(_item('--job-name', name == job_name(token), f'必須是 {job_name(token)}' if name != job_name(token) else name))
    memory = directives.get('--mem')
    if memory and re.fullmatch(r'[0-9]+(?:\.[0-9]+)[KMGT]?', memory, re.IGNORECASE):
        whole = math.ceil(float(re.match(r'[0-9.]+', memory).group()))
        items.append(_item('--mem', False, f'{memory}：Slurm 只接受整數（sbatch 會回 Invalid --mem specification）；'
                                         f'無條件進位寫成 {whole}{memory[len(memory.rstrip("KMGTkmgt")):]}'))
    else:
        ok = bool(memory) and re.fullmatch(r'[0-9]+[KMGT]?', memory, re.IGNORECASE) is not None
        items.append(_item('--mem', ok, memory if ok else '缺少或格式不對；整數加單位，例如 1G 或 72M（先寬鬆，之後依 MaxRSS 調小）'))
    value = directives.get('--time')
    ok = bool(value) and parse_duration(value) is not None
    items.append(_item('--time', ok, value if ok else '缺少或格式不對；例如 00:10:00（先寬鬆，之後依 Elapsed 調短）'))
    output = directives.get('--output', '')
    ok = output.startswith(container_dir(token))
    items.append(_item('--output', ok, output if ok else f'要寫到 {container_dir(token)}，例如 {container_dir(token)}job-%j.out'))
    if '--chdir' not in directives:
        items.append(_item('--chdir', True, '沒寫也可以：頁面終端已在你的練習目錄提交'))
    else:
        chdir = directives['--chdir'].rstrip('/')
        ok = chdir == container_dir(token).rstrip('/')
        items.append(_item('--chdir', ok, chdir if ok else f'有寫 --chdir 就要設成 {container_dir(token)}（或乾脆不寫）'))
    # program must be this learner's file: the full path, or a bare name resolved through the work dir.
    target = re.compile(r'\bsrun\b.*(?<![\w/.-])(?:' + re.escape(container_dir(token)) + r'|\./)?' + re.escape(program) + r'(?![\w.-])')
    runs = any(target.search(line) for line in lines if not line.lstrip().startswith('#'))
    items.append(_item(f'用 srun 執行 {program}', runs, '' if runs else f'script 本體要有 srun python3 {container_dir(token)}{program}（路徑要指到你自己的練習目錄）'))
    return _verdict(items)


def _identity_items(token, summary):
    allocation = summary['allocation']
    return [
        _item('JobName', allocation.get('JobName') == job_name(token), allocation.get('JobName', '')),
        _item('使用者', allocation.get('User') == 'lab', allocation.get('User', '')),
        _item('WorkDir', allocation.get('WorkDir', '').startswith(container_dir(token).rstrip('/')),
              allocation.get('WorkDir', '') or '（空）'),
    ]


def evaluate_first(token, summary, output_found):
    if summary['status'] != 'ok':
        return _verdict([_item('sacct 紀錄', False, f"查不到 job {summary.get('job_id')}；確認 ID，或剛提交請稍候")])
    allocation = summary['allocation']
    items = _identity_items(token, summary)
    state = allocation.get('State', '')
    if state in {'PENDING', 'RUNNING', 'COMPLETING', 'CONFIGURING'}:
        return _verdict(items + [_item('狀態', False, f'{state}：還沒結束；MaxRSS 在 step 結束時才寫入，等結束後再按一次檢查')], pending=True)
    items.append(_item('狀態', state == 'COMPLETED', state))
    items.append(_item('ExitCode', allocation.get('ExitCode') == '0:0', allocation.get('ExitCode', '')))
    items.append(_item('輸出檔', output_found, '找到且非空' if output_found else f'在 {container_dir(token)} 找不到含 job ID 的輸出檔'))
    rss = summary['max_rss_bytes']
    items.append(_item('step MaxRSS', rss is not None, _mib(rss) if rss is not None else
                       'step 列沒有 MaxRSS：sacct 在 step 結束時才寫入；工作還沒結束，或 step 沒有成功啟動（看 .0 列的 State）'))
    advice = None
    elapsed = parse_duration(allocation.get('Elapsed', ''))
    if rss is not None and elapsed is not None:
        memory = max(64, math.ceil(rss * 1.3 / 1024 ** 2))
        seconds = max(MIN_TIME, math.ceil(elapsed * 1.5))
        advice = {'mem': f'{memory}M', 'time': format_duration(seconds),
                  'text': (f'第一次申請 ReqMem={allocation.get("ReqMem")}、Timelimit={allocation.get("Timelimit")}；'
                           f'實際 MaxRSS={_mib(rss)}、Elapsed={allocation.get("Elapsed")}。'
                           f'建議下一次 --mem={memory}M（≈1.3×MaxRSS）、--time={format_duration(seconds)}（≈1.5×Elapsed，至少 1 分鐘）。')}
    return _verdict(items, advice)


def evaluate_second(token, first, second, output_found):
    if second['status'] != 'ok':
        return _verdict([_item('sacct 紀錄', False, f"查不到 job {second.get('job_id')}")])
    if first.get('status') != 'ok':
        return _verdict([_item('第一次結果', False, '先通過步驟 2')])
    allocation, before = second['allocation'], first['allocation']
    items = [_item('不同的 job', second['job_id'] != first['job_id'], f"第一次 {first['job_id']}，第二次 {second['job_id']}")]
    items += _identity_items(token, second)
    state = allocation.get('State', '')
    if state in {'PENDING', 'RUNNING', 'COMPLETING', 'CONFIGURING'}:
        return _verdict(items + [_item('狀態', False, f'{state}：還沒結束，等一下再檢查')], pending=True)
    items.append(_item('狀態', state == 'COMPLETED', state))
    items.append(_item('ExitCode', allocation.get('ExitCode') == '0:0', allocation.get('ExitCode', '')))
    items.append(_item('輸出檔', output_found, '找到且非空' if output_found else '找不到輸出檔'))
    old_mem, new_mem = parse_mem(before.get('ReqMem', '')), parse_mem(allocation.get('ReqMem', ''))
    rss = first.get('max_rss_bytes')
    if None in (old_mem, new_mem, rss):
        items.append(_item('--mem 調整', False, '缺少 ReqMem 或第一次的 MaxRSS，無法判斷'))
    else:
        floor = 1.2 * rss
        ok = floor <= new_mem < old_mem
        items.append(_item('--mem 調整', ok, f'{_mib(old_mem)} → {_mib(new_mem)}；要比第一次小，且 ≥ 1.2×MaxRSS（{_mib(floor)}）'))
    old_time, new_time = parse_duration(before.get('Timelimit', '')), parse_duration(allocation.get('Timelimit', ''))
    elapsed = parse_duration(before.get('Elapsed', ''))
    if None in (old_time, new_time, elapsed):
        items.append(_item('--time 調整', False, '缺少 Timelimit 或 Elapsed，無法判斷'))
    else:
        floor = max(MIN_TIME, math.ceil(1.2 * elapsed))
        ok = floor <= new_time < old_time
        items.append(_item('--time 調整', ok, f'{format_duration(old_time)} → {format_duration(new_time)}；'
                                              f'要比第一次短，且 ≥ max(1 分鐘, 1.2×Elapsed)＝{format_duration(floor)}'))
    return _verdict(items)


# ---- read-only I/O ------------------------------------------------------------------

def check_files(token, program='job.py', script='job.sbatch'):
    directory = _directory(token)
    program_path, script_path = directory / program, directory / script
    found = program_path.is_file() and not program_path.is_symlink() and program_path.stat().st_size > 0
    items = [_item(program, found, '找到' if found else f'在 shared/course/{token}/ 建立 {program}')]
    if script_path.is_file() and not script_path.is_symlink():
        graded = check_sbatch_text(token, script_path.read_text(encoding='utf-8', errors='replace'), program=program)
        items += graded['items']
    else:
        items.append(_item(script, False, f'在 shared/course/{token}/ 建立 {script}'))
    return _verdict(items)


def job_summary(job_id):
    job_id = (job_id or '').strip()
    if not _JOB.fullmatch(job_id):
        return {'status': 'invalid', 'job_id': job_id, 'rows': []}
    result = run_command(compose_argv('sacct', '--parsable2', '-j', job_id,
                                      '--format=JobID,JobName,User,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS,WorkDir'),
                         cwd=ROOT, timeout=15)
    if result.returncode:
        return {'status': 'error', 'job_id': job_id, 'rows': [], 'error': result.stderr.strip()}
    return summarize(job_id, parse_sacct(result.stdout))


def output_ok(token, job_id):
    directory = _directory(token)
    return any(path.is_file() and not path.is_symlink() and job_id in path.name and path.stat().st_size > 0
               for path in directory.iterdir())


# Real sacct --parsable2 output captured on this cluster (names/paths rewritten to the course layout), for chapter 03's
# "common mistakes" examples: 603 first run, 604 --mem=60M OOM, 748 checked while still RUNNING.
_SACCT_HEADER = 'JobID|JobName|User|State|ExitCode|Elapsed|Timelimit|ReqMem|MaxRSS|WorkDir\n'
_REAL_SACCT = {
    '603': ('603|course-{token}|lab|COMPLETED|0:0|00:00:16|00:10:00|1G||/shared/course/{token}/\n'
            '603.batch|batch||COMPLETED|0:0|00:00:16|||6408K|\n'
            '603.extern|extern||COMPLETED|0:0|00:00:16||||\n'
            '603.0|python3||COMPLETED|0:0|00:00:15|||55688K|\n'),
    '604': ('604|course-{token}|lab|FAILED|1:0|00:00:01|00:01:00|60M||/shared/course/{token}/\n'
            '604.batch|batch||FAILED|1:0|00:00:01|||5800K|\n'
            '604.extern|extern||COMPLETED|0:0|00:00:01||||\n'
            '604.0|python3||OUT_OF_MEMORY|0:125|00:00:00|||53740K|\n'),
    '748': ('748|course-{token}|lab|RUNNING|0:0|00:00:07|00:10:00|1G||/shared/course/{token}/\n'
            '748.batch|batch||RUNNING|0:0|00:00:07||||\n'
            '748.extern|extern||RUNNING|0:0|00:00:07||||\n'
            '748.0|python3||RUNNING|0:0|00:00:06||||\n'),
}


def _real_sacct(job_id, token):
    text = _SACCT_HEADER + _REAL_SACCT[job_id].replace('{token}', token)
    return text, summarize(job_id, parse_sacct(text))


def mistake_examples(token):
    """Three common mistakes with the real Slurm output and what the page's graders say about them."""
    token = _token(token)
    directory = container_dir(token)
    wrong_path = (f'#!/bin/bash\n#SBATCH --job-name={job_name(token)}\n#SBATCH --mem=1G\n#SBATCH --time=00:10:00\n'
                  f'#SBATCH --chdir={directory}\n#SBATCH --output={directory}job-%j.out\n'
                  'srun python3 /shared/course/abc/jobb.py\n')
    running_text, running = _real_sacct('748', token)
    _, first = _real_sacct('603', token)
    tight_text, tight = _real_sacct('604', token)
    return [
        {'title': '檔案路徑錯',
         'what': '`srun python3 /shared/course/abc/jobb.py`：目錄與檔名都打錯。工作照樣會被接受、排程，然後在節點上失敗。',
         'slurm': ("/usr/bin/python3: can't open file '/shared/course/abc/jobb.py': [Errno 2] No such file or directory\n"
                   'srun: error: cpu01: task 0: Exited with exit code 2\n'
                   'sacct：allocation 與 .0 都是 FAILED 2:0'),
         'grader_items': check_sbatch_text(token, wrong_path)['items']},
        {'title': 'MaxRSS 空白：工作還沒結束，或看錯列',
         'what': '工作跑到第 7 秒時就查 sacct。MaxRSS 在 step 結束時才寫入，所以每一列都空白；'
                 '結束後也只有 `.batch`／`.0` 列有值，allocation 列（無點號）永遠空白。'
                 '本 lab 即使 1 秒的工作，結束後 `.0` 列也記得到峰值（實測 50 MB 程式：54500K）。',
         'slurm': running_text,
         'grader_items': evaluate_first(token, running, output_found=False)['items']},
        {'title': '資源縮得太緊',
         'what': '第一次 `.0` MaxRSS 55688K（約 54.4 MiB），第二次只申請 `--mem=60M`：不到 1.2 倍餘裕，kernel 在 cgroup 內 OOM kill。',
         'slurm': ('error: Detected 2 oom_kill events in StepId=604.0. Some of the step tasks have been OOM Killed.\n'
                   'srun: error: cpu01: task 0: Out Of Memory\n' + tight_text),
         'grader_items': evaluate_second(token, first, tight, output_found=True)['items']},
    ]


def reference_files(token, program='job.py'):
    """Minimal working program and sbatch for this learner (shown after the first file check)."""
    token = _token(token)
    directory = container_dir(token)
    job_py = '''import hashlib
import os
import socket
import time

data = bytearray(50 * 1024 * 1024)        # 約 50 MB
for offset in range(0, len(data), 4096):   # 每一頁都寫入，記憶體才會真的被用到
    data[offset] = offset % 251
time.sleep(15)                             # 留時間讓你用 squeue 看到它在跑
print('hostname', socket.gethostname())
print('SLURM_JOB_ID', os.environ.get('SLURM_JOB_ID'))
print('sha256', hashlib.sha256(data).hexdigest())
'''
    job_sbatch = (f'#!/bin/bash\n#SBATCH --job-name={job_name(token)}\n#SBATCH --partition=cpu\n'
                  '#SBATCH --cpus-per-task=1\n#SBATCH --mem=1G\n#SBATCH --time=00:10:00\n'
                  f'#SBATCH --chdir={directory}\n#SBATCH --output={directory}job-%j.out\n'
                  f'srun python3 {directory}{program}\n')
    return job_py, job_sbatch
