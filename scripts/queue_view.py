"""Read-only Chapter 03 queue observations, job evidence and saved outputs."""
from datetime import datetime, timezone

import notebook_lab as lab
from lesson_common import Pending, job_id, receipt
from lessons_cpu import _holder, _pending
from notebook_views import json_view
from slurm_cli import compose_argv, run_command
from submit_view import _file_panel


def job_rows(data):
    rows = []
    for step, label in [('holder', 'A（先佔用資源）'), ('waiter', 'B（後提交）')]:
        saved = receipt(data, step)
        if not saved:
            continue
        observed = data['jobs'].get(saved.get('job_id'), {})
        records = observed.get('records', []) if observed.get('status') == 'observed' else []
        common = {'工作': label, 'Job ID': saved.get('job_id') or '未確認'}
        if not records:
            rows.append({**common, '狀態': observed.get('status', '尚未取得紀錄'), '節點／等待原因': '未確認'})
        for job in records:
            rows.append({**common, '狀態': ', '.join(job['job_state']),
                         '節點／等待原因': job.get('state_reason') if 'PENDING' in job['job_state']
                         else job.get('nodes') or '未分配'})
    return rows


def before_ready(data):
    try:
        _holder(data)
        _pending(data, 'waiter', {'Resources', 'Priority'})
    except (AssertionError, ValueError, KeyError, Pending):
        return False
    return True


def sample_queue(run_id):
    initial = lab.read_run(run_id)
    identifiers = [job_id(initial, step) for step in ('holder', 'waiter')]
    argv = compose_argv('squeue', '--jobs=' + ','.join(identifiers),
                        '--format=%.12i %.12T %.6C %.12M %.12l %R')
    try:
        result = run_command(argv, cwd=lab.ROOT, timeout=10)
        command = dict(argv=argv, stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
    except Exception as exc:
        command = dict(argv=argv, error=str(exc))
    # Independent fresh identity-checked job records; not an atomic squeue snapshot.
    data = lab.read_run(run_id)
    return {'observed_at': datetime.now(timezone.utc).isoformat(), 'command': command,
            'rows': job_rows(data), 'ready': command.get('returncode') == 0 and before_ready(data)}



def results_panel(mo, lesson, run_id, event):
    panels = [mo.md('## 輸出、驗證與原始紀錄\n\nB 的 `.out` 應包含 `hostname: cpu01`、1 CPU 的 affinity 與 `sum: 50005000`。A 被取消是本實驗的預期結果。')]
    if event:
        panels.append(mo.plain_text('建立／驗證／清理結果：' + str(event.get('status', '已返回')) + ' · ' +
                                    str(event.get('reason') or event.get('error') or '請對照下方驗證報告。')))
    if run_id:
        try:
            data = lab.read_run(run_id)
            for identifier, logs in data['outputs'].items():
                panels.append(mo.accordion({f'Job {identifier} 的輸出': mo.vstack([
                    _file_panel(mo, run_id, log) for log in logs])}))
            panels.append(mo.accordion({'驗證報告': json_view(mo, data.get('report')),
                                        '完整指令回條／取消前證據': json_view(mo, data['receipts']),
                                        '查詢與路徑錯誤': json_view(mo, data['errors'])}))
        except Exception as exc:
            panels.append(mo.plain_text(f'讀取結果失敗：{exc}'))
    panels.append(mo.md('''### 獨立終端驗收

完成操作後先按「驗證並保存」。它檢查取消前 A RUNNING／B PENDING 的證據、A CANCELLED，以及 B 完成且輸出正確。
若 B 尚在執行，等它結束再驗證。「只清理本次實驗」會取消本次尚未結束的工作；不會刪除輸出與紀錄。
關閉頁面不會停止工作；要重做，先清理，再於上方建立新實驗。

下面是額外的自動驗收，會另建測試工作，採用通知 holder 自行結束的方式；不是本頁的 scancel 操作。
請先清理本次實驗，並確認 lab 沒有其他工作，再到 Ubuntu 專案目錄執行：

```bash
python3 scripts/smoke.py --case resource-queue-release
```
'''))
    return mo.vstack(panels)
