"""Chapter 02 presentation of existing receipts and observations; no submissions."""
import json
from pathlib import Path

import notebook_lab as lab
from environment_view import TERMINAL_CSS, _terminal
from notebook_views import json_view, table_rows


def run_summary(mo, run_id, event):
    """Show saved setup immediately after the form, without querying Docker."""
    panels = [mo.Html('<span id="submit-current-run"></span>')]
    if event and event.get('status') in {'blocked', 'failed', 'unknown'}:
        panels.append(mo.plain_text('最近操作未完成：' + str(
            event.get('reason') or event.get('error') or event['status'])))
    if not run_id:
        panels.append(mo.md('**尚未建立實驗。** 選好節點與 CPU 數後，按上方「套用參數並建立實驗」。'))
        return mo.vstack(panels)
    try:
        run = lab.load_run(run_id)
    except (OSError, ValueError) as exc:
        panels.append(mo.plain_text(f'無法讀取目前實驗：{exc}'))
        return mo.vstack(panels)
    p = run['parameters']
    panels.append(mo.md(f'''### 目前實驗已就緒

    **執行節點：{p['node']}　｜　每個 task：{p['cpus']} CPU　｜　RAM：128 MiB**

    實驗編號：`{run['run_id']}`

    這是本次已保存的設定；修改上方選單後，需再次按「套用參數並建立實驗」才會切換。
    建立實驗不會提交計算工作。**下一步：直接操作下方的 srun／sbatch 按鈕。**

    [srun 練習](#submit-interactive) · [sbatch 練習](#submit-batch) ·
    [加做：觀察實際運算](#submit-external) · [加做：1／4 核比較](#submit-serial)
    '''))
    panels.append(mo.accordion({'本次實驗的檔案目錄': mo.plain_text(
        f"Ubuntu：{run['run_dir']}\n容器內：{run['container_dir']}")}))
    return mo.vstack(panels)


def action_header(mo, run):
    return mo.vstack([
        mo.Html(TERMINAL_CSS),
        mo.md('''## 基礎練習：分別按 srun 與 sbatch
        兩個按鈕都使用上方[目前實驗](#submit-current-run)已保存的節點與 CPU 數。
        下方 srun 與 sbatch 按鈕各提交一個獨立工作；兩個都按，就會有兩個 Job ID。
        完成這兩個短程式後，可以接著做下方的[外部觀察](#submit-external)與[1／4 核比較](#submit-serial)。
        若已有其他實驗工作正在執行，請先停止或等待它結束，以免搶占資源。
        黑底區塊只顯示指令與輸出；**按鈕才會執行指令**，刷新不會重送。'''),
    ])


def step_terminal(mo, step_id, title, argv, existing):
    interactive = step_id == 'interactive'
    explanation = ('''這是在既有 allocation 外直接呼叫 srun：先取得資源，再啟動一個 Python task，等待它結束。
        程式的 JSON 會直接回到下方 stdout。這裡的「互動式」是指前景執行，不會開啟可輸入指令的 shell。'''
        if interactive else '''sbatch 把 cpu.sbatch 交給排程器，收到 Job ID 就返回，不等計算完成。
        下方 stdout 的數字是提交回條；Python 程式的結果要到結果區看 batch-<Job ID>.out。''')
    record = existing if existing is not None else {'argv': argv or []}
    note = ('這是已保存的執行紀錄，刷新不會再次執行。exit 是這支指令的退出碼；工作狀態要另看結果區。'
            if existing else '這是指令預覽，尚未執行；按下本段按鈕才會建立工作。')
    return mo.vstack([
        mo.Html(f'<span id="submit-{step_id}"></span>'),
        mo.md(f"### {title}\n\n{explanation}"),
        _terminal(mo, 'srun / 前景執行' if interactive else 'sbatch / 提交腳本', record,
                  pending=existing is None, note=note,
                  error_label='指令執行／確認錯誤（不是程式的 stderr）'),
    ])


def job_rows(data):
    """Keep command outcomes separate from scheduler states and missing evidence."""
    rows = []
    for receipt in data['receipts']:
        if receipt['step_id'] not in {'interactive', 'batch'}:
            continue
        identifier = receipt.get('job_id')
        observed = data['jobs'].get(identifier, {})
        records = observed.get('records', []) if observed.get('status') == 'observed' else []
        common = {'路徑': 'srun' if receipt['step_id'] == 'interactive' else 'sbatch',
                  'Job ID': identifier or '尚未確認', '指令結果': receipt['status'],
                  '指令退出碼': receipt.get('returncode')}
        if not records:
            rows.append({**common, '工作狀態': observed.get('status') or '尚未取得紀錄',
                         '節點': '無法判斷', '工作退出碼': '無法判斷', '等待原因': '無法判斷'})
        for job in records:
            code = job.get('exit_code') or {}
            signal = (code.get('signal') or {}).get('id')
            rows.append({**common, '工作狀態': ', '.join(job['job_state']),
                         '節點': job.get('nodes') or '尚未分配',
                         '工作退出碼': f"return={code.get('return_code')}; signal={signal}",
                         '等待原因': job.get('state_reason') or '無'})
    return rows


def _file_panel(mo, run_id, log):
    path = log['path']
    name = Path(path).name
    is_error = name.endswith('.err')
    text = log.get('text')
    record = {'stderr' if is_error else 'stdout': text or ''}
    if log['status'] != 'ok':
        record['error'] = str(log.get('error') or log['status'])
    note = ('這是已保存的檔案預覽，沒有額外執行 cat。空白 .err 通常表示沒有錯誤輸出，仍需核對工作狀態。'
            if is_error else '這是 Python task 寫入 .out 的內容；對照下方欄位說明，確認它在哪裡、用什麼 CPU 執行。')
    if log.get('truncated'):
        note += '\n檔案預覽只保留末 64 KiB，完整內容可下載。'
    panels = [_terminal(mo, name, record, stdin_note=f'（讀取檔案預覽）{path}', note=note,
                        error_label='讀取輸出檔失敗')]
    if log['status'] == 'ok':
        panels.append(mo.download(lambda: lab.download_log(run_id, path), filename=name, label='下載完整輸出'))
    return mo.vstack(panels)


def status_panel(mo, lesson, run_id, event):
    panels = [mo.Html(TERMINAL_CSS), mo.Html('<span id="submit-results"></span>'),
              mo.md('''## 結果在哪裡？先分清楚兩種輸出
              **srun：** 回到[前景執行區](#submit-interactive)看 stdout，裡面是程式印出的 JSON。
              **sbatch：** [提交區](#submit-batch)的 stdout 只有 Job ID；程式結果在下方 `.out`，錯誤在 `.err`。
              用左側「只讀刷新」更新狀態；選 5s 就會每五秒查一次，無須重新整理瀏覽器。''')]
    if event:
        status = event.get('status', '未提供')
        panels.append(mo.plain_text(f'最近操作結果：{status}'))
        if status in {'blocked', 'failed', 'unknown'}:
            panels.append(mo.plain_text(str(event.get('reason') or event.get('error') or status)))
        panels.append(mo.accordion({'最近操作的完整回應': json_view(mo, event)}))
    if run_id:
        try:
            data = lab.read_run(run_id)
        except Exception as exc:
            panels.append(mo.plain_text(f'讀取本次實驗失敗：{type(exc).__name__}: {exc}'))
        else:
            report = data.get('report') or {}
            panels.append(mo.plain_text(f"查詢時間：{data['observed_at']} · 驗證報告：{report.get('status', '缺失／無法判斷')}"))
            rows = job_rows(data)
            panels.append(mo.ui.table(table_rows(rows), selection=None) if rows else
                          mo.md('本表尚無 srun／cpu.sbatch 工作；請先執行上方按鈕。觀察工作與 1／4 核比較的狀態顯示在各自的實驗區。'))
            panels.append(mo.md('''### 怎麼判讀這張工作表？
            - **指令結果／指令退出碼**：按鈕呼叫的 srun 或 sbatch 是否成功返回。sbatch exit 0 只表示提交成功。
            - **工作狀態／工作退出碼**：Slurm 回報的工作執行結果；本章兩個工作都應為 COMPLETED，return=0，沒有終止訊號。
            - **節點／等待原因**：程式被安排到哪裡；若是 PENDING，先看等待原因與可用資源。
            - **record-unavailable**：目前查不到保留紀錄；**query-error**：查詢失敗；兩者都不代表成功。
              **identity-mismatch** 表示紀錄身分不符，不能拿來證明本次工作成功。
            - **unknown**：提交結果未能確認，可能已建立工作；不要直接重送。先展開完整紀錄核對唯一工作名稱。

            同時出現兩個 Job ID，是因為你分別按了 srun 與 sbatch。
            cpu.sbatch 裡面的 srun 是 batch 工作內的 step，會沿用該工作的 Job ID，不會再多提交一個獨立 job。'''))
            for identifier, logs in data['outputs'].items():
                panels.append(mo.plain_text(f'Job {identifier} 的輸出檔'))
                panels.extend(_file_panel(mo, run_id, log) for log in logs)
            if not data['outputs']:
                panels.append(mo.md('目前沒有 batch 輸出檔預覽。若只執行 srun，請往上看它的 stdout；若已提交 batch，稍後刷新。'))
            if data['errors']:
                panels.append(mo.plain_text('讀取或路徑錯誤：' + json.dumps(data['errors'], ensure_ascii=False)))
            panels.append(mo.Html('<span id="submit-evidence"></span>'))
            panels.append(mo.accordion({
                '原始查詢：scontrol --json show jobs': _terminal(
                    mo, 'Slurm 工作查詢 / 本次刷新',
                    {**data['job_query'], 'error': json.dumps(data['job_query']['errors'], ensure_ascii=False)
                     if data['job_query'].get('errors') else None},
                    note='保留本次查詢的實際指令與原始回應，可能包含其他人的工作；上方表格只列本次實驗的工作。'),
                '完整紀錄：報告／驗證證據／清理錯誤': json_view(mo, data['report']),
                '完整紀錄：指令回條／unknown 候選（不代表已確認歸屬）': json_view(mo, {
                    'receipts': data['receipts'], 'unknown_candidates': data.get('unknown_candidates', {})}),
                '完整紀錄：Slurm 查詢／輸出檔路徑／錯誤': json_view(mo, {
                    'jobs': data['jobs'], 'job_query': data['job_query'], 'outputs': data['outputs'], 'errors': data['errors']}),
            }, multiple=True))
    else:
        panels.append(mo.md('尚未選擇本次實驗；建立實驗或從側欄恢復既有 run 後，這裡才會有實際結果。'))
    panels.extend([
        mo.Html('<span id="submit-probe"></span>'),
        mo.md('''### 程式 JSON 的每個欄位代表什麼？

        | 欄位 | 代表什麼 | 本章預期 |
        | --- | --- | --- |
        | `job_id` | 程式從 SLURM_JOB_ID 讀到的工作編號 | 與該路徑的 Job ID 相同 |
        | `hostname` | 真正執行 Python 的節點 | 你選擇的 cpu01 或 cpu02 |
        | `uid` | 執行程式的 Linux 使用者編號 | 1000，也就是容器內的 lab |
        | `affinity` | 這個 process 被允許在哪些 Linux 邏輯 CPU 上執行 | 1 或 4 個 CPU 編號，且位於所選節點的 cpuset |
        | `sum` | Python 計算 0 到 10000 的加總 | 50005000 |

        affinity 是允許執行的 CPU 集合，不是即時使用率，也不保證 CPU 編號從 0 開始。
        這支程式是單執行緒：申請 4 個 CPU 不會自動讓加總平行或變成四倍快。
        本章的通過條件由[驗證並保存](#submit-verify)一起檢查，不能只看到 sum 正確就判定整個實驗成功。
        這些 JSON 欄位仍是程式自己回報的資訊；想從 Docker 與 Linux 獨立確認，請看[外部觀察實際運算](#submit-external)。'''),
        mo.Html('<span id="submit-source"></span>'),
        mo.md('''## 對照腳本：sbatch 到底執行了什麼？
        `cpu.sbatch` 的 `#SBATCH` 行是資源需求，最後的 `srun ... cpu_probe.py affinity` 才啟動計算。
        筆記本會在 sbatch 命令列覆寫 node、CPU 數、工作目錄與 `.out`／`.err` 路徑；
        所以腳本裡的 `--cpus-per-task=1` 不表示選 4 CPU 會失效，命令列設定優先。
        `set -euo pipefail` 讓常見腳本錯誤及早回報；Python 的 identity() 則收集表中欄位。'''),
    ])
    sources = {}
    for name in lesson['sources']:
        path = lab.ROOT / 'examples' / name
        language = 'python' if name.endswith('.py') else 'bash'
        sources[name] = mo.md(f'```{language}\n{path.read_text(encoding="utf-8")}\n```') if path.exists() else mo.plain_text(f'缺少檔案：{path}')
    panels.extend([
        mo.accordion(sources, multiple=True),
        mo.Html('<span id="submit-smoke"></span>'),
        mo.md('''## 獨立終端驗收：確認 CPU 分配真的有效
        完成「驗證並保存」與「只清理本次實驗」，確認整個 lab 沒有其他工作，再於 Ubuntu 終端執行：
        ```bash
        cd ~/slurm-learning
        python3 scripts/smoke.py --case cpu-affinity
        ```
        這個驗收會先跑 nodes-partitions，然後自動在 cpu01／cpu02 分別申請 1 與 4 個 CPU，
        **額外提交四個測試工作**，核對 task 實際看到的 CPU affinity 與運算結果，並保存 Evidence 報告。
        它不會替代 notebook 的兩個按鈕，也不是只查詢狀態；不用在每次刷新時執行。
        完成本章後，可以另建 run 切換 node 或 cpus 比較結果。'''),
    ])
    return mo.vstack(panels)
