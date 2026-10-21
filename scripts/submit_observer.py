"""Bounded Chapter 02 workload and external Linux observations, via explicit buttons."""
from datetime import datetime, timezone
import json
import shlex

import notebook_lab as lab
from environment_view import TERMINAL_CSS, _terminal
from lesson_common import job_id, submit
from notebook_views import json_view, table_rows
from slurm_cli import compose_argv, run_command


WORKLOAD = '''import time
end = time.monotonic() + 90
while time.monotonic() < end:
    sum(range(10000))
'''

# This runs in an independent observer process. No task stdout is read.
PROCESS_PROBE = '''import json, os, sys, time
from pathlib import Path
marker = sys.argv[1]
def sample():
    found = []
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            args = directory.joinpath('cmdline').read_bytes().rstrip(b'\\0').split(b'\\0')
            if not args or args[-1].decode(errors='replace') != marker:
                continue
            if args[0].rsplit(b'/', 1)[-1] not in (b'python3', b'python'):
                continue
            if directory.stat().st_uid != 1000:
                continue
            fields = directory.joinpath('stat').read_text().rsplit(')', 1)[1].split()
            status = directory.joinpath('status').read_text().splitlines()
            allowed = next(line.split(':', 1)[1].strip() for line in status if line.startswith('Cpus_allowed_list:'))
            found.append(dict(pid=int(directory.name), start_ticks=int(fields[19]),
                              cpu_ticks=int(fields[11])+int(fields[12]), last_cpu=int(fields[36]),
                              allowed_cpus=allowed, cgroup=directory.joinpath('cgroup').read_text().strip()))
        except (OSError, ValueError, IndexError, StopIteration):
            continue
    return found
before = sample()
time.sleep(1)
after = sample()
print(json.dumps(dict(before=before, after=after, ticks_per_second=os.sysconf('SC_CLK_TCK'))))
'''


def observer_argv(run):
    node = run['parameters']['node']
    cpus = run['parameters']['cpus']
    if node not in {'cpu01', 'cpu02'}:
        raise ValueError('觀察工作只允許 cpu01 或 cpu02')
    if type(cpus) is not int or cpus not in (1, 4):
        raise ValueError('觀察工作只允許申請 1 或 4 CPU')
    marker = lab.job_name(run['run_id'], 'observer')
    command = shlex.join(['srun', '--cpu-bind=threads', 'python3', '-c', WORKLOAD, marker])
    return submit(run, 'observer', command=command, options=(
        f'--nodelist={node}', '--partition=cpu', '--nodes=1', '--ntasks=1',
        f'--cpus-per-task={cpus}', '--mem=128M', '--time=00:02:00'))


def observer_steps():
    return {'observer': lab.Step('submit', observer_argv),
            'observer-stop': lab.Step('cancel', lambda run: compose_argv('scancel', job_id(run, 'observer')))}


def _cpu_set(value):
    result = set()
    for part in value.split(','):
        limits = part.strip().split('-')
        if len(limits) == 1:
            result.add(int(limits[0]))
        elif len(limits) == 2:
            first, last = map(int, limits)
            if first < 0 or last < first or last - first > 65536:
                raise ValueError('Invalid CPU range')
            result.update(range(first, last + 1))
        else:
            raise ValueError('Invalid CPU list')
    return result


def evaluate_samples(node, config, samples, *, expected_cpus):
    """Accept only the same kernel PID/start-time identity across both samples."""
    before, after = samples['before'], samples['after']
    row = {'節點': node, '取樣前／後 process 數': f'{len(before)} / {len(after)}',
           'PID（容器內）': '未確認', 'CPU 秒增加': None, '最近 CPU': None,
           '允許 CPU': '未確認', '容器 cpuset': config['cpuset'], '判讀': '未找到持續執行的同一 process'}
    if config.get('pid_mode') not in ('', 'private'):
        row['判讀'] = '容器共用 PID namespace，不能據此判定節點歸屬'
        return row
    if len(before) != 1 or len(after) != 1:
        return row
    first, last = before[0], after[0]
    if (first['pid'], first['start_ticks']) != (last['pid'], last['start_ticks']):
        row['判讀'] = '兩次取樣不是同一 process，不能比較 CPU 時間'
        return row
    ticks = samples['ticks_per_second']
    if ticks <= 0:
        raise ValueError('Invalid clock tick rate')
    delta = (last['cpu_ticks'] - first['cpu_ticks']) / ticks
    allowed = _cpu_set(last['allowed_cpus'])
    cpuset = _cpu_set(config['cpuset'])
    row.update({'PID（容器內）': last['pid'], 'CPU 秒增加': round(delta, 4),
                '最近 CPU': last['last_cpu'], '允許 CPU': last['allowed_cpus']})
    if not allowed or len(allowed) != expected_cpus or not allowed <= cpuset or last['last_cpu'] not in allowed:
        row['判讀'] = f'CPU 綁定與本次 {expected_cpus} CPU／容器 cpuset 不符'
    elif delta > 0:
        row['判讀'] = '已觀察到實際 CPU 運算'
    else:
        row['判讀'] = 'process 存在，但本次未觀察到 CPU 時間增加'
    return row


def _query(argv):
    record = {'argv': argv}
    try:
        process = run_command(argv, cwd=lab.ROOT, timeout=6)
        record.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
        if process.returncode:
            record['error'] = f'查詢退出碼 {process.returncode}'
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
    return record


def observe_run(run_id):
    data = lab.read_run(run_id)
    receipt = next((r for r in data['receipts'] if r['step_id'] == 'observer'), None)
    if not receipt or receipt['status'] != 'succeeded' or not receipt.get('job_id'):
        return {'status': 'blocked', 'reason': '先啟動觀察工作；提交結果未確認時不能把候選 process 當成已確認工作。'}
    observed = data['jobs'].get(receipt['job_id'], {})
    if observed.get('status') != 'observed' or not observed.get('records'):
        return {'status': 'blocked', 'reason': '目前無法核對 Slurm 工作身分；請先看工作查詢與錯誤。'}
    states = {state for job in observed['records'] for state in job['job_state']}
    if 'RUNNING' not in states:
        return {'status': 'not-running', 'reason': '目前工作狀態：' + ', '.join(sorted(states)),
                'observed_at': datetime.now(timezone.utc).isoformat()}
    marker = lab.job_name(run_id, 'observer')
    result = {'status': 'inconclusive', 'run_id': run_id, 'job_id': receipt['job_id'],
              'target': data['parameters']['node'], 'started_at': datetime.now(timezone.utc).isoformat(),
              'rows': [], 'commands': [], 'errors': [], 'kernel_samples': {}}
    for node in ('cpu01', 'cpu02'):
        top = _query(['docker', 'compose', 'top', node])
        identity = _query(['docker', 'compose', 'ps', '--all', '--quiet', node])
        result['commands'].extend([top, identity])
        identifiers = (identity.get('stdout') or '').split()
        if identity.get('error') or len(identifiers) != 1:
            result['errors'].append(f'{node}: 無法唯一識別容器；請展開原始回應')
            continue
        config = _query(['docker', 'inspect', '--format',
                         '{"cpuset":{{json .HostConfig.CpusetCpus}},"pid_mode":{{json .HostConfig.PidMode}}}',
                         identifiers[0]])
        kernel = _query(compose_argv('python3', '-c', PROCESS_PROBE, marker, user='root', service=node))
        result['commands'].extend([config, kernel])
        try:
            if any(record.get('error') for record in (top, config, kernel)):
                raise ValueError(f'{node} 外部查詢失敗；請展開實際回應')
            settings, samples = json.loads(config['stdout']), json.loads(kernel['stdout'])
            result['kernel_samples'][node] = samples
            row = evaluate_samples(node, settings, samples, expected_cpus=data['parameters']['cpus'])
            row['Docker 清單含唯一標記'] = marker in top['stdout']
            result['rows'].append(row)
        except (ValueError, KeyError, TypeError) as exc:
            result['errors'].append(f'{node}: {exc}')
    if not result['errors'] and len(result['rows']) == 2:
        target = next(row for row in result['rows'] if row['節點'] == result['target'])
        other = next(row for row in result['rows'] if row['節點'] != result['target'])
        if (target['判讀'] == '已觀察到實際 CPU 運算' and target['Docker 清單含唯一標記']
                and other['取樣前／後 process 數'] == '0 / 0' and not other['Docker 清單含唯一標記']
                and other['判讀'] != '容器共用 PID namespace，不能據此判定節點歸屬'):
            result['status'] = 'confirmed'
    result['observed_at'] = datetime.now(timezone.utc).isoformat()
    return result


def observer_panel(mo, run_id, evidence, set_evidence, set_event, *, buttons=None):
    panels = [mo.Html(TERMINAL_CSS), mo.Html('<span id="submit-external"></span>'),
              mo.md('''## 加做：從外部確認它真的在指定節點運算
              按「啟動 90 秒計算」，再按「觀察 process 與 CPU」；每次觀察約需幾秒。
              觀察資料來自 **Docker process 清單與 Linux /proc**，不讀計算程式自己印出的 hostname。
              本工作使用上方建立實驗時選定的**節點與 CPU 數**，申請 **128 MiB RAM**。
              先看按鈕下方的提交回應，拿到 Job ID 後再觀察；不用等待 90 秒才看到回應。
              想提早結束可以按「停止觀察工作」，或使用下方的「只清理本次實驗」。''')]
    if not run_id:
        panels.append(mo.md('先在上方建立實驗，或從側欄恢復既有 run，再回來操作。'))
        return mo.vstack(panels)
    try:
        run = lab.load_run(run_id)
        data = lab.read_run(run_id)
        receipt = next((r for r in data['receipts'] if r['step_id'] == 'observer'), None)
        stopped = any(r['step_id'] == 'observer-stop' for r in data['receipts'])
    except Exception as exc:
        panels.append(mo.plain_text(f'讀取實驗失敗：{exc}'))
        return mo.vstack(panels)

    def start(_):
        try:
            with mo.status.spinner(title='正在提交觀察工作…'):
                frozen = lab.load_run(run_id)
                result = lab.execute_once(run_id, 'observer', observer_argv(frozen), effect='submit')
        except Exception as exc:
            result = {'status': 'failed', 'error': str(exc)}
        set_evidence({'run_id': run_id, 'operation': {'action': '啟動', **result}})
        set_event(result)

    def observe(_):
        try:
            with mo.status.spinner(title='正在讀取兩個節點的 process 與 CPU…'):
                result = observe_run(run_id)
        except Exception as exc:
            result = {'status': 'failed', 'error': str(exc)}
        previous = evidence if evidence and evidence.get('run_id') == run_id else {}
        set_evidence({'operation': previous.get('operation'), **result, 'run_id': run_id})

    def stop(_):
        try:
            with mo.status.spinner(title='正在取消觀察工作…'):
                frozen = lab.load_run(run_id)
                result = lab.execute_once(run_id, 'observer-stop', observer_steps()['observer-stop'].argv(frozen), effect='cancel')
        except Exception as exc:
            result = {'status': 'failed', 'error': str(exc)}
        previous = evidence if evidence and evidence.get('run_id') == run_id else {}
        set_evidence({**previous, 'run_id': run_id, 'operation': {'action': '停止', **result}})
        set_event(result)

    identifier = receipt.get('job_id') if receipt else None
    observed = data['jobs'].get(identifier, {})
    states = {state for job in observed.get('records', []) for state in job['job_state']}
    panels.append(mo.plain_text(f"本次設定：{run['parameters']['node']} · {run['parameters']['cpus']} CPU / task · 128 MiB RAM · Job ID：{identifier or '尚未確認'} · Slurm 狀態：{', '.join(sorted(states)) or '尚無可核對紀錄'}"))
    if 'PENDING' in states:
        reasons = [str(job.get('state_reason') or '未提供') for job in observed.get('records', [])]
        panels.append(mo.plain_text('已提交，正在排隊。等待原因：' + ', '.join(reasons)))
    start_button = mo.ui.button(label='啟動 90 秒計算', on_click=start, disabled=receipt is not None)
    observe_button = mo.ui.button(label='觀察 process 與 CPU', on_click=observe,
                                  disabled=not receipt or receipt['status'] != 'succeeded' or not identifier)
    stop_button = mo.ui.button(label='停止觀察工作', on_click=stop, kind='danger',
                               disabled=stopped or observed.get('status') != 'observed' or not states & {'RUNNING', 'PENDING'})
    if buttons is not None:
        buttons.update(start=start_button, observe=observe_button, stop=stop_button)
    panels.append(mo.hstack([start_button, observe_button, stop_button], wrap=True))
    if evidence and evidence.get('run_id') == run_id and evidence.get('operation'):
        operation = evidence['operation']
        status = operation.get('status', '未確認')
        message = {'succeeded': '指令已成功返回；工作狀態請看上方 Slurm 狀態',
                   'blocked': '操作被擋住，尚未送出這次指令',
                   'failed': '指令失敗', 'unknown': '結果未確認，請先核對紀錄，勿重新提交'}.get(status, status)
        panels.append(mo.plain_text(f"{operation['action']}結果：{status} · {message}"))
        if operation.get('reason') or operation.get('error'):
            panels.append(mo.plain_text(str(operation.get('reason') or operation['error'])))
        panels.append(mo.accordion({'這次按鈕操作的完整回應': json_view(mo, operation)}))
    if receipt:
        panels.append(mo.plain_text(f"已保存的提交結果：{receipt['status']} · Job ID：{identifier or '尚未確認'}"))
    stop_receipt = next((r for r in data['receipts'] if r['step_id'] == 'observer-stop'), None)
    if stop_receipt:
        panels.append(_terminal(mo, '停止觀察工作 / 實際回應', stop_receipt))
    panels.append(_terminal(mo, '90 秒計算 / 提交指令與回應', receipt or {'argv': observer_argv(run)},
                            pending=receipt is None, error_label='執行／確認錯誤',
                            note='sbatch 只負責提交，stdout 的 Job ID 不代表已運算完成。計算本身在指定節點執行，最多 2 分鐘。'))
    if evidence and evidence.get('run_id') == run_id and evidence.get('status'):
        verdict = {'confirmed': '已從外部觀察到：指定容器內的 process 確實累積 CPU 運算時間',
                   'inconclusive': '本次證據不足，不能判定成功；可在工作執行期間再按觀察',
                   'not-running': '工作目前沒有執行；若已結束，就沒有即時 process 可觀察',
                   'blocked': '目前無法觀察', 'failed': '觀察失敗'}.get(evidence['status'], evidence['status'])
        panels.append(mo.plain_text(verdict))
        panels.append(mo.plain_text('這是該次取樣的結果，不代表目前仍在運算。取樣完成時間：' + evidence.get('observed_at', '未取得')))
        if evidence.get('reason') or evidence.get('error'):
            panels.append(mo.plain_text(evidence.get('reason') or evidence['error']))
        if evidence.get('rows'):
            panels.append(mo.ui.table(table_rows(evidence['rows']), selection=None))
        if evidence.get('errors'):
            panels.append(mo.plain_text('\n'.join(evidence['errors'])))
        panels.append(mo.accordion({f'{index + 1}. 實際觀察指令與原始回應': _terminal(
            mo, '外部觀察 / 實際回應', record) for index, record in enumerate(evidence.get('commands', []))}, multiple=True))
        panels.append(mo.accordion({'完整觀察證據': json_view(mo, evidence)}))
    panels.append(mo.accordion({'怎麼判讀外部觀察？': mo.md('''

    | 觀察項目 | 要看什麼？ |
    | --- | --- |
    | process 數 | 指定節點兩次取樣各有 1 個唯一標記的 process；另一節點為 0 |
    | PID 與啟動時間 | 兩次都相同，才能確認是在比較同一個 process |
    | CPU 秒增加 | Linux 累計的 CPU ticks 在約一秒取樣間隔內增加，證明它不是只在等待 |
    | 最近 CPU | /proc/PID/stat 的 processor 欄位，意義同 ps 的 PSR；不是實體伺服器編號 |
    | 允許 CPU／容器 cpuset | task 允許的 CPU 數應與本次選定的 1 或 4 相同，且落在 Docker 設定的 CPU 範圍內 |

    **這支程式只有一條計算執行緒。** 選 4 CPU 會保留 4 個 CPU 的資源，允許它在這些 CPU 間移動，
    但不會同時用滿 4 核；「最近 CPU」改變也不表示已平行化。下方另有 1 核與 4 核的耗時比較。

    展開原始回應，可以對照 Docker process 清單、目前容器 cpuset 與 /proc 的兩次取樣；不填入模擬成功結果。
    cpu01／cpu02 是同一台主機上的兩個容器，本實驗確認的是容器與邏輯 CPU。
    若剛提交仍在 PENDING，稍後再觀察；若 process 剛啟動或剛結束，可能取樣不足，不能當作成功。
    「只讀刷新」更新工作狀態，不會自動啟動計算或執行這個外部取樣。
    觀察工作也屬於本次 run；先停止或等它結束，再做下方的比較、驗證或執行 smoke。
    同一次實驗只啟動一次；結束後若要重做，請建立新實驗。重新開頁後可恢復既有 run，但需重新取樣才有外部觀察結果。
    欄位定義：[Linux process stat](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)。''')}))
    return mo.vstack(panels)
