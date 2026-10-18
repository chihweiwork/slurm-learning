import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="Slurm Learning Dashboard")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import pandas as pd
    import json
    from datetime import datetime, timezone
    from pathlib import Path
    from notebook_queries import read_snapshot, download_log
    from notebook_lab import read_run
    from notebook_views import navigation, json_view, table_rows

    return (
        Path,
        alt,
        datetime,
        download_log,
        json,
        json_view,
        mo,
        navigation,
        pd,
        read_run,
        read_snapshot,
        table_rows,
        timezone,
    )


@app.cell
def _(mo):
    refresh = mo.ui.refresh(options=["5s", "15s", "1m"], default_interval="15s")
    partition = mo.ui.dropdown(["全部", "cpu", "gpu"], value="全部", label="Partition")
    get_run_filter, set_run_filter = mo.state("")
    search = mo.ui.text(label="搜尋 job ID／名稱／Reason")
    state_filter = mo.ui.dropdown(["全部", "RUNNING", "PENDING", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY"], value="全部", label="Job state")
    return get_run_filter, partition, refresh, search, set_run_filter, state_filter


@app.cell
def _(mo, navigation, partition, refresh, run_filter):
    mo.sidebar(mo.vstack([mo.md("## Slurm Learning Lab"), navigation(mo, "00"), partition, run_filter, refresh,
        mo.md("**只讀 Dashboard**\n\n提交與維運請到實驗頁。關閉頁面不取消工作。")]), width=290)
    return


@app.cell
def _(read_snapshot, refresh):
    refresh.value
    snapshot = read_snapshot()
    return (snapshot,)


@app.cell
def _(get_run_filter, mo, set_run_filter, snapshot):
    _options = {"全部／未選": "", **{
        f"{r['kind']} · {r['run_id']}": f"{r['source']}/{r['run_id']}"
        for r in snapshot['history'] if r.get('run_id')}}
    _selected = get_run_filter()
    run_filter = mo.ui.dropdown(
        _options,
        value=next((label for label, value in _options.items() if value == _selected), "全部／未選"),
        label="Run", full_width=True, on_change=set_run_filter,
    )
    return (run_filter,)


@app.cell
def _(mo, snapshot):
    _sources = snapshot['sources']
    _controller = _sources['controller']
    _value = lambda x: 'N/A' if x is None else str(x)
    mo.vstack([
        mo.md("# Slurm Learning Dashboard\n真實排程與實驗證據 · 跨命令觀測不是原子快照"),
        mo.hstack([
            mo.stat('UP' if _controller['status'] == 'ok' else 'STALE / ERROR', label='Controller', caption='最後成功：' + str(_controller['last_success_at'] or '尚無')),
            mo.stat(_value(snapshot['counts']['healthy_nodes']), label='健康節點', caption='不代表可接受任意新工作'),
            mo.stat(_value(snapshot['counts']['running']), label='RUNNING tasks'),
            mo.stat(_value(snapshot['counts']['pending']), label='PENDING tasks'),
        ], wrap=True),
        mo.md('本次取得：`' + snapshot['observed_at'] + '`'),
        mo.vstack([mo.md(f"**{_name}: {'stale' if _source['stale'] else 'error'}** · 最後成功 {_source['last_success_at'] or 'N/A'}\n\n`{_source['errors']}`").callout(kind='warn')
                   for _name, _source in _sources.items() if _source['status'] != 'ok']),
    ])
    return


@app.cell
def _(Path, download_log, json, partition, run_filter, search, snapshot, state_filter):
    selected_history = next((h for h in snapshot['history'] if f"{h['source']}/{h.get('run_id')}" == run_filter.value), None)
    if selected_history and selected_history['status'] == 'ok':
        try:
            selected_history = {**selected_history, 'report_scope': 'full',
                'report': json.loads(download_log(Path(selected_history['path']).parent, 'report.json'))}
        except (OSError, ValueError) as _error:
            selected_history = {**selected_history, 'status': 'error', 'error': str(_error), 'report': None}
    _owned = set(str(x) for x in (selected_history or {}).get('report', {}).get('created_job_ids', [])) if (selected_history or {}).get('report') else set()
    def _matches(row):
        _state = row.get('state') or ','.join(row.get('job_state', []))
        return ((partition.value == '全部' or row.get('partition') == partition.value)
            and (state_filter.value == '全部' or state_filter.value in _state)
            and (not run_filter.value or row.get('job_id') in _owned or row.get('parent_job_id') in _owned or row.get('array_job_id') in _owned)
            and (not search.value or search.value.casefold() in str(row).casefold()))
    active_jobs = [j for j in snapshot['sources']['queue']['data'] or [] if _matches(j)]
    retained_jobs = [j for j in snapshot['sources']['jobs']['data'] or [] if _matches(j)]
    return active_jobs, retained_jobs, selected_history


@app.cell
def _(active_jobs, mo, retained_jobs, table_rows):
    job_table = mo.ui.table(table_rows(retained_jobs), selection='single', pagination=True, page_size=10, label='Retained jobs（控制器短期紀錄）')
    active_table = mo.ui.table(table_rows(active_jobs), selection=None, pagination=True, page_size=10, label='Active queue（逐 array task）')
    return active_table, job_table


@app.cell
def _(
    active_table,
    alt,
    datetime,
    job_table,
    json_view,
    mo,
    partition,
    pd,
    search,
    selected_history,
    snapshot,
    state_filter,
    table_rows,
    timezone,
):
    _nodes = [n for n in snapshot['sources']['nodes']['data'] or [] if partition.value == '全部' or partition.value in n['partitions']]
    _node_rows = [{k: n[k] for k in ('name','state','effective_cpus','alloc_cpus','real_memory','alloc_memory','gres','gres_used','reason')} for n in _nodes]
    _resources = mo.vstack([
        mo.md('## 節點／排程資源\nCPU 使用 **effective_cpus**；RAM 是可排程容量，不是主機 free_mem。GPU GRES 配置與實體 GPU 利用率不同。'),
        mo.ui.table(table_rows(_node_rows), selection=None),
    ])
    _jobs = mo.vstack([mo.hstack([search, state_filter], wrap=True), mo.ui.tabs({'Active queue': active_table, 'Retained jobs': job_table}),
        mo.md('Active queue 以 squeue 逐 task 計數；retained parent 不重複計入。外部工作只顯示 metadata，沒有取消按鈕。選取 retained job 後詳情在頁面下方。')])
    _gpu = mo.vstack([
        mo.md('## 實體整卡觀測\n包含桌面／Ollama 等非 Slurm 負載，不能歸因為單一 job 的專屬使用率。`--mem` 限制 RAM，不是 VRAM；無顯存切分或效能保證。CUDA 成功須檢查全部 65539 元素，不看 nvidia-smi 利用率。'),
        mo.ui.table(snapshot['sources']['gpu']['data'] or [], selection=None),
        mo.md('### Slurm GRES 配額（獨立語意）'),
        mo.ui.table([{'node': n['name'], 'gres': n['gres'], 'allocated': n['gres_used']} for n in snapshot['sources']['nodes']['data'] or [] if n['gres']], selection=None),
    ])
    _segments, _omitted = [], []
    _report = (selected_history or {}).get('report') or {}
    _ids = set(map(str, _report.get('created_job_ids', [])))
    _now = datetime.fromisoformat(snapshot['observed_at']).timestamp()
    for _job in snapshot['sources']['jobs']['data'] or []:
        if _job['job_id'] not in _ids and _job['array_job_id'] not in _ids:
            continue
        _label = f"{_job['array_job_id']}_{_job['array_task_id']}" if _job['array_job_id'] and _job['array_task_id'] is not None else _job['job_id']
        _submit, _start, _end = (_job[k] for k in ('submit_time','start_time','end_time'))
        _state = _job['job_state']
        if _submit and (_start or 'PENDING' in _state):
            _segments.append({'job': _label, 'phase': '等待（未完成）' if not _start else '等待', 'start': datetime.fromtimestamp(_submit, timezone.utc), 'end': datetime.fromtimestamp(_start or _now, timezone.utc)})
        if _start and (_end or 'RUNNING' in _state):
            _segments.append({'job': _label, 'phase': '執行（未完成）' if not _end else '執行', 'start': datetime.fromtimestamp(_start, timezone.utc), 'end': datetime.fromtimestamp(_end or _now, timezone.utc)})
        if not _submit or (not _start and 'PENDING' not in _state):
            _omitted.append(_label)
    _timeline = mo.vstack([
        mo.md('## 實驗時間軸\n選擇側欄 run；使用 scheduler submit/start/end timestamp，並非輪詢時間點的偽造事件。PENDING 不畫執行區間。'),
        mo.ui.altair_chart(alt.Chart(pd.DataFrame(_segments)).mark_bar().encode(x='start:T', x2='end:T', y='job:N', color='phase:N', tooltip=['job','phase','start:T','end:T']).properties(height=max(160,len(_segments)*18)), chart_selection=False) if _segments else mo.md('尚無可畫時間區間；未選 run、未知時間或 scheduler 紀錄已過期。'),
        mo.md('省略未知時間：' + (', '.join(_omitted) or '無') + '。未保存且已過期的排程時間不補造。'),
    ])
    _history_rows = [{'source': h['kind'], 'run_id': h['run_id'], 'read_status': h['status'], 'result': (h.get('report') or {}).get('status'), 'path': h['path'], 'error': h['error']} for h in snapshot['history']]
    _results = mo.vstack([
        mo.md('## 結果與證據\nnotebook 實驗、單案例驗收、套件紀錄分開呈現；多案例紀錄不等於完整回歸通過。'),
        mo.ui.table(_history_rows, selection=None, pagination=True) if _history_rows else mo.md('尚無實驗或驗收紀錄。'),
        mo.accordion({'所選 run 原始 report／case evidence／commands／cleanup errors': json_view(mo, selected_history)}, multiple=True) if selected_history else mo.md('從側欄選擇一份 run 查看證據。'),
    ])
    mo.ui.tabs({'節點／資源': _resources, '工作': _jobs, '實驗時間軸': _timeline, 'GPU': _gpu, '結果／證據': _results})
    return


@app.cell
def _(
    Path,
    download_log,
    job_table,
    json_view,
    mo,
    read_run,
    retained_jobs,
    selected_history,
):
    _selection = job_table.value
    _selected = _selection[0] if isinstance(_selection, list) and _selection else None
    _job = next((j for j in retained_jobs if _selected and j['job_id'] == _selected['job_id']), None)
    _panels = []
    if _job:
        _panels.append(mo.accordion({'所選工作：dependency／exit code／原始查詢': json_view(mo, _job)}, multiple=True))
        if selected_history and selected_history['source'] == 'demos' and selected_history.get('report') and (_job['job_id'] in map(str, selected_history['report'].get('created_job_ids', [])) or _job['array_job_id'] in map(str, selected_history['report'].get('created_job_ids', []))):
            _run = read_run(selected_history['run_id'])
            for _identifier, _logs in _run['outputs'].items():
                if _identifier not in {_job['job_id'], _job['array_job_id'], f"{_job['array_job_id']}_{_job['array_task_id']}"}:
                    continue
                for _log in _logs:
                    _panels.append(mo.md(f"### {_log['path']} · {_log['status']} {'（截斷：末 64 KiB）' if _log['truncated'] else ''}"))
                    _panels.append(mo.plain_text(_log['text'] if _log['text'] is not None else _log['error']))
                    if _log['status'] == 'ok':
                        _panels.append(mo.download(download_log(Path(_run['run_dir']), _log['path']), filename=Path(_log['path']).name, label='下載完整本次輸出'))
        else:
            _panels.append(mo.md('外部或未選本次 notebook run：只讀 metadata，不讀取任意工作輸出。'))
    mo.vstack(_panels)
    return


@app.cell
def _(
    Path,
    active_jobs,
    download_log,
    json,
    mo,
    pd,
    selected_history,
    snapshot,
):
    _report_bytes = b''
    _error = None
    if selected_history and selected_history['status'] == 'ok':
        try:
            _report_bytes = download_log(Path(selected_history['path']).parent, 'report.json')
        except (OSError, ValueError) as _exc:
            _error = str(_exc)
    mo.vstack([
        mo.hstack([
            mo.download(json.dumps(snapshot, ensure_ascii=False, indent=2).encode('utf-8'), filename='snapshot.json', mimetype='application/json', label='下載目前完整 snapshot JSON'),
            mo.download(pd.DataFrame(active_jobs).to_csv(index=False).encode('utf-8'), filename='filtered-active-jobs.csv', mimetype='text/csv', label='下載篩選後 active queue CSV', disabled=not active_jobs),
            mo.download(_report_bytes, filename='report.json', mimetype='application/json', label='下載所選 run 原始 report JSON', disabled=not _report_bytes),
        ], wrap=True),
        mo.md(_error).callout(kind='warn') if _error else mo.md('下載範圍依按鈕標籤；空工作列表與未選 report 停用。'),
    ])
    return


if __name__ == "__main__":
    app.run()
