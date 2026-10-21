"""marimo controls: all external mutations live in synchronous button callbacks."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex

import notebook_lab as lab
from notebook_queries import read_history, read_snapshot, read_log as preview_file
from notebook_views import navigation, json_view, table_rows


def _call(callback):
    try:
        return callback()
    except Exception as exc:
        return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}


def setup_controls(mo, lesson):
    get_run, set_run = mo.state(None)
    # Only button/form callbacks set this state; rerendering controls is read-only.
    get_event, set_event = mo.state(None, allow_self_loops=True)
    fields = lesson.get('fields') or {'practice': ['標準實驗']}
    submit_chapter = lesson['chapter'] == '02-submit'
    single_setup = lesson['chapter'] in {'02-submit', '03-queue', '04-csv', '05-mpi'}
    manual_observation = lesson['chapter'] in {'04-csv', '05-mpi'}

    def create_with_parameters(value):
        if value is None:
            return
        result = _call(lambda: lab.prepare_run(lesson['chapter'], value))
        if result.get('run_id'):
            set_run(result['run_id'])
        set_event(result)

    labels = {'node': '執行節點', 'cpus': '每個 task 申請的 CPU 數'} if submit_chapter else (
        {'mode': '實驗路徑'} if lesson['chapter'] == '04-csv' else
        {'practice': '實驗設定'} if lesson['chapter'] == '05-mpi' else {})
    form = mo.md('\n\n'.join(f'**{labels.get(name, name)}** {{{name}}}' for name in fields)).batch(**{
        name: mo.ui.dropdown(values, value=values[0]) for name, values in fields.items()
    }).form(submit_button_label='套用參數並建立實驗' if single_setup else '凍結參數（不提交工作）',
            on_change=create_with_parameters if single_setup else
            lambda value: set_event({'status': 'parameters-ready', 'parameters': value}))

    def create(_):
        if form.value is None:
            result = {'status': 'blocked', 'reason': '先送出參數 form；此動作不提交 Slurm 工作。'}
        else:
            result = _call(lambda: lab.prepare_run(lesson['chapter'], form.value))
            if result.get('run_id'):
                set_run(result['run_id'])
        set_event(result)
        return result

    create_buttons = [] if single_setup else [mo.ui.button(label='建立實驗', on_click=create)]
    choices = {'未選擇': ''}
    for entry in read_history():
        if entry.get('source') != 'demos' or not entry.get('run_id'):
            continue
        try:
            run = lab.load_run(entry['run_id'])
            if run['chapter'] == lesson['chapter']:
                choices[run['run_id']] = run['run_id']
        except (OSError, ValueError):
            continue

    def restore(value):
        if not value:
            set_run(None)
            return
        result = _call(lambda: lab.load_run(value))
        if result.get('run_id') and result['chapter'] == lesson['chapter']:
            set_run(value)
        set_event(result)

    restore_menu = mo.ui.dropdown(choices, value='未選擇', label='恢復既有 run', full_width=True, on_change=restore)
    refresh = mo.ui.refresh(options=['5s', '15s', '1m'], default_interval=None, label='只讀刷新')
    sidebar = mo.sidebar(mo.vstack([navigation(mo, lesson['chapter'].split('-', 1)[0]), restore_menu,
        *([] if manual_observation else [refresh]),
        mo.md('各段觀察按鈕只更新該段取樣。重新載入不重送、不自動清理。' if manual_observation else
              '重新載入只讀取紀錄，不重送、不自動清理。')]), width=290)
    return {'get_run': get_run, 'get_event': get_event, 'set_event': set_event, 'refresh': refresh,
            'form': form, 'restore_menu': restore_menu,
            'view': mo.vstack([sidebar, form, *create_buttons, mo.md(
                '參數變更需要新 run。按鈕才會執行外部命令；關閉頁面不取消工作。')])}


def action_controls(mo, lesson, run_id, set_event, *, include_verification=True, buttons=None):
    # The caller binds these UIElements to notebook globals. HTML alone is not
    # a reliable owner/binding for marimo's weak UI-element registry.
    if not run_id:
        return mo.md('先在上方建立實驗，或在側欄恢復既有 run。')
    try:
        run = lab.load_run(run_id)
        observed = lab.read_run(run_id)
    except (OSError, ValueError) as exc:
        return mo.md(str(exc)).callout(kind='danger')
    snapshot = None
    submit_chapter = lesson['chapter'] == '02-submit'
    if submit_chapter:
        from submit_view import action_header, step_terminal
        panels = [action_header(mo, run)]
    else:
        panels = [mo.md(f'## 本次實驗 `{run_id}`'), json_view(mo, run['parameters'])]
    for step_id, step in lesson['steps'].items():
        existing = next((r for r in observed['receipts'] if r['step_id'] == step_id), None)
        reason, argv = None, None
        try:
            argv = step.argv(run)
            if step.precondition and not existing:
                if snapshot is None:
                    snapshot = read_snapshot()
                result = step.precondition(run, snapshot)
                if isinstance(result, str):
                    reason = result
        except Exception as exc:
            reason = str(exc)
        confirmation = lesson.get('confirmations', {}).get(step_id)
        confirm = mo.ui.text(label=f'輸入 {confirmation}', placeholder=confirmation) if confirmation else None

        def invoke(_, step_id=step_id, step=step, confirm=confirm, phrase=confirmation):
            def perform():
                if phrase and confirm.value != phrase:
                    return {'status': 'blocked', 'reason': f'必須輸入 {phrase}；確認不會因舊表單自動沿用。'}
                frozen = lab.load_run(run_id)
                timeout = 15 if step.effect == 'interactive' else 90 if step.effect in {'restart-controller', 'restore-controller'} else 30
                return lab.execute_once(run_id, step_id, step.argv(frozen), effect=step.effect, timeout=timeout)
            result = _call(perform)
            set_event(result)
            return result

        title = lesson['labels'].get(step_id, step_id)
        button = mo.ui.button(label=title, on_click=invoke, disabled=bool(reason or existing),
                              kind='danger' if confirmation or step.effect == 'cancel' else 'neutral')
        if buttons is not None:
            buttons[step_id] = button
        if submit_chapter:
            content = [step_terminal(mo, step_id, title, argv, existing)]
        else:
            content = [mo.md(f'### {title} · `{step_id}`'),
                       mo.md('```bash\n' + shlex.join(argv) + '\n```') if argv else mo.md('命令等待前置步驟的 job ID。')]
        if confirm:
            content.append(confirm)
        content.append(button)
        if existing:
            label = '已執行過，本次不再重送' if submit_chapter else '已消耗'
            content.append(mo.md(f"{label}：**{existing['status']}** · job `{existing.get('job_id') or 'N/A'}`；重新載入不重送。"))
        elif reason:
            content.append(mo.md('尚不可執行：' + reason).callout(kind='warn'))
        panels.append(mo.vstack(content))

    if include_verification:
        panels.append(verification_controls(mo, lesson, run_id, set_event, buttons=buttons))
    return mo.vstack(panels)


def verification_controls(mo, lesson, run_id, set_event, *, buttons=None):
    if not run_id:
        return mo.md('')
    submit_chapter = lesson['chapter'] == '02-submit'
    panels = []

    def save(_):
        result = _call(lambda: lab.verify_run(run_id))
        set_event(result)
        return result

    def cleanup(_):
        result = _call(lambda: lab.cleanup_run(run_id))
        set_event(result)
        return result

    if submit_chapter:
        panels.extend([mo.Html('<span id="submit-verify"></span>'), mo.md('''### 驗證並保存，再清理
        兩條路徑都執行後，先到[結果區](#submit-results)核對工作與輸出，再按「驗證並保存」。
        它會檢查兩個工作是否 COMPLETED、退出碼是否成功，以及節點、UID、CPU affinity 和加總結果是否正確。
        若工作還沒結束，報告可能仍是 running；稍後用側欄刷新，完成後再按一次驗證。
        「只清理本次實驗」會取消本次仍未結束的工作，保留報告與輸出檔，不會取消別人的工作。
        **關閉瀏覽器不會取消工作。**''')])
    verify_button = mo.ui.button(label='驗證並保存', on_click=save, kind='success')
    cleanup_button = mo.ui.button(label='只清理本次實驗', on_click=cleanup, kind='danger')
    if buttons is not None:
        buttons.update(verify=verify_button, cleanup=cleanup_button)
    panels.append(mo.hstack([verify_button, cleanup_button], wrap=True))
    panels.append(mo.md(
        '清理失敗可以再按清理；已執行過的提交按鈕不會重送。若是 unknown，先核對完整紀錄中的工作名稱、使用者、目錄與時間；'
        '確認並處理既有工作後，才建立新實驗。' if submit_chapter else
        '清理可重試，但不重放提交。unknown 請先人工核對唯一名稱、UID、工作目錄與時間；不自動收編。'))
    return mo.vstack(panels)


def status_panel(mo, lesson, run_id, event):
    panels = []
    if event:
        panels.append(mo.accordion({'最近明確操作結果': json_view(mo, event)}, multiple=True))
        if event.get('status') in {'blocked', 'failed', 'unknown'}:
            panels.append(mo.md(str(event.get('reason') or event.get('error') or event.get('status'))).callout(kind='warn'))
    if run_id:
        result = _call(lambda: lab.read_run(run_id))
        if 'receipts' not in result:
            panels.append(json_view(mo, result))
        else:
            panels.append(mo.md(f"## 只讀狀態 · {result['observed_at']}\nReport: **{(result.get('report') or {}).get('status', '損壞／缺失')}**"))
            rows = []
            for identifier, observed in result['jobs'].items():
                if not observed['records']:
                    rows.append({'job_id': identifier, 'observation': observed['status']})
                for job in observed['records']:
                    rows.append({k: job[k] for k in ('job_id','array_job_id','array_task_id','name','job_state','state_reason','exit_code','start_time')})
                    if 'RUNNING' in job['job_state'] and job['start_time'] and any(word in job['name'] for word in ('holder','neighbor','active')):
                        step_id = next((r['step_id'] for r in result['receipts'] if r.get('job_id') == identifier), '')
                        seconds = lesson.get('holder_seconds', {}).get(step_id, 240 if lesson['chapter'].startswith('11') else 120 if lesson['chapter'].startswith('07') else 180)
                        remaining = max(0, int(job['start_time'] + seconds - datetime.now(timezone.utc).timestamp()))
                        panels.append(mo.md(f"Holder `{job['job_id']}` 操作窗口約剩 **{remaining} 秒**（依 scheduler StartTime；啟動開銷可能縮短窗口）。過期不能算完成。"))
            panels.append(mo.ui.table(table_rows(rows), selection=None) if rows else mo.md('尚無本次 job；查不到紀錄不等於 COMPLETED。'))
            panels.append(mo.accordion({'報告／case evidence／cleanup errors': json_view(mo, result['report']),
                                       'Receipts 與不可重試的 unknown': json_view(mo, result['receipts']),
                                       '查詢／路徑錯誤': json_view(mo, result['errors'])}, multiple=True))
            for identifier, logs in result['outputs'].items():
                for log in logs:
                    content = [mo.plain_text(log['text'] if log['text'] is not None else str(log['error']))]
                    if log['status'] == 'ok':
                        content.append(mo.download(lambda path=log['path']: lab.download_log(run_id,path), filename=Path(log['path']).name, label='下載完整輸出'))
                    panels.append(mo.accordion({f"{identifier} · {Path(log['path']).name} · {log['status']} {'（末 64 KiB 截斷）' if log['truncated'] else ''}": mo.vstack(content)}, multiple=True))
            if lesson['chapter'].startswith('04'):
                files = ['pipeline/manifest.json', 'pipeline/summary.json'] + [f'pipeline/input/shard-{i}.csv' for i in range(4)] + [f'pipeline/partials/{i}.json' for i in range(4)]
                panels.append(mo.accordion({name: json_view(mo, preview_file(Path(result['run_dir']),name)) for name in files}, multiple=True))
    sources = {}
    for name in lesson.get('sources', []):
        if Path(name).name != name:
            continue
        path = lab.ROOT / 'examples' / name
        sources[name] = mo.md('```' + ('python' if name.endswith('.py') else 'bash') + '\n' + path.read_text() + '\n```') if path.exists() else mo.md(f'缺少公開 workload：{path}')
    if sources:
        panels.append(mo.accordion(sources, multiple=True))
    panels.append(mo.md('## 獨立終端驗收\n先清理 notebook 工作，再於專案根目錄執行；不在 callback 同步跑 suite。\n```bash\n' + '\n'.join('python3 scripts/smoke.py --case ' + name for name in lesson['cases']) + '\n```'))
    return mo.vstack(panels)
