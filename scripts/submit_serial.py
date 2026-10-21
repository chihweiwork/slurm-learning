"""Explicit, sequential 1/4 CPU comparison of one fixed serial workload."""
import json
import math
import shlex

import notebook_lab as lab
from environment_view import _terminal
from smoke import CPUSETS
from lesson_common import submit
from notebook_views import json_view, table_rows


ITERATIONS = 12_000_000
ROUNDS = 3
SERIAL_WORKLOAD = f'''import json, os, socket, statistics, time
wall, cpu = [], []
for repeat in range({ROUNDS}):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    total = sum(i * i for i in range({ITERATIONS}))
    cpu.append(time.process_time() - cpu_start)
    wall.append(time.perf_counter() - wall_start)
print(json.dumps(dict(job_id=os.environ['SLURM_JOB_ID'], hostname=socket.gethostname(),
    affinity=sorted(os.sched_getaffinity(0)), iterations={ITERATIONS}, rounds={ROUNDS},
    checksum=total, wall_seconds=statistics.median(wall), cpu_seconds=statistics.median(cpu),
    average_cores=sum(cpu)/sum(wall))))
'''


def serial_argv(run, cpus):
    if cpus not in (1, 4) or run['parameters']['node'] not in ('cpu01', 'cpu02'):
        raise ValueError('比較只允許 cpu01/cpu02 上的 1 或 4 CPU')
    command = shlex.join(['srun', '--cpu-bind=threads', 'python3', '-c', SERIAL_WORKLOAD])
    return submit(run, f'serial-{cpus}', command=command, options=(
        f"--nodelist={run['parameters']['node']}", f'--cpus-per-task={cpus}',
        '--mem=128M', '--time=00:02:00'))


def serial_result(data, cpus):
    """Only compare completed, identity-checked jobs with intact measurement output."""
    receipt = next((r for r in data['receipts'] if r['step_id'] == f'serial-{cpus}'), None)
    if not receipt or receipt['status'] != 'succeeded' or not receipt.get('job_id'):
        return None
    identifier = receipt['job_id']
    observed = data['jobs'].get(identifier, {})
    records = observed.get('records', [])
    if observed.get('status') != 'observed' or not records:
        return None
    if any(job['job_state'] != ['COMPLETED'] or
           (job.get('exit_code') or {}).get('return_code') != 0 or
           ((job.get('exit_code') or {}).get('signal') or {}).get('id') not in (None, 0)
           for job in records):
        return None
    values = []
    for log in data.get('outputs', {}).get(identifier, []):
        if log['status'] != 'ok' or log.get('truncated') or not log['path'].endswith('.out'):
            continue
        for line in (log.get('text') or '').splitlines():
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if len(values) != 1 or not isinstance(values[0], dict):
        return None
    value = values[0]
    try:
        if (str(value['job_id']) != identifier or value['hostname'] != data['parameters']['node'] or
                len(set(value['affinity'])) != cpus or
                not set(value['affinity']) <= CPUSETS[data['parameters']['node']] or
                value['iterations'] != ITERATIONS or value['rounds'] != ROUNDS or
                value['checksum'] != (ITERATIONS - 1) * ITERATIONS * (2 * ITERATIONS - 1) // 6 or
                any(not math.isfinite(value[key]) or value[key] <= 0
                    for key in ('wall_seconds', 'cpu_seconds', 'average_cores'))):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return value


def _ready(run, snapshot, *, needs_baseline=False):
    data = lab.read_run(run['run_id'])
    for observed in data['jobs'].values():
        if observed.get('status') != 'observed' or any(
                not set(job['job_state']) & lab.TERMINAL for job in observed.get('records', [])):
            return '請先停止或等待本次實驗的其他工作結束，再做耗時比較。'
    if needs_baseline and serial_result(data, 1) is None:
        return '先完成 1 CPU 測量並取得有效輸出，再執行 4 CPU 測量。'


def serial_steps():
    return {
        'serial-1': lab.Step('submit', lambda run: serial_argv(run, 1), _ready),
        'serial-4': lab.Step('submit', lambda run: serial_argv(run, 4),
                             lambda run, snapshot: _ready(run, snapshot, needs_baseline=True)),
    }


def serial_panel(mo, run_id, event, set_event, *, buttons=None):
    panels = [mo.Html('<span id="submit-serial"></span>'), mo.md('''## 加做：單執行緒申請 4 核，會快四倍嗎？
    **程式相同、計算量相同、節點相同，只有申請的 CPU 數不同。**
    這一組對照實驗**刻意固定為 1 核與 4 核**，沿用你選的節點；上方 CPU 選單控制的是 srun／sbatch 練習與 90 秒工作。
    每個工作做三輪，通常需幾秒到數十秒。請照以下順序操作：

    1. 先停止或等待上方的 90 秒工作與其他實驗工作結束。
    2. 按「測量 1 CPU」，取得第一個 Job ID；這時只是提交成功，還沒代表計算完成。
    3. 等幾秒，按「更新比較結果」。必須讀到 1 CPU 工作 **COMPLETED 且有有效測量數據**，才會解鎖「測量 4 CPU」。若仍在排隊或執行，稍後再按一次更新。
    4. 按「測量 4 CPU」，取得第二個 Job ID。
    5. 等幾秒，再按「更新比較結果」，直到 4 CPU 工作也完成，查看兩組數據。

    **操作順序：測量 1 CPU → 等待 → 更新比較結果 → 測量 4 CPU → 等待 → 更新比較結果。**
    「更新比較結果」只重新查詢狀態與輸出，不會提交新工作，也不是重新整理瀏覽器。
    每個實驗的兩個測量各只能提交一次；想重測，請回上方用相同設定再按「套用參數並建立實驗」。''')]
    if not run_id:
        panels.append(mo.md('先在上方選節點與 CPU 數，建立實驗。'))
        return mo.vstack(panels)
    try:
        run, data = lab.load_run(run_id), lab.read_run(run_id)
    except Exception as exc:
        panels.append(mo.plain_text(f'讀取比較失敗：{exc}'))
        return mo.vstack(panels)
    results = {cpus: serial_result(data, cpus) for cpus in (1, 4)}
    panels.append(mo.plain_text(f"比較節點：{run['parameters']['node']} · 每次 1 task、128 MiB RAM · Python 單執行緒"))
    if event and event.get('ui_section') == 'serial' and event.get('ui_run_id') == run_id:
        panels.append(mo.plain_text('比較操作：' + event.get('status', '未確認') + ' · ' +
                                    str(event.get('reason') or event.get('error') or '指令已返回，請看下方工作狀態。')))
        panels.append(mo.accordion({'比較按鈕的完整回應': json_view(mo, event)}))
    for cpus in (1, 4):
        receipt = next((r for r in data['receipts'] if r['step_id'] == f'serial-{cpus}'), None)

        def measure(_, cpus=cpus):
            try:
                with mo.status.spinner(title=f'正在提交 {cpus} CPU 測量…'):
                    frozen = lab.load_run(run_id)
                    result = lab.execute_once(run_id, f'serial-{cpus}', serial_argv(frozen, cpus), effect='submit')
            except Exception as exc:
                result = {'status': 'failed', 'error': str(exc)}
            set_event({**result, 'ui_section': 'serial', 'ui_run_id': run_id})

        button = mo.ui.button(label=f'測量 {cpus} CPU', on_click=measure,
                               disabled=receipt is not None or (cpus == 4 and results[1] is None))
        if buttons is not None:
            buttons[f'serial-{cpus}'] = button
        panels.append(button)
        if cpus == 4 and receipt is None and results[1] is None:
            panels.append(mo.plain_text('尚未解鎖：先完成 1 CPU 測量，再按「更新比較結果」確認有效數據。'))
        if receipt:
            identifier = receipt.get('job_id')
            observed = data['jobs'].get(identifier, {})
            states = [state for job in observed.get('records', []) for state in job['job_state']]
            panels.append(mo.plain_text(f"{cpus} CPU · Job {identifier or '未確認'} · 提交 {receipt['status']} · 工作 {', '.join(states) or observed.get('status', '未確認')}"))
            if states == ['COMPLETED'] and results[cpus] is None:
                panels.append(mo.plain_text('尚無有效測量數據；請核對輸出檔、退出碼與工作身分。'))
        panels.append(mo.accordion({f'{cpus} CPU 的指令與提交回應': _terminal(
            mo, f'單執行緒 / {cpus} CPU', receipt or {'argv': serial_argv(run, cpus)}, pending=receipt is None)}))
    refresh_button = mo.ui.button(label='更新比較結果', on_click=lambda _: set_event(
        {'status': 'refreshed', 'ui_section': 'serial', 'ui_run_id': run_id}))
    if buttons is not None:
        buttons['refresh'] = refresh_button
    panels.append(refresh_button)
    rows = []
    for cpus, value in results.items():
        if value:
            rows.append({'申請 CPU': cpus, 'Job ID': value['job_id'], '允許 CPU': str(value['affinity']),
                         '耗時中位數（秒）': round(value['wall_seconds'], 4),
                         'CPU 時間中位數（秒）': round(value['cpu_seconds'], 4),
                         '平均使用幾核': round(value['average_cores'], 2),
                         '已申請 CPU 的使用比例': f"{value['average_cores'] / cpus:.1%}"})
    if rows:
        panels.append(mo.ui.table(table_rows(rows), selection=None))
    if all(results.values()):
        ratio = results[1]['wall_seconds'] / results[4]['wall_seconds']
        panels.append(mo.plain_text(f'實測加速比（1 核耗時 ÷ 4 核耗時）：{ratio:.2f} 倍。這是本次測量，不預設一定等於 1 或 4。'))
    panels.append(mo.accordion({'比較原理與程式碼': mo.vstack([mo.md('''
    | 看哪個數據？ | 怎麼理解？ |
    | --- | --- |
    | 允許 CPU | 申請 4 核時應列出 4 個邏輯 CPU，表示資源確實分配了 |
    | 耗時 | 每輪固定計算量實際花幾秒；不包含排隊、Python 啟動與提交指令的時間 |
    | CPU 時間 | 這條 process 真正獲得 CPU 執行的累計秒數 |
    | 平均使用幾核 | CPU 時間 ÷ 實際耗時；單執行緒通常接近 1，受到搶占時可能較低 |
    | 已申請 CPU 的使用比例 | 平均使用核數 ÷ 申請核數；使用約 1 核卻申請 4 核時約為 25% |

    **Slurm 分配資源，程式決定怎麼用。** 這裡沒有建立其他計算執行緒或 process，申請 4 核也不會自動拆成四份。
    想同時使用多核，程式需要 multiprocessing、OpenMP、MPI，或本身會平行運算的函式庫。
    三輪取中位數只能減少部分波動；背景程式、CPU 頻率及排程都會影響結果，不用「必須一樣快」當通過條件。
    這裡的核數指 Slurm CPU／Linux 邏輯 CPU；CPU 時間由程式讀取作業系統計時器，
    外部確認工作位置與 CPU 綁定請搭配上方的 Docker／Linux 觀察實驗。
    '''), mo.md('```python\n' + SERIAL_WORKLOAD + '\n```')])}))
    return mo.vstack(panels)
