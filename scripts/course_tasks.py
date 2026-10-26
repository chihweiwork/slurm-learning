"""Graders for the "換你練習" tasks: pure functions over sacct rows and the terminal transcript.

Every grader returns course_jobs._verdict's shape: {'passed', 'items', 'advice', 'pending'}.
The I/O helpers at the bottom are read-only queries as user lab.
"""
from datetime import datetime
import re

import course_files
import course_jobs
import course_ops
import course_progress
import course_terminal
from course_jobs import _item, _verdict, parse_sacct
from notebook_queries import ROOT, query_nodes
from slurm_cli import compose_argv, run_command

SACCT_FORMAT = 'JobID,JobName,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS,NCPUS,ReqTRES,Partition,WorkDir,Submit,NodeList'
ACTIVE = ('PENDING', 'RUNNING', 'COMPLETING', 'CONFIGURING', 'REQUEUED', 'RESIZING', 'SUSPENDED')
_SUBMITTED = re.compile(r'Submitted batch job ([0-9]+)')


def _active(state):
    return state.startswith(ACTIVE)


def _parent(job_id):
    return re.split(r'[._]', job_id, maxsplit=1)[0]


def _mentions(text, identifier):
    return re.search(rf'(?<![0-9]){re.escape(identifier)}(?![0-9])', text) is not None


def combine(*verdicts):
    items = [item for verdict in verdicts for item in verdict['items']]
    return _verdict(items, pending=any(v.get('pending') for v in verdicts))


def submitted_ids(transcript):
    """JobIDs printed by successful sbatch lines in the transcript, oldest first."""
    found = []
    for entry in transcript:
        if (entry.get('argv') or [None])[0] == 'sbatch' and entry.get('returncode') == 0:
            found += _SUBMITTED.findall(entry.get('stdout', ''))
    return found


def grade_command_used(transcript, command, *, must_include=(), job_ids=frozenset()):
    """A successful run of `command` whose text contains every must_include entry (a string, or a tuple of
    acceptable alternatives) and, when job_ids is given, mentions one of them."""
    def matches(entry):
        argv = entry.get('argv') or []
        if not argv or argv[0] != command or entry.get('returncode') != 0:
            return False
        joined = ' '.join(argv)
        for need in must_include:
            options = need if isinstance(need, tuple) else (need,)
            if not any(option in joined for option in options):
                return False
        return not job_ids or any(_mentions(joined, str(identifier)) for identifier in job_ids)

    hits = [entry for entry in transcript if matches(entry)]
    wanted = ' '.join([command] + [n if isinstance(n, str) else '／'.join(n) for n in must_include])
    if hits:
        when = datetime.fromisoformat(hits[-1]['at']).astimezone().strftime('%H:%M:%S')
        return _verdict([_item(f'執行 {wanted}', True, f"`{hits[-1]['command']}`（{when}）")])
    tried = [e for e in transcript if (e.get('argv') or [None])[0] == command]
    if not tried:
        hint = f'在下方終端輸入 {wanted}' + ('，後面接你自己的 JobID' if job_ids else '')
    elif all(e.get('returncode') != 0 for e in tried):
        hint = f"跑過 {command} 但都沒有成功結束（最後一次：`{tried[-1]['command']}`）；看紅色／黃色訊息修正"
    elif job_ids:
        hint = f"有跑 {command}，但沒有帶到你這份練習的 JobID（{'、'.join(sorted(map(str, job_ids))[-5:])}）"
    else:
        hint = f"有跑 {command}，但缺少 {wanted} 裡的選項（最後一次：`{tried[-1]['command']}`）"
    return _verdict([_item(f'執行 {wanted}', False, hint)])


def grade_completed_job(allocations, *, name_prefix=None, partition=None, min_count=1, tres_contains=None, state='COMPLETED'):
    rows = [r for r in allocations
            if (name_prefix is None or r.get('JobName', '').startswith(name_prefix))
            and (partition is None or r.get('Partition') == partition)
            and (tres_contains is None or tres_contains in r.get('ReqTRES', ''))]
    done = [r for r in rows if r.get('State', '').startswith(state)]
    waiting = [r for r in rows if _active(r.get('State', ''))]
    if len(done) >= min_count:
        return _verdict([_item(f'{state} 的工作', True, '、'.join(f"{r['JobID']} {r['JobName']}" for r in done[-5:]))])
    if waiting:
        return _verdict([_item(f'{state} 的工作', False, '還在跑：' + '、'.join(f"{r['JobID']} {r['State']}" for r in waiting))],
                        pending=True)
    seen = '、'.join(f"{r['JobID']} {r['State']}" for r in rows[-5:]) or '還沒有在你的練習目錄提交過符合的工作'
    return _verdict([_item(f'{state} 的工作', False, f'需要 {min_count} 個，找到 {len(done)} 個；目前：{seen}')])


def grade_array(allocations):
    tasks = [r for r in allocations if re.fullmatch(r'[0-9]+_[0-9]+', r.get('JobID', ''))]
    groups = {}
    for row in tasks:
        groups.setdefault(_parent(row['JobID']), []).append(row)
    best = max(groups.values(), key=lambda rows: sum(r['State'] == 'COMPLETED' for r in rows), default=[])
    completed = [r for r in best if r['State'] == 'COMPLETED']
    pending = any(_active(r.get('State', '')) or '[' in r.get('JobID', '') for r in allocations
                  if _parent(r.get('JobID', '')) in groups)
    if len(completed) >= 3:
        return _verdict([_item('array 至少 3 個 task COMPLETED', True,
                               f"array {_parent(completed[0]['JobID'])}：" + '、'.join(r['JobID'] for r in completed))])
    if not groups:
        detail = '還沒找到 array task（JobID 會長得像 123_0）；用 sbatch --array=0-2 提交'
    else:
        detail = f"array {_parent(best[0]['JobID'])} 目前 {len(completed)} 個 COMPLETED：" + '、'.join(f"{r['JobID']} {r['State']}" for r in best)
    return _verdict([_item('array 至少 3 個 task COMPLETED', False, detail)], pending=pending and len(completed) < 3)


def grade_dependency(transcript, allocations):
    by_id = {r['JobID']: r for r in allocations}
    parents = {_parent(r['JobID']) for r in allocations}
    tried = []
    for entry in transcript:
        argv = entry.get('argv') or []
        if not argv or argv[0] != 'sbatch' or entry.get('returncode') != 0:
            continue
        joined = ' '.join(argv)
        target = re.search(r'(?:--dependency[= ]|-d ?)afterok:([0-9]+)', joined)
        if not target:
            continue
        submitted = _SUBMITTED.findall(entry.get('stdout', ''))
        tried.append((target.group(1), submitted[0] if submitted else None, entry))
    if not tried:
        return _verdict([_item('afterok 相依工作', False, '還沒看到 sbatch --dependency=afterok:<JobID>；先提交 array，再用它的 JobID')])
    items, pending = [], False
    for target, dependent, entry in reversed(tried):
        if target not in parents:
            items = [_item('afterok 相依工作', False, f"`{entry['command']}` 等的是 {target}，但它不是你練習目錄裡的工作")]
            continue
        row = by_id.get(dependent or '')
        if row is None:
            items = [_item('afterok 相依工作', False, f'相依工作 {dependent} 還沒有 accounting 紀錄，稍後再檢查')]
            pending = True
            continue
        if row['State'] == 'COMPLETED':
            return _verdict([_item('afterok 相依工作', True, f"{dependent} 等 {target} 成功後才執行，State=COMPLETED")])
        pending = _active(row['State'])
        items = [_item('afterok 相依工作', False, f"{dependent} 目前 {row['State']}"
                       + ('：前面的工作還沒全部成功，等一下再檢查' if pending else '：前面的工作有失敗，相依工作不會執行；修好後重送'))]
    return _verdict(items, pending=pending)


def grade_state(allocations, rows, state):
    """Any of the learner's allocation or step rows whose State starts with `state`."""
    own = {r['JobID'] for r in allocations}
    candidates = [r for r in rows if r['JobID'] in own or _parent(r['JobID']) in own]
    hits = [r for r in candidates if r.get('State', '').startswith(state)]
    if hits:
        return _verdict([_item(f'State={state}', True, '、'.join(f"{r['JobID']} {r['State']} {r.get('ExitCode', '')}" for r in hits[:6]))])
    waiting = [r for r in allocations if _active(r.get('State', ''))]
    detail = ('還在跑：' + '、'.join(f"{r['JobID']} {r['State']}" for r in waiting)) if waiting else \
        f'在你的練習目錄還沒找到 State 是 {state} 的工作'
    return _verdict([_item(f'State={state}', False, detail)], pending=bool(waiting))


def grade_gpu_job(allocations, outputs):
    """outputs maps JobID -> text of its output file (or None)."""
    gpu = [r for r in allocations if r.get('Partition') == 'gpu']
    if not gpu:
        return _verdict([_item('GPU 工作', False, '還沒有 --partition=gpu 的工作；照提示指令提交')])
    latest = gpu[-1]
    if _active(latest['State']):
        return _verdict([_item('GPU 工作', False, f"{latest['JobID']} 目前 {latest['State']}，稍後再檢查")], pending=True)
    for row in reversed(gpu):
        text = outputs.get(row['JobID']) or ''
        if row['State'] == 'COMPLETED' and 'gres/gpu=1' in row.get('ReqTRES', '') and 'GPU 0' in text:
            return _verdict([_item('申請 gres/gpu=1', True, row['ReqTRES']), _item('COMPLETED', True, row['JobID']),
                             _item('輸出看得到 GPU 0', True, text.strip().splitlines()[0][:120])])
    text = outputs.get(latest['JobID']) or ''
    return _verdict([
        _item('申請 gres/gpu=1', 'gres/gpu=1' in latest.get('ReqTRES', ''), latest.get('ReqTRES', '') or '（空）：要寫 --gres=gpu:1'),
        _item('COMPLETED', latest['State'] == 'COMPLETED', f"{latest['JobID']} {latest['State']} {latest.get('ExitCode', '')}"),
        _item('輸出看得到 GPU 0', 'GPU 0' in text, '找不到輸出檔' if not text else text.strip()[:120]),
    ])


def grade_drain(nodes, token, events=()):
    return course_ops.grade_drained(token, nodes, events)


def grade_resume(nodes, events, token):
    return course_ops.grade_resumed(token, nodes, events, [])


# ---- read-only I/O ------------------------------------------------------------------

def token_jobs(token):
    """All sacct rows since the learner's record was created, plus own allocations: jobs whose WorkDir is the
    learner's directory, or that the learner's terminal submitted (example scripts may set their own --chdir)."""
    created = course_progress.load(token).get('created', '')
    try:
        start = datetime.fromisoformat(created).strftime('%Y-%m-%dT%H:%M:%S')
    except ValueError:
        start = 'now-7days'
    try:
        result = run_command(compose_argv('sacct', '-u', 'lab', f'--starttime={start}', '--parsable2',
                                          f'--format={SACCT_FORMAT}'), cwd=ROOT, timeout=15)
    except OSError as exc:
        return {'rows': [], 'allocations': [], 'error': str(exc)}
    if result.returncode:
        return {'rows': [], 'allocations': [], 'error': result.stderr.strip() or f'sacct exit {result.returncode}'}
    rows = parse_sacct(result.stdout)
    directory = course_progress.container_dir(token).rstrip('/')
    submitted = set(submitted_ids(course_terminal.transcript(token)))
    allocations = [r for r in rows if '.' not in r['JobID']
                   and (r.get('WorkDir', '') == directory or r.get('WorkDir', '').startswith(directory + '/')
                        or _parent(r['JobID']) in submitted)]
    return {'rows': rows, 'allocations': allocations, 'error': None}


def node_state():
    result = query_nodes()
    return result['data'] if result.get('status') == 'ok' else []


def job_ids(jobs):
    """Every JobID (and array parent) the learner owns, for grade_command_used(job_ids=...)."""
    return {r['JobID'] for r in jobs['allocations']} | {_parent(r['JobID']) for r in jobs['allocations']}


def query_error(jobs):
    """A failing verdict when sacct itself failed, else None."""
    if jobs.get('error'):
        return _verdict([_item('sacct 查詢', False, f"查詢失敗：{jobs['error']}")])
    return None


def outputs_for(token, allocations):
    texts = {}
    for row in allocations:
        path = course_files.find_output(token, row['JobID'])
        texts[row['JobID']] = path.read_text(encoding='utf-8', errors='replace')[:4096] if path else None
    return texts


# ---- per-chapter task checks (I/O + graders) -------------------------------------------

def _jobs(token):
    jobs = token_jobs(token)
    return jobs, query_error(jobs)


def _first(token, chapter, value):
    summary = course_jobs.job_summary(value)
    verdict = course_jobs.evaluate_first(token, summary, bool(value) and course_jobs.output_ok(token, value))
    if verdict['passed']:
        course_progress.record(token, chapter, 'first_job_id', value)
    return verdict


def _second(token, chapter, value):
    first_id = (course_progress.load(token)['chapters'].get(chapter) or {}).get('first_job_id')
    if not first_id:
        return _verdict([_item('第一次結果', False, '先通過上一個任務（第一次提交）')])
    return course_jobs.evaluate_second(token, course_jobs.job_summary(first_id), course_jobs.job_summary(value),
                                       bool(value) and course_jobs.output_ok(token, value))


def _with_jobs(grader):
    def run(token, value):
        jobs, error = _jobs(token)
        return error or grader(token, jobs, course_terminal.transcript(token))
    return run


def _oom_then_sacct(token, jobs, transcript):
    state = grade_state(jobs['allocations'], jobs['rows'], 'OUT_OF_MEMORY')
    ooms = {_parent(r['JobID']) for r in jobs['rows'] if r.get('State', '').startswith('OUT_OF_MEMORY')} & job_ids(jobs)
    if not ooms:
        return state
    return combine(state, grade_command_used(transcript, 'sacct', job_ids=ooms))


CHECKS = {
    ('00', 't0-sinfo'): lambda token, value: grade_command_used(course_terminal.transcript(token), 'sinfo'),
    ('02', 't1-submit'): _with_jobs(lambda token, jobs, transcript: grade_completed_job(jobs['allocations'])),
    ('02', 't2-squeue'): lambda token, value: grade_command_used(course_terminal.transcript(token), 'squeue',
                                                                 must_include=[('--me', '-u lab', '--user=lab')]),
    ('02', 't3-show-job'): _with_jobs(lambda token, jobs, transcript: grade_command_used(
        transcript, 'scontrol', must_include=['show', 'job'], job_ids=job_ids(jobs))),
    ('02', 't4-sacct'): _with_jobs(lambda token, jobs, transcript: grade_command_used(transcript, 'sacct', job_ids=job_ids(jobs))),
    ('02', 't5-cancel'): _with_jobs(lambda token, jobs, transcript: combine(
        grade_state(jobs['allocations'], jobs['rows'], 'CANCELLED'),
        grade_command_used(transcript, 'scancel', job_ids=job_ids(jobs)))),
    ('03', 't1-files'): lambda token, value: course_jobs.check_files(token),
    ('03', 't2-first'): lambda token, value: _first(token, '03', value),
    ('03', 't3-second'): lambda token, value: _second(token, '03', value),
    ('04', 't1-reason'): lambda token, value: grade_command_used(course_terminal.transcript(token), 'squeue',
                                                                 must_include=[('%R', '%r', 'Reason', 'reason')]),
    ('05', 't1-array'): _with_jobs(lambda token, jobs, transcript: grade_array(jobs['allocations'])),
    ('05', 't2-dependency'): _with_jobs(lambda token, jobs, transcript: grade_dependency(transcript, jobs['allocations'])),
    ('06', 't1-gpu-job'): _with_jobs(lambda token, jobs, transcript: grade_gpu_job(
        jobs['allocations'], outputs_for(token, jobs['allocations']))),
    ('07', 't1-oom'): _with_jobs(lambda token, jobs, transcript: grade_state(jobs['allocations'], jobs['rows'], 'OUT_OF_MEMORY')),
    ('07', 't2-timeout'): _with_jobs(lambda token, jobs, transcript: grade_state(jobs['allocations'], jobs['rows'], 'TIMEOUT')),
    ('08', 't1-sacct-usage'): lambda token, value: grade_command_used(course_terminal.transcript(token), 'sacct',
                                                                      must_include=['MaxRSS']),
    ('08', 't2-assoc'): lambda token, value: grade_command_used(course_terminal.transcript(token), 'sacctmgr',
                                                                must_include=[('association', 'assoc')]),
    ('09', 't1-drain'): lambda token, value: grade_drain(node_state(), token, course_ops.node_events()),
    ('09', 't2-resume'): lambda token, value: grade_resume(node_state(), course_ops.node_events(), token),
    ('10', 't1-files'): lambda token, value: course_jobs.check_files(token, program='capstone.py', script='capstone.sbatch'),
    ('10', 't2-first'): lambda token, value: _first(token, '10', value),
    ('10', 't3-second'): lambda token, value: _second(token, '10', value),
    ('10', 't4-failure'): _with_jobs(_oom_then_sacct),
}


def check(chapter, task_id, token, value=None):
    """Run one task's check: returns the verdict shown under the task card."""
    return CHECKS[(chapter, task_id)](token, value)

