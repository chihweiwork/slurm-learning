"""Demo-run engine for the course pages: one run per lesson per learner, actions in background threads.

External mutations happen only in start(), after an explicit click: the action runs in a daemon
thread and the page polls step_states()/last_event(). notebook_lab still refuses to replay a
consumed step and re-checks every precondition right before executing.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

import course_progress
import notebook_lab as lab
from lesson_common import text as job_text
from notebook_queries import _number, read_snapshot

TERMINAL = lab.TERMINAL
VERIFY, CLEANUP = 'verify', 'cleanup'
# Action currently running per run (label, start, timeout): one action per run at a time.
_RUNNING: dict[str, dict] = {}
_RUNNING_LOCK = threading.Lock()
# Most recent action outcome per run, for the page to show (submitted -> succeeded/failed/blocked).
LAST_EVENT: dict[str, dict] = {}
EVENT_TEXT = {'submitted': '已送出，背景執行中', 'succeeded': '已完成', 'passed': '已完成（passed）',
              'failed': '失敗', 'blocked': '未執行（被擋下）', 'unknown': '結果未確認', 'running': '已完成（仍有工作在跑）'}


def _call(callback):
    try:
        return callback()
    except Exception as exc:
        return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}


def _timeout(effect):
    return 15 if effect == 'interactive' else 90 if effect in {'restart-controller', 'restore-controller'} else 30


def _clock(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().strftime('%H:%M:%S')


def _job_rows(observed, identifier):
    return (observed['jobs'].get(identifier) or {}).get('records', [])


def _time_left(job, now):
    limit = _number(job['raw'].get('time_limit', 0))
    if not job.get('start_time') or not limit:
        return None
    return int(job['start_time'] + limit * 60 - now)


def _step_status(lesson, step_id, existing, reason, observed, now):
    """(badge, detail) for one step, from receipts, retained jobs and output markers."""
    if existing is None:
        return ('尚不可執行', reason) if reason else ('可執行', '按下方按鈕即執行一次')
    status = existing['status']
    if status == 'unknown':
        started = datetime.fromisoformat(existing['started']).timestamp() if existing.get('started') else 0
        if now - started < existing.get('timeout', 30) + 5:
            return '命令執行中', f'外部命令已開始 {int(now - started)} 秒；完成前不要重複操作'
        return '結果未確認', '有 claim 沒有 receipt：不可重送，請人工核對唯一 job name'
    if status == 'failed':
        return '失敗', existing.get('error') or existing.get('stderr') or '非零結束'
    identifier = existing.get('job_id')
    if not identifier:
        return '已完成', f"{existing.get('seconds', '?')} 秒"
    rows = _job_rows(observed, identifier)
    if not rows:
        state = (observed['jobs'].get(identifier) or {}).get('status', 'record-unavailable')
        return '等待 scheduler 紀錄', f'job {identifier}：{state}（查不到不等於完成）'
    states = {s for row in rows for s in row['job_state']}
    if states & {'PENDING'}:
        reasons = sorted({row['state_reason'] for row in rows if 'PENDING' in row['job_state']})
        estimate = [row['start_time'] for row in rows if 'PENDING' in row['job_state'] and row.get('start_time')]
        hint = f"；scheduler 預估 {_clock(min(estimate))} 開始（只是估計）" if estimate else ''
        return '等待 scheduler', f"job {identifier} PENDING，Reason={'/'.join(reasons)}{hint}"
    if states & {'RUNNING', 'COMPLETING', 'CONFIGURING'}:
        detail = [f"job {identifier} {'/'.join(sorted(states - TERMINAL)) or 'RUNNING'}"]
        marker = lesson.get('markers', {}).get(step_id, '"started": true' if step_id in lesson.get('holder_seconds', {}) else None)
        running = [row for row in rows if 'RUNNING' in row['job_state']]
        for row in running:
            left = _time_left(row, now)
            if left is not None:
                detail.append(f'距 TimeLimit 約 {left} 秒' if left > 0 else
                              '已到 TimeLimit：Slurm 正在送 SIGTERM、終止程序並清理 cgroup（可能需要數十秒）')
            seconds = lesson.get('holder_seconds', {}).get(step_id)
            if seconds and row.get('start_time'):
                detail.append(f"holder 操作窗口約剩 {max(0, int(row['start_time'] + seconds - now))} 秒")
        if marker and running and marker not in job_text(observed, step_id):
            return '等待輸出 marker', '；'.join(detail + [f'尚未看到 {marker}'])
        if running:
            return '執行中', '；'.join(detail)
        return '收尾中（COMPLETING）', '；'.join(detail + ['Slurm 正在終止程序並清理 cgroup，完成後才會變成終態'])
    exit_code = rows[0]['exit_code']
    code = f"{exit_code['return_code'] or 0}:{exit_code['signal']['id'] or 0}"
    return '已結束', f"job {identifier} {'/'.join(sorted(states & TERMINAL))} ExitCode={code}"


def _four_state(badge):
    """Collapse the detailed step status into the four action states shown on every button."""
    if badge == '尚不可執行':
        return '尚未就緒'
    if badge == '可執行':
        return '可執行'
    if badge == '命令執行中':
        return '執行中'
    return '已消耗'


def _timeline_text(record):
    """'RUNNING 16:24:56.1 → COMPLETING 16:26:05.3（停留 1.2 秒）→ TIMEOUT …' from sampled transitions."""
    samples = record.get('samples') or []
    if not samples:
        return '狀態時間軸：取樣中，尚無資料' if not record.get('done') else f"狀態時間軸：沒有取得資料（{record.get('error') or '查無紀錄'}）"
    stamps = [datetime.fromisoformat(s['at']) for s in samples]
    parts = []
    for index, sample in enumerate(samples):
        text = f"{sample['state']} {stamps[index].astimezone().strftime('%H:%M:%S.%f')[:-5]}"
        if index + 1 < len(samples):
            text += f"（停留 {(stamps[index + 1] - stamps[index]).total_seconds():.1f} 秒）"
        parts.append(text)
    line = '**狀態時間軸**（每 %s 秒取樣）：' % record.get('interval', '?') + ' → '.join(parts)
    states = [s['state'] for s in samples]
    if not record.get('done'):
        line += ' → …取樣中'
    elif 'COMPLETING' not in states and states[-1] in TERMINAL:
        line += '。這次 COMPLETING 短於取樣間隔，沒有捕捉到（清理很快完成）'
    if record.get('error'):
        line += f"。取樣錯誤：{record['error']}"
    return line


# ---- runs ----------------------------------------------------------------------------

def default_parameters(lesson):
    return {key: values[0] for key, values in (lesson.get('fields') or {}).items()}


def _chapter(lesson):
    return lesson['chapter'][:2]


def ensure_run(lesson, token, parameters=None):
    """This learner's run for the lesson: reuse the saved one, or freeze a new run (no Slurm effect)."""
    progress = course_progress.load(token)
    runs = progress['chapters'].get(_chapter(lesson), {}).get('runs', {})
    saved = runs.get(lesson['chapter'])
    if saved:
        try:
            if lab.load_run(saved)['chapter'] == lesson['chapter']:
                return saved
        except (OSError, ValueError):
            pass
    created = lab.prepare_run(lesson['chapter'], parameters or default_parameters(lesson))
    if not created.get('run_id'):
        raise RuntimeError(created.get('reason') or f'無法建立實驗：{created}')
    runs = {**runs, lesson['chapter']: created['run_id']}
    course_progress.record(token, _chapter(lesson), 'runs', runs)
    return created['run_id']


def reset_run(lesson, token):
    """Retire the saved run so the next ensure_run() freezes a new one; evidence stays on disk and the retired
    id stays in progress.json so the closing checklist still reports it if it was never cleaned."""
    progress = course_progress.load(token)
    chapter = progress['chapters'].get(_chapter(lesson), {})
    runs = dict(chapter.get('runs', {}))
    retired = runs.pop(lesson['chapter'], None)
    course_progress.record(token, _chapter(lesson), 'runs', runs)
    if retired:
        course_progress.record(token, _chapter(lesson), 'retired_runs', [*chapter.get('retired_runs', []), retired])


def report(run_id):
    """Saved report.json plus whether the latest cleanup attempt had no errors (no scheduler query)."""
    try:
        run = lab.load_run(run_id)
        value = json.loads((Path(run['run_dir']) / 'report.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'status': '缺失', 'cleaned': False, 'acted': False}
    attempts = value.get('cleanup_attempts') or []
    actions = Path(run['run_dir']) / 'actions'
    return {**value, 'cleaned': bool(attempts) and not attempts[-1].get('errors'),
            'acted': actions.is_dir() and any(actions.iterdir())}


def step_states(lesson, run_id):
    """{step_id: {badge, detail, state, receipt, argv, outputs, timeline}} from one read_run snapshot."""
    run = lab.load_run(run_id)
    observed = lab.read_run(run_id)
    now = time.time()
    snapshot, blocked_before, result = None, None, {}
    applicable = set(lesson.get('applicable', lambda r: list(lesson['steps']))(run))
    running = _RUNNING.get(run_id)
    for step_id, step in lesson['steps'].items():
        existing = next((r for r in observed['receipts'] if r['step_id'] == step_id), None)
        reason, argv = None, None
        try:
            argv = step.argv(run)
            if step.precondition and not existing and step_id in applicable:
                if blocked_before:
                    reason = f'先完成「{blocked_before}」'
                else:
                    if snapshot is None:
                        snapshot = read_snapshot()
                    checked = step.precondition(run, snapshot)
                    if isinstance(checked, str):
                        reason = checked
        except Exception as exc:
            reason = str(exc)
        if step_id not in applicable and not existing:
            reason = reason or '這次實驗的參數不適用此步'
        if reason and not existing and step_id in applicable and blocked_before is None:
            blocked_before = lesson['labels'].get(step_id, step_id)
        if running and running['action'] == step_id and existing is None:
            badge, detail = '命令執行中', f"已送出 {int(now - running['started'])} 秒，外部命令進行中（最長 {running['timeout']} 秒）"
        else:
            badge, detail = _step_status(lesson, step_id, existing, reason, observed, now)
        outputs = []
        if existing and existing.get('job_id'):
            for log in observed['outputs'].get(existing['job_id'], []):
                if log['text'] is None:
                    continue  # not written yet (job still pending) or unreadable: nothing to show
                outputs.append({'name': Path(log['path']).name, 'text': log['text'], 'truncated': log.get('truncated', False)})
        timeline = None
        if step_id in lesson.get('timeline', ()):
            record = _call(lambda: lab.read_timeline(run_id, step_id))
            if record:
                timeline = _timeline_text(record) if 'samples' in record else f"狀態時間軸讀取失敗：{record.get('error')}"
        result[step_id] = {'badge': badge, 'detail': detail, 'state': _four_state(badge), 'receipt': existing,
                           'argv': argv, 'outputs': outputs, 'timeline': timeline}
    return result


# ---- actions -------------------------------------------------------------------------

def busy(run_id):
    return _RUNNING.get(run_id)


def last_event(run_id):
    return LAST_EVENT.get(run_id)


def start(lesson, run_id, action, *, typed=''):
    """Start one action ('<step id>', 'verify' or 'cleanup') in a daemon thread; never waits for it."""
    if action == VERIFY:
        label, timeout, perform = '驗證並保存', 60, lambda: lab.verify_run(run_id)
    elif action == CLEANUP:
        label, timeout, perform = '只清理本次實驗', 120, lambda: lab.cleanup_run(run_id)
    elif action in lesson['steps']:
        step = lesson['steps'][action]
        label, timeout = lesson['labels'].get(action, action), _timeout(step.effect)
        phrase = lesson.get('confirmations', {}).get(action)
        if phrase and typed != phrase:
            message = f'必須先在此步驟的輸入框輸入 {phrase} 並按 Enter。'
            LAST_EVENT[run_id] = {'status': 'blocked', 'label': label, 'action': action, 'reason': message,
                                  'finished_at': datetime.now().astimezone().strftime('%H:%M:%S')}
            return 'blocked', message

        def perform():
            frozen = lab.load_run(run_id)
            return lab.execute_once(run_id, action, step.argv(frozen), effect=step.effect, timeout=timeout)
    else:
        raise ValueError(f'未知的動作：{action}')
    with _RUNNING_LOCK:
        current = _RUNNING.get(run_id)
        if not current:
            _RUNNING[run_id] = {'label': label, 'action': action, 'started': time.time(), 'timeout': timeout}
    if current:
        return 'busy', f"「{current['label']}」仍在執行（已 {int(time.time() - current['started'])} 秒）；它結束後再按。"

    def worker():
        try:
            result = _call(perform)
            if result.get('status') == 'succeeded' and result.get('job_id') and action in lesson.get('timeline', ()):
                failed = _call(lambda: lab.start_timeline(run_id, action, str(result['job_id'])))
                if failed:
                    result = {**result, 'reason': f"狀態時間軸沒有啟動：{failed.get('error')}"}
        finally:
            with _RUNNING_LOCK:
                _RUNNING.pop(run_id, None)
        LAST_EVENT[run_id] = {**result, 'label': label, 'action': action,
                              'finished_at': datetime.now().astimezone().strftime('%H:%M:%S')}

    LAST_EVENT[run_id] = {'status': 'submitted', 'label': label, 'action': action, 'timeout': timeout,
                          'submitted_at': datetime.now().astimezone().strftime('%H:%M:%S')}
    threading.Thread(target=worker, daemon=True).start()
    return 'started', f'「{label}」已送出，背景執行中（最長 {timeout} 秒）。'
