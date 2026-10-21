"""Chapter 05 controls and read-only MPI evidence, with isolated updates."""
from pathlib import Path

import notebook_lab as lab
from environment_view import _terminal
from lesson_common import Pending, json_lines, receipt
from lessons_cpu import _mpi_verify
from notebook_views import json_view, table_rows
from slurm_cli import compose_argv, run_command


def mpi_controls(mo, lesson, run_id):
    initial, setup_error = {}, None
    if run_id:
        try:
            initial = lab.read_run(run_id)
        except Exception as exc:
            setup_error = str(exc)
    previous = receipt(initial, 'mpi') if 'receipts' in initial else None
    get_submit, set_submit = mo.state(previous)
    get_snapshot, set_snapshot = mo.state(None)

    def submit(_):
        try:
            run = lab.load_run(run_id)
            step = lesson['steps']['mpi']
            result = lab.execute_once(run_id, 'mpi', step.argv(run), effect=step.effect)
        except Exception as exc:
            result = {'status': 'failed', 'error': str(exc)}
        set_submit(result)

    def observe(_):
        try:
            result = mpi_snapshot(run_id)
        except Exception as exc:
            result = {'error': str(exc)}
        set_snapshot(result)

    return {'submit': mo.ui.button(label='提交兩節點 MPI 工作', disabled=not run_id, on_click=submit),
            'observe': mo.ui.button(label='查看工作狀態與兩個 rank 的結果', disabled=not run_id, on_click=observe),
            'get_submit': get_submit, 'get_snapshot': get_snapshot, 'setup_error': setup_error}


def submit_result(mo, lesson, run_id, result):
    if not run_id:
        return mo.md('先建立實驗，這裡會顯示實際提交指令。')
    panels = []
    if result:
        panels.append(mo.plain_text('提交操作：' + str(result.get('status', '未確認')) + ' · ' + str(
            result.get('reason') or result.get('error') or
            ('Job ID：' + str(result['job_id']) if result.get('job_id') else '請核對回應。'))))
    if result and result.get('argv'):
        record, pending = result, False
    else:
        try:
            record = {'argv': lesson['steps']['mpi'].argv(lab.load_run(run_id))}
        except Exception as exc:
            record = {'error': str(exc)}
        pending = True
    panels.append(_terminal(mo, 'sbatch / 兩節點 MPI', record, pending=pending, blank_stdout=True,
        note='按按鈕才會提交。stdout 的 Job ID 與 exit 0 只表示提交成功；MPI 計算輸出要按下一段觀察按鈕讀取。'
             '重按提交只讀回本次原紀錄；想重跑請建立新實驗。'))
    return mo.vstack(panels)


def query_commands(identifier):
    return {'squeue / 執行與排隊狀態': compose_argv('squeue', '--jobs=' + identifier,
                    '--format=%.18i %.12T %.6D %.6C %.12M %N %R'),
            'scontrol / 工作配置': compose_argv('scontrol', 'show', 'job', identifier)}


def evidence_status(data):
    """Use the lesson's real verifier without writing a report or changing jobs."""
    saved = receipt(data, 'mpi')
    if not saved or saved.get('status') != 'succeeded' or not saved.get('job_id'):
        return {'status': 'waiting', 'reason': '尚無已確認的 MPI 提交回條。'}
    try:
        _mpi_verify(data)
        logs = data['outputs'].get(saved['job_id'], [])
        stdout = [item for item in logs if item['path'].endswith('.out')]
        if data.get('errors') or not stdout or any(
                item.get('status') != 'ok' or item.get('truncated') for item in stdout):
            raise ValueError('輸出讀取有錯誤、缺失或截斷，不能當作完整 MPI 證據。')
    except Pending as exc:
        return {'status': 'waiting', 'reason': str(exc)}
    except (AssertionError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'unconfirmed', 'reason': str(exc)}
    return {'status': 'ready', 'reason': '本次取樣符合兩節點、rank 0／1、sum=3 與工作成功條件；可以驗證並保存。'}


def mpi_snapshot(run_id):
    data = lab.read_run(run_id)
    saved = receipt(data, 'mpi') or {}
    identifier = saved.get('job_id')
    commands, rows, ranks, logs = {}, [], [], []
    if identifier:
        for title, argv in query_commands(identifier).items():
            try:
                result = run_command(argv, cwd=lab.ROOT, timeout=10)
                commands[title] = dict(argv=argv, returncode=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr)
            except Exception as exc:
                commands[title] = dict(argv=argv, error=str(exc))
        observed = data['jobs'].get(identifier, {})
        trusted = observed.get('status') == 'observed'
        for job in observed.get('records', []) if trusted else []:
            code = job.get('exit_code') or {}
            rows.append({'Job ID': identifier, '狀態': ', '.join(job['job_state']),
                         '節點': job.get('nodes'), 'UID': job.get('user_id'),
                         '等待原因': job.get('state_reason'), '退出碼': code.get('return_code'),
                         'Signal': (code.get('signal') or {}).get('id')})
        if not rows:
            rows.append({'Job ID': identifier, '狀態': observed.get('status', '尚無可信紀錄')})
        logs = data['outputs'].get(identifier, [])
        for log in logs:
            if log['path'].endswith('.out') and log.get('status') == 'ok':
                for value in json_lines(log.get('text') or ''):
                    ranks.append({key: value.get(key) for key in ('rank', 'hostname', 'size', 'sum', 'valid')})
    return {'run_id': run_id, 'observed_at': data['observed_at'], 'commands': commands,
            'rows': rows, 'ranks': ranks, 'logs': logs, 'errors': data['errors'],
            'evidence': evidence_status(data)}


def snapshot_result(mo, sample, submission=None):
    if not sample:
        identifier = (submission.get('job_id') if submission and submission.get('status') == 'succeeded' else None)
        return mo.vstack([_terminal(mo, title, {'argv': argv}, pending=True, blank_stdout=True,
            note='按上方觀察按鈕才會執行查詢；不會提交或重送。' if identifier else
                 '<JOB_ID> 是佔位文字。先提交，再按上方觀察按鈕；不會自動提交或重送。')
            for title, argv in query_commands(identifier or '<JOB_ID>').items()])
    if sample.get('error'):
        return mo.plain_text('查詢失敗：' + sample['error'])
    panels = [mo.plain_text('取樣時間：' + sample['observed_at'] + '；只在按觀察按鈕時更新。')]
    for title, command in sample['commands'].items():
        panels.append(_terminal(mo, title, command, blank_stdout=True,
            note='完成的工作會從 squeue 消失；scontrol 若已不保留紀錄，也不能用缺失推論成功。'))
    if sample['rows']:
        panels.append(mo.ui.table(table_rows(sample['rows']), selection=None))
    else:
        panels.append(mo.md('尚未取得本次 Job ID；先提交 MPI 工作。'))
    panels.append(mo.plain_text(sample['evidence']['reason']))
    for log in sample['logs']:
        panels.append(_terminal(mo, Path(log['path']).name,
            {'stderr' if log['path'].endswith('.err') else 'stdout': log.get('text') or '',
             'error': log.get('error') if log.get('status') != 'ok' else None}, blank_stdout=True,
            stdin_note='（讀取本次工作的輸出檔）' + log['path'],
            note='這是 MPI 程式的輸出；' + ('內容已截斷，不能當完整證據。' if log.get('truncated') else
                  '兩行出現順序不固定，rank 1 先印出也正常。')))
    if sample['ranks']:
        panels.extend([mo.md('### 將程式的 rank JSON 整理成表格'),
                       mo.ui.table(table_rows(sample['ranks']), selection=None)])
    if sample['errors']:
        panels.append(mo.accordion({'查詢／路徑錯誤': json_view(mo, sample['errors'])}))
    return mo.vstack(panels)


def report_result(mo, run_id, event):
    if not run_id:
        return mo.md('建立實驗後，這裡會顯示驗證報告。')
    panels = []
    if event:
        panels.append(mo.plain_text('操作結果：' + str(event.get('status', '已返回')) + ' · ' +
            str(event.get('reason') or event.get('error') or '請對照報告。')))
    try:
        data = lab.read_run(run_id)
        panels.append(mo.plain_text('報告：' + str((data.get('report') or {}).get('status', '尚未驗證'))))
        panels.append(mo.accordion({'完整驗證報告': json_view(mo, data.get('report')),
            '提交回條／unknown 診斷': json_view(mo, data['receipts']),
            '讀取錯誤': json_view(mo, data['errors'])}))
    except Exception as exc:
        panels.append(mo.plain_text('讀取報告失敗：' + str(exc)))
    return mo.vstack(panels)


def source_result(mo):
    return mo.accordion({name: mo.md('```' + ('c' if name.endswith('.c') else 'bash') + '\n' +
        (lab.ROOT / 'examples' / name).read_text(encoding='utf-8') + '\n```')
        for name in ('mpi.sbatch', 'mpi_sum.c')}, multiple=True)
