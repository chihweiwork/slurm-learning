"""End-of-chapter cleanup checklist: read-only, shows what is still left behind before leaving a chapter.

collect() runs read-only queries and never raises; evaluate() is pure and decides ✓ / ⚠ / —.
Nothing here cancels, resumes or deletes anything.
"""
from datetime import datetime
import json

from notebook_lab import DEMOS, ROOT
from notebook_queries import query_nodes
from notebook_views import result_table
from slurm_cli import compose_argv, run_command

OWN_PREFIXES = ('demo-', 'course-')
# Chapters with demo runs (course_runner lessons); 00, 01, 03 and 10 have none, so checks 4–5 do not apply.
DEMO_CHAPTERS = frozenset({'02', '04', '05', '06', '07', '08', '09'})
_BAD_NODE = ('DRAIN', 'DOWN', 'FAIL', 'NOT_RESPONDING')


def _read_json(path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def course_run_ids():
    """Run ids that some learning record (shared/course/<token>/progress.json) created, current or retired by
    「重新開始示範」; excludes old-course and smoke runs."""
    import course_progress
    found = set()
    for token in course_progress.list_tokens():
        try:
            chapters = course_progress.load(token)['chapters']
        except (OSError, ValueError):
            continue
        for data in chapters.values():
            found.update(value for value in (data.get('runs') or {}).values() if isinstance(value, str))
            found.update(value for value in data.get('retired_runs') or [] if isinstance(value, str))
    return found


def load_runs(chapter, demos=DEMOS, allowed=None):
    """This chapter's teaching runs: whether they acted, their report status and whether cleanup succeeded.

    `allowed` limits the result to those run ids (the course passes course_run_ids())."""
    runs = []
    if not demos.is_dir():
        return runs
    for directory in sorted(demos.iterdir()):
        if allowed is not None and directory.name not in allowed:
            continue
        run = _read_json(directory / 'run.json') if directory.is_dir() and not directory.is_symlink() else None
        if not run or not str(run.get('chapter', '')).startswith(chapter + '-'):
            continue
        report = _read_json(directory / 'report.json') or {}
        attempts = report.get('cleanup_attempts') or []
        actions = directory / 'actions'
        runs.append({'run_id': directory.name,
                     'acted': actions.is_dir() and any(actions.iterdir()),
                     'report': report.get('status', '缺失'),
                     'cleaned': bool(attempts) and not attempts[-1].get('errors'),
                     'verified': bool(report.get('verification'))})
    return runs


def _lines(argv):
    result = run_command(argv, cwd=ROOT, timeout=15)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f'exit {result.returncode}')
    return [line for line in result.stdout.splitlines() if line.strip()]


def collect(chapter):
    """Raw inputs for evaluate(); every query failure is captured as an error string."""
    data = {'observed_at': datetime.now().astimezone().strftime('%H:%M:%S'), 'chapter': chapter}
    try:
        data['queue'] = [dict(zip(('job_id', 'name', 'user', 'state', 'reason'), line.split('|', 4)))
                         for line in _lines(compose_argv('squeue', '--all', '--noheader', '--format=%i|%j|%u|%T|%R'))]
    except (OSError, ValueError) as exc:
        data['queue'], data['queue_error'] = None, str(exc)
    nodes = query_nodes()
    if nodes['status'] == 'ok':
        data['nodes'] = [{'name': n['name'], 'state': n['state'], 'reason': n['reason']} for n in nodes['data']]
    else:
        data['nodes'], data['nodes_error'] = None, '; '.join(nodes.get('errors') or []) or nodes['status']
    try:
        data['accounts'] = [line.split('|', 1)[0] for line in
                            _lines(compose_argv('sacctmgr', '--noheader', '--parsable2', 'show', 'account', 'format=Account'))]
    except (OSError, ValueError) as exc:
        data['accounts'], data['accounts_error'] = None, str(exc)
    data['runs'] = load_runs(chapter, allowed=course_run_ids()) if chapter in DEMO_CHAPTERS else None
    return data


def _item(name, result, text):
    return {'項目': name, '結果': result, '說明': text}


def _jobs(rows):
    return '、'.join(f"{r['job_id']} {r['name']}（{r['state']}）" for r in rows)


def evaluate(data):
    """Fixed checks; ✓ nothing left, ⚠ needs your attention, — not applicable or unknown.

    Checks 4–5 (this chapter's demo runs) appear only when data['runs'] is a list, i.e. the chapter has demos."""
    items = []
    queue = data.get('queue')
    if queue is None:
        items.append(_item('1 自己的 active job', '—', f"查詢失敗，無法確認：{data.get('queue_error')}"))
    else:
        own = [r for r in queue if r['name'].startswith(OWN_PREFIXES)]
        others = [r for r in queue if r not in own]
        note = f'；另有不是你的工作，不要動：{_jobs(others)}' if others else ''
        items.append(_item('1 自己的 active job', '⚠' if own else '✓',
                           (f'還在：{_jobs(own)}。教材 run 用該章「只清理本次實驗」；練習工作用 scancel 你自己的 job ID' if own
                            else '沒有你的工作在 queue 裡') + note))
    nodes = data.get('nodes')
    if nodes is None:
        items.append(_item('2 節點 DRAIN／DOWN', '—', f"查詢失敗，無法確認：{data.get('nodes_error')}"))
    else:
        bad = [n for n in nodes if any(flag in state for state in n['state'] for flag in _BAD_NODE)]
        texts = [f"{n['name']} {'+'.join(n['state'])} Reason={n['reason'] or '（空）'}："
                 + ('你的維護還沒恢復，確認後 RESUME' if n['reason'].startswith(OWN_PREFIXES)
                    else '別人的維護或故障：不要動，必要時回報') for n in bad]
        items.append(_item('2 節點 DRAIN／DOWN', '⚠' if bad else '✓', '；'.join(texts) or '所有節點都可排程'))
    accounts = data.get('accounts')
    if accounts is None:
        items.append(_item('3 臨時 account', '—', f"accounting 未啟用或查詢失敗：{data.get('accounts_error')}"))
    else:
        demo = [a for a in accounts if a.startswith('demo-')]
        items.append(_item('3 臨時 account', '⚠' if demo else '✓',
                           f"還在：{'、'.join(demo)}；用第 08 章該 run 的「只清理本次實驗」刪除" if demo else '沒有 demo-* account'))
    runs = data.get('runs')
    if runs is None:
        return items
    acted = [r for r in runs if r['acted']]
    dirty = [r for r in acted if not r['cleaned']]
    items.append(_item('4 本章實驗目錄', '⚠' if dirty else '✓',
                       f"尚未成功清理：{'、'.join(r['run_id'] for r in dirty)}；在該章收尾區按「只清理本次實驗」" if dirty
                       else f'{len(acted)} 個示範 run 都已清理（證據保留在 shared/demos/）' if acted
                       else '還沒按過示範按鈕，沒有要清理的'))
    unverified = [r for r in acted if r['report'] != 'passed']
    # A failed report, or an unverified run that was never cleaned, needs attention; cleaned-but-unverified is history.
    problem = [r for r in unverified if r['report'] == 'failed' or not r['cleaned']]
    items.append(_item('5 report 狀態', '⚠' if problem else ('—' if unverified else '✓'),
                       '；'.join(f"{r['run_id']}：{_report_text(r)}" for r in unverified)
                       + ('。failed 看該章示範卡片的輸出找原因' if any(r['report'] == 'failed' for r in unverified) else '')
                       or ('都已 passed' if acted else '還沒有要驗證的示範')))
    return items


def _report_text(run):
    cleaned = '（已清理）' if run['cleaned'] else ''
    if run['report'] == 'running' and not run.get('verified'):
        return f'還沒按過「驗證並保存」{cleaned}——回該章收尾區補按（工作結束後約 1 小時內都還查得到）'
    if run['report'] == 'running':
        return f'驗證時還有步驟沒做或工作沒結束{cleaned}——做完後再按一次「驗證並保存」'
    return f"{run['report']}{cleaned}"


def closing_panel(mo, chapter, refresh_value=None):
    """Read-only checklist element; refresh_value is only a dependency hook for a re-check button."""
    data = collect(chapter)
    items = evaluate(data)
    warnings = [i for i in items if i['結果'] == '⚠']
    advice = (mo.md('**還有東西沒收：** ' + '；'.join(i['項目'] for i in warnings)
                    + '。只處理你自己的工作、Reason 與 account；不要 scancel 或 RESUME 別人的。').callout(kind='warn')
              if warnings else mo.md('沒有留下需要你處理的東西，可以離開本章。').callout(kind='success'))
    return mo.vstack([mo.md(f"### 收尾清單（離開本章前）\n唯讀檢查，快照 {data['observed_at']}；不會自動取消或刪除任何東西。"),
                      result_table(mo, items, title='收尾檢查'), advice])
