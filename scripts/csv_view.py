"""Chapter 04: stable step controls and independent pipeline observations."""
import json
from pathlib import Path

import notebook_lab as lab
from environment_view import _terminal
from lesson_common import receipt
from notebook_queries import read_log
from notebook_views import json_view, table_rows
from slurm_cli import compose_argv, run_command


SUCCESS = ('prepare', 'array', 'aggregate')
RECOVERY = ('prepare', 'backup', 'inject', 'array', 'aggregate', 'missing-aggregate',
            'cancel-dependent', 'repair-input', 'repair-shard', 'aggregate-repaired')
ALL_STEPS = RECOVERY
TITLES = {
    'prepare': '準備四份 CSV 輸入', 'backup': '備份第 2 號分片',
    'inject': '刻意把第 2 號分片改壞', 'array': '提交四個 worker task',
    'aggregate': '提交要等待 worker 成功的彙總工作',
    'missing-aggregate': '確認程式會拒絕缺片的結果',
    'cancel-dependent': '保存失敗證據，取消原本等待中的彙總工作',
    'repair-input': '還原第 2 號分片的輸入', 'repair-shard': '只重跑第 2 號 worker',
    'aggregate-repaired': '提交新的彙總工作，等待修復完成',
}
EXPLANATIONS = {
    'prepare': '在本次實驗目錄建立 input/shard-0.csv 到 shard-3.csv，各 1000 筆。'
               '這一步在 Ubuntu 準備共享檔案，不提交 Slurm 工作。完成後可按下方「查看第一階段工作與檔案」先看輸入。',
    'backup': '備份 input/shard-2.csv 到 shard-2.backup.csv，稍後用它還原；仍然是本地檔案操作。',
    'inject': '把 shard-2.csv 第一筆資料的 value 改成 bad-value。資料列從 0 起算，所以指令裡的 row=0 是第一筆資料，不是 CSV 標題。',
    'array': '以 --array=0-3%2 一次提交 index 0、1、2、3 四個 task，同時最多執行兩個。'
             '每個 task 申請 1 CPU、128 MiB RAM，讀取對應 CSV，產生 partials/編號.json。'
             'stdout 是 array 的提交編號；不是四個 task 都已成功的意思。',
    'aggregate': '依賴的是整個 array：--dependency=afterok:ARRAY_JOB_ID。'
                 '可在 worker 還沒完成時就提交；Slurm 會等四個 task 全部成功，才允許彙總程式啟動。'
                 '提交後按下一段觀察按鈕查看每個 task 的結果。',
    'missing-aggregate': '先在第一階段觀察中確認 index 2 FAILED、其他三個 COMPLETED，原彙總工作仍 PENDING。'
                         '本步另外提交一個沒有 dependency 的彙總工作，測試程式自身會不會拒絕缺片資料。'
                         '它預期 FAILED，.err 應指出缺少 partials/2.json；不應產生 summary.json。'
                         '提交後再更新第一階段觀察，確認它失敗，才進入下一步。',
    'cancel-dependent': '重新確認 worker 失敗、彙總被 dependency 擋住，以及缺片測試已失敗，再保存證據並 scancel 原彙總 Job ID。'
                        '取消後可更新第一階段觀察，直到原彙總工作 CANCELLED。',
    'repair-input': '把備份複製回 input/shard-2.csv。只有原彙總工作確實 CANCELLED 後才可執行。'
                    '同時保存另外三個成功 partial 的內容，驗證時會確認它們未被改寫。',
    'repair-shard': '使用 --array=2 建立新的 array，只執行 index 2。它不是重跑四個 task，也不是沿用原失敗工作的 Job ID。',
    'aggregate-repaired': '建立新的 aggregate，afterok 依賴的是新的修復工作。'
                         '原彙總工作的依賴不會因補跑一個新工作自動修好，所以需要新的提交。'
                         '完成後按下方「查看修復後工作與檔案」。',
}
FILES = ('manifest.json', *(f'input/shard-{i}.csv' for i in range(4)),
         *(f'partials/{i}.json' for i in range(4)), 'summary.json')


def visible_steps(mode):
    if mode == 'success':
        return SUCCESS
    if mode == 'failure-recovery':
        return RECOVERY
    return ()


def csv_controls(mo, lesson, run_id):
    """Buttons are created once per run; each callback updates one result only."""
    mode, initial, setup_error = None, {}, None
    if run_id:
        try:
            mode = lab.load_run(run_id)['parameters']['mode']
            initial = lab.read_run(run_id)
        except Exception as exc:
            setup_error = str(exc)
    getters, setters, buttons = {}, {}, {}
    for key in (*ALL_STEPS, 'observe-initial', 'observe-final', 'report'):
        previous = receipt(initial, key) if initial.get('receipts') and key in lesson['steps'] else None
        getters[key], setters[key] = mo.state(previous)

    def action(step_id):
        def callback(_):
            if step_id not in visible_steps(mode):
                setters[step_id]({'status': 'blocked', 'reason': '這個步驟不適用目前模式；請另建對應模式的實驗。'})
                return
            try:
                run = lab.load_run(run_id)
                step = lesson['steps'][step_id]
                outcome = lab.execute_once(run_id, step_id, step.argv(run), effect=step.effect)
            except Exception as exc:
                outcome = {'status': 'failed', 'error': str(exc)}
            setters[step_id](outcome)
        return callback

    for key in ALL_STEPS:
        buttons[key] = mo.ui.button(label=TITLES[key], on_click=action(key), disabled=key not in visible_steps(mode))

    def observe(key):
        def callback(_):
            try:
                result = pipeline_snapshot(run_id)
            except Exception as exc:
                result = {'error': str(exc)}
            setters[key](result)
        return callback

    for key, label in [('observe-initial', '查看第一階段工作與檔案'), ('observe-final', '查看修復後工作與檔案')]:
        buttons[key] = mo.ui.button(label=label, on_click=observe(key),
                                    disabled=mode is None or (key == 'observe-final' and mode != 'failure-recovery'))
    buttons['report'] = mo.ui.button(label='更新驗證報告', disabled=not run_id,
                                     on_click=lambda _: setters['report'](lambda value: (value or 0) + 1))
    return {'mode': mode, 'setup_error': setup_error, 'buttons': buttons, 'getters': getters}


def step_heading(mo, step_id, mode, button):
    order = visible_steps(mode)
    if step_id not in order:
        return mo.md('')
    return mo.vstack([mo.md(f'## {order.index(step_id) + 1}．{TITLES[step_id]}\n\n{EXPLANATIONS[step_id]}'), button])


PREVIEW_DEPENDENCIES = {
    'aggregate': ('array', '<ARRAY_JOB_ID>'),
    'cancel-dependent': ('aggregate', '<AGGREGATE_JOB_ID>'),
    'aggregate-repaired': ('repair-shard', '<REPAIR_JOB_ID>'),
}


def command_preview(lesson, run_id, step_id, prerequisite=None):
    """Build display-only argv; never query Slurm or execute an operation."""
    run = {**lab.load_run(run_id), 'receipts': []}
    note = '尚未執行。按上方按鈕後，這裡才會顯示實際 stdout；預覽不會執行指令。'
    if step_id in PREVIEW_DEPENDENCIES:
        parent, placeholder = PREVIEW_DEPENDENCIES[step_id]
        confirmed = (prerequisite and prerequisite.get('status') == 'succeeded'
                     and prerequisite.get('job_id'))
        # These placeholders are used only in this display copy. Execution
        # loads the real run and checks durable receipts and preconditions.
        run['receipts'] = [{'step_id': parent, 'status': 'succeeded',
                            'job_id': prerequisite['job_id'] if confirmed else placeholder}]
        if not confirmed:
            note += f' {placeholder} 是佔位文字；先完成「{TITLES[parent]}」，取得 ID 後會自動替換。'
    return {'argv': lesson['steps'][step_id].argv(run)}, note


def step_result(mo, step_id, mode, result, lesson, run_id, prerequisite=None):
    if step_id not in visible_steps(mode):
        return mo.md('')
    panels = []
    if result:
        panels.append(mo.plain_text('操作結果：' + str(result.get('status', '未確認')) + ' · ' + str(
            result.get('reason') or result.get('error') or
            ('Job ID：' + str(result['job_id']) if result.get('job_id') else '操作已返回。'))))
    if result and result.get('argv'):
        panels.append(_terminal(mo, TITLES[step_id], result,
            blank_stdout=True,
            note='這是已保存的操作回應；sbatch exit 0 只代表提交成功。重按同一步驟只會讀回原紀錄，不會重送。'))
    else:
        try:
            preview, note = command_preview(lesson, run_id, step_id, prerequisite)
            panels.append(_terminal(mo, TITLES[step_id], preview,
                                    pending=True, blank_stdout=True, note=note))
        except Exception as exc:
            panels.append(_terminal(mo, TITLES[step_id], {'error': str(exc)},
                pending=True, blank_stdout=True, stdin_note='無法準備指令，請檢查實驗設定。'))
    return mo.vstack(panels)


def job_rows(data):
    rows = []
    for saved in data.get('receipts', []):
        if saved['step_id'] not in {'array', 'aggregate', 'missing-aggregate', 'repair-shard', 'aggregate-repaired'}:
            continue
        parent = saved.get('job_id')
        observed = data['jobs'].get(parent, {})
        common = {'工作': TITLES[saved['step_id']], '提交 Job ID': parent or '未確認'}
        records = observed.get('records', []) if observed.get('status') == 'observed' else []
        if not records:
            rows.append({**common, 'Task': '未確認', '狀態': observed.get('status', '尚未取得紀錄')})
        for job in records:
            index = job.get('array_task_id')
            code = job.get('exit_code') or {}
            rows.append({**common, 'Task': f'{parent}_{index}' if index is not None else str(job['job_id']),
                         '狀態': ', '.join(job['job_state']), '等待原因': job.get('state_reason'),
                         '依賴': job.get('dependency'), '節點': job.get('nodes') or '尚未分配',
                         '退出碼': code.get('return_code'), 'Signal': (code.get('signal') or {}).get('id')})
    return rows


def pipeline_snapshot(run_id):
    data = lab.read_run(run_id)
    ids = sorted({r['job_id'] for r in data['receipts'] if r.get('job_id')})
    command = None
    if ids:
        argv = compose_argv('squeue', '--jobs=' + ','.join(ids),
                            '--format=%.18i %.12T %.6C %.12M %R')
        try:
            result = run_command(argv, cwd=lab.ROOT, timeout=10)
            command = dict(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except Exception as exc:
            command = dict(argv=argv, error=str(exc))
    files = {name: read_log(Path(data['run_dir']), 'pipeline/' + name) for name in FILES}
    return {'observed_at': data['observed_at'], 'mode': data['parameters']['mode'],
            'command': command, 'rows': job_rows(data), 'files': files,
            'outputs': data['outputs'], 'errors': data['errors'], 'run_id': run_id}


def _json_file(record):
    if record.get('status') != 'ok' or record.get('truncated'):
        return None
    try:
        value = json.loads(record.get('text') or '')
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def observation_result(mo, result):
    if not result:
        return mo.md('尚未取樣；按本段觀察按鈕查詢，不會提交新工作。')
    if result.get('error'):
        return mo.plain_text('觀察失敗：' + result['error'])
    panels = [mo.plain_text('取樣時間：' + result['observed_at'] + '；這份取樣只在重按本段按鈕時更新。')]
    if result['command']:
        panels.append(_terminal(mo, 'squeue / 仍在執行或等待的工作', result['command'],
            note='結束的工作會從 squeue 消失。下表是另外查詢 scontrol 的保留紀錄，兩次查詢之間狀態可能改變。'))
    if result['rows']:
        panels.append(mo.ui.table(table_rows(result['rows']), selection=None))
    else:
        panels.append(mo.md('尚無已提交工作；準備 CSV 與備份等檔案操作不會產生 Job ID。'))
    partial_rows = []
    for index in range(4):
        record = result['files'][f'partials/{index}.json']
        value = _json_file(record)
        partial_rows.append({'分片 index': index, '檔案狀態': '無有效 JSON' if record['status'] == 'ok' and value is None else record['status'],
                             'row_count': value.get('row_count') if value else None,
                             'value_sum': value.get('value_sum') if value else None})
    panels.extend([mo.md('### 四份部分結果（partials）'), mo.ui.table(table_rows(partial_rows), selection=None)])
    summary = result['files']['summary.json']
    value = _json_file(summary)
    if value:
        panels.append(mo.md(f"**summary.json：** shards＝`{value.get('shards')}`、row_count＝`{value.get('row_count')}`、value_sum＝`{value.get('value_sum')}`。\n\n預期為 4、4000、16004000；最後仍需按「驗證並保存」核對整個實驗。"))
    else:
        panels.append(mo.md('**尚無可讀的 summary.json。** 尚未彙總或刻意製造失敗時，這可能是預期狀態；請對照上方工作狀態。'))
    previews = {}
    for name, record in result['files'].items():
        text = record.get('text') or ''
        is_csv = name.endswith('.csv')
        if is_csv:
            text = '\n'.join(text.splitlines()[:6])
        previews[name] = _terminal(mo, name, {'stdout': text,
            'error': record.get('error') if record['status'] != 'ok' else None},
            stdin_note='（讀取共享檔案）' + 'pipeline/' + name,
            note='只預覽標題與前五筆資料。' if is_csv else '直接讀取檔案，沒有額外執行 cat；missing 表示檔案尚不存在。')
    panels.append(mo.accordion({'輸入／partial／summary 的檔案內容': mo.accordion(previews, multiple=True)}))
    logs = {}
    for identifier, records in result['outputs'].items():
        for record in records:
            path = record['path']
            logs[f'Job {identifier} · {Path(path).name}'] = _terminal(mo, Path(path).name,
                {'stderr' if path.endswith('.err') else 'stdout': record.get('text') or '',
                 'error': record.get('error') if record['status'] != 'ok' else None},
                stdin_note='（讀取 Slurm 輸出檔）' + path,
                note='worker／aggregate 程式的輸出；FAILED 時先看 .err。空白 .err 不足以證明成功。')
    if logs:
        panels.append(mo.accordion({'各工作的 stdout／stderr': mo.accordion(logs, multiple=True)}))
    if result['errors']:
        panels.append(mo.accordion({'讀取或路徑錯誤': json_view(mo, result['errors'])}))
    return mo.vstack(panels)


def report_panel(mo, run_id, event):
    if not run_id:
        return mo.md('建立實驗後，這裡會顯示驗證報告。')
    panels = []
    if event:
        panels.append(mo.plain_text('建立／驗證／清理結果：' + str(event.get('status', '已返回')) + ' · ' +
                                    str(event.get('reason') or event.get('error') or '請對照驗證報告。')))
    try:
        data = lab.read_run(run_id)
        panels.append(mo.plain_text('驗證報告：' + str((data.get('report') or {}).get('status', '尚未確認'))))
        panels.append(mo.accordion({'完整驗證報告': json_view(mo, data.get('report')),
                                    '指令回條／失敗與修復證據': json_view(mo, data['receipts'])}))
    except Exception as exc:
        panels.append(mo.plain_text('讀取報告失敗：' + str(exc)))
    return mo.vstack(panels)


def source_panel(mo):
    sources = {}
    for name in ('pipeline-worker.sbatch', 'pipeline-aggregate.sbatch', 'pipeline.py'):
        path = lab.ROOT / 'examples' / name
        language = 'python' if name.endswith('.py') else 'bash'
        sources[name] = mo.md(f'```{language}\n{path.read_text(encoding="utf-8")}\n```')
    return mo.accordion(sources, multiple=True)
