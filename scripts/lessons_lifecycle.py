"""Fixed lifecycle workloads and read-only evidence checks for notebooks 08–11."""
import subprocess
import time

import notebook_lab as lab
from lesson_common import (
    PROBE, Pending, case, exit_failed, job_id, json_lines, probe, receipt, records, require,
    state, submit, text, view,
)
from notebook_queries import query_nodes
from slurm_cli import compose_argv, run_command


def _guard(check):
    def precondition(run, snapshot):
        try:
            return check(view(run), snapshot)
        except (Pending, AssertionError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
            return str(exc)
    return precondition


def _done(data, step):
    result = receipt(data, step)
    if not result:
        raise Pending(f'請先執行 {step}')
    require(result['status'] == 'succeeded', f'{step} 未成功或結果不確定，不能繼續：{result["status"]}')
    return result


def _saved(data, step):
    result = _done(data, step)
    require(isinstance(result.get('evidence'), dict), f'{step} 缺少動作前證據')
    return result['evidence']


def _identity(data, step, node, cpus=1):
    values = [r for r in json_lines(text(data, step)) if 'affinity' in r and 'sum' in r]
    require(values, f'{step} 缺少 CPU 計算輸出')
    # The configured set is checked against the same source as the CLI smoke suite.
    from smoke import CPUSETS
    allowed = CPUSETS
    for value in values:
        require(value.get('hostname') == node and value.get('uid') == 1000
                and value.get('job_id') == job_id(data, step), f'{step} 工作身分不符：{value}')
        require(value.get('sum') == 50005000 and len(value['affinity']) == cpus
                and set(value['affinity']) <= allowed[node], f'{step} 計算或 affinity 不符：{value}')
    return values


def _holder(data, step='holder', seconds=180, node='cpu01', cpus=4):
    rows = state(data, step, 'RUNNING')
    require(len(rows) == 1 and rows[0].get('start_time'), f'{step} 缺少唯一 StartTime')
    remaining = rows[0]['start_time'] + seconds - time.time()
    require(remaining > 0, f'{step} 操作窗口已過期，請清理並建立新 run')
    values = _identity(data, step, node, cpus)
    require(any(r.get('started') is True for r in values), f'{step} 尚未輸出 started marker')
    return {'job': rows[0], 'started': values, 'remaining_seconds': remaining}


def _released(data, step, node, cpus):
    rows = state(data, step, 'COMPLETED')
    values = _identity(data, step, node, cpus)
    require(any(r.get('released') is True for r in values), f'{step} 沒有真正收到 release marker')
    return {'job': rows, 'output': values}


def _pending(data, step='waiter', reasons=None):
    """Waiting evidence: PENDING now, never requeued, and no workload output yet.

    A PENDING record's StartTime is the backfill scheduler's *expected* start
    (e.g. behind an exclusive holder), not proof that the job ever ran.
    """
    rows = state(data, step, 'PENDING')
    require(all(r['raw'].get('restart_cnt') == 0 for r in rows),
            f'{step} 曾被 requeue（restart_cnt>0），不能作為等待證據')
    require(not text(data, step).strip(), f'{step} 等待中卻已有輸出')
    if reasons:
        require(all(r['state_reason'] in reasons for r in rows), f'{step} 非預期的等待原因：{rows}')
    return rows


def _node(snapshot, name='cpu02'):
    source = (snapshot or {}).get('sources', {}).get('nodes')
    if source is None:
        source = query_nodes()
    require(source and source.get('status') == 'ok' and not source.get('stale'), '節點查詢失敗，不能推論健康狀態')
    nodes = [n for n in source['data'] if n['name'] == name]
    require(len(nodes) == 1, f'找不到唯一節點 {name}')
    return nodes[0]


def _drained(data, snapshot):
    node = _node(snapshot)
    require(any('DRAIN' in s for s in node['state'])
            and node['reason'] == f'demo-{data["run_id"]}', 'cpu02 不再由本次 DRAIN Reason 所有')
    return node


def _hold_submit(run, step, node, *, seconds=180, exclusive=True):
    options = [f'--nodelist={node}', '--time=00:05:00' if seconds == 240 else '--time=00:04:00']
    if exclusive:
        options += ['--cpus-per-task=4', '--exclusive']
    return submit(run, step, command=probe('hold', '--release', f'{run["container_dir"]}/{step}.release',
                                         '--seconds', seconds), options=options)


def _release(run, step='holder'):
    return lab.local_argv(run['run_id'], 'release', f'{step}.release')


def _affinity(run, step, node='cpu01', exclusive=False):
    options = [f'--nodelist={node}']
    if exclusive:
        options += ['--cpus-per-task=4', '--exclusive']
    return submit(run, step, command=probe('affinity'), options=options)


def _oom(data):
    rows = state(data, 'offender', {'FAILED', 'OUT_OF_MEMORY'})
    for row in rows:
        code = row['exit_code']
        require(exit_failed(code), 'OOM 缺少明確非零 ExitCode')
    values = json_lines(text(data, 'offender'))
    task = next((r for r in values if 'allocation_ceiling_mib' in r), None)
    require(task and task['allocation_ceiling_mib'] == 256, '缺少最多 256 MiB 的實際配置紀錄')
    _identity(data, 'offender', 'cpu01')
    limit = str(128 * 1024 * 1024)
    numeric = [int(r['memory.max']) for r in task['limits'] if r['memory.max'].isdigit()]
    require(numeric and min(numeric) == int(limit), '缺少 128 MiB job cgroup 上限')
    require(any(r['memory.max'] == limit and r['memory.swap.max'] == '0' for r in task['limits']), 'job swap 未停用')
    observations = [r for r in values if r.get('event') == 'oom_observation']
    require(any(entry['memory.max'] == limit and entry['events'].get('oom_kill', 0) > 0
                for record in observations for entry in record['limits']), '缺少該 128 MiB cgroup 的 kernel oom_kill event')
    require(not any('unexpected_allocation_success_mib' in r for r in values), '配置全部成功，並非 OOM 證據')
    return {'job': rows, 'task': task, 'kernel_events': observations}


def _oom_summary(data):
    """Field-level OOM evidence; full events can exceed the 64 KiB preview."""
    values = json_lines(text(data, 'offender'))
    task = next((r for r in values if 'allocation_ceiling_mib' in r), None)
    after = next((r for r in values if r.get('event') == 'oom_observation'), None)
    note = ('「前」來自 offender task 開始時讀到的 cgroup（含祖先層），「後」來自 srun 結束後 batch shell 的 '
            '`oom-events` 觀測；兩者只在共同祖先（job 層）重疊。採用為證據＝該層 `memory.max=134217728`（128 MiB）'
            '且之後 `oom_kill>0`；`memory.swap.max=0` 表示不能用 swap 逃過限制。路徑省略 '
            '`/sys/fs/cgroup/system.slice/slurmstepd.scope/` 前綴；完整內容可在下方輸出區下載。')
    if task is None:
        return [('OOM 欄位摘要', [], '尚無 offender 的 limits 輸出；job 開始執行後才會出現。')]
    before = {entry['path']: entry for entry in task.get('limits', [])}
    later = {entry['path']: entry for entry in (after or {}).get('limits', [])}
    limit = str(128 * 1024 * 1024)
    rows = []
    prefix = '/sys/fs/cgroup/system.slice/slurmstepd.scope/'
    for path in list(before) + [p for p in later if p not in before]:
        first, last = before.get(path), later.get(path)
        entry = last or first
        rows.append({'採用為證據': '是' if last and last['memory.max'] == limit and last['events'].get('oom_kill', 0) > 0 else '否',
                     'cgroup': path.replace(prefix, '…/') if path.startswith(prefix) else path,
                     'memory.max': entry['memory.max'], 'memory.swap.max': entry['memory.swap.max'],
                     'oom_kill 前': first['events'].get('oom_kill') if first else '（task 未讀到此層）',
                     'oom_kill 後': last['events'].get('oom_kill') if last else
                     ('（batch 觀測不含此層）' if after else '尚未觀測')})
    rows.sort(key=lambda row: row['採用為證據'] != '是')
    return [('OOM 欄位摘要', rows, note)]


def _memory_release(data, snapshot):
    return {'oom': _oom(data), 'neighbor_alive_after_oom': _holder(data, 'neighbor', node='cpu01', cpus=1)}


def _memory_reuse(data, snapshot):
    return {'release': _saved(data, 'release-neighbor'), 'neighbor': _released(data, 'neighbor', 'cpu01', 1)}


def _verify_memory(data):
    def evidence():
        result = _memory_reuse(data, {})
        result['offender'] = _oom(data)
        result['reuse'] = state(data, 'reuse', 'COMPLETED')
        result['reuse_output'] = _identity(data, 'reuse', 'cpu01', 4)
        return result
    return [case('memory-oom-isolation', evidence)]


def _processes(data):
    values = [r for r in json_lines(text(data, 'descendants')) if r.get('role') in {'parent', 'child', 'grandchild'}]
    require(len(values) == 3 and {r['role'] for r in values} == {'parent', 'child', 'grandchild'}, '等待三代程序 marker：必須恰有 parent/child/grandchild')
    require(len({r.get('pid') for r in values}) == 3 and all(
        type(r.get('pid')) is int and r['pid'] > 0 and str(r.get('starttime', '')).isdigit()
        and r.get('hostname') == 'cpu01' for r in values), 'PID/starttime/hostname 證據無效')
    return values


def _process_check(data, *, gone):
    identities = _processes(data)
    command = compose_argv('python3', PROBE, 'check-processes', '--marker',
                           f'{data["container_dir"]}/process', user='root', service='cpu01')
    result = run_command(command, cwd=lab.ROOT, timeout=5)
    values = json_lines(result.stdout)
    require(result.returncode in (0, 1) and len(values) == 1 and values[0].get('record_count') == 3,
            f'程序檢查失敗：{result.stdout} {result.stderr}')
    observed = values[0]
    expected = {(r['pid'], str(r['starttime']), r['role']) for r in identities}
    live = {(r['pid'], str(r['starttime']), r['role']) for r in observed.get('live', [])}
    if gone:
        if result.returncode != 0 or live:
            roles = '、'.join(sorted(role for _, _, role in live)) or '未知'
            raise Pending(f'正在等 Slurm 清理程序與 cgroup：{roles} 仍以相同 PID/starttime 存活，'
                          '清乾淨後本步驟會自動解鎖（不要自行 kill）')
    else:
        require(result.returncode == 1 and live == expected, '三代程序尚未同時存活，或工作已過期')
    return {'identities': identities, 'observation': observed, 'argv': command}


def _cancel_pre(data, snapshot):
    require(data['parameters']['mode'] == 'cancel', 'timeout 模式不可手動取消；請等待 TIMEOUT')
    running = state(data, 'descendants', 'RUNNING')
    return {'running': running, 'processes_before_cancel': _process_check(data, gone=False)}


def _lifecycle_reuse(data, snapshot):
    mode = data['parameters']['mode']
    require(mode in {'cancel', 'timeout'}, '無效模式')
    target = 'CANCELLED' if mode == 'cancel' else 'TIMEOUT'
    try:
        ended = state(data, 'descendants', target)
    except Pending:
        rows = records(data, 'descendants')
        if any('COMPLETING' in row['job_state'] for row in rows):
            raise Pending(f'正在等 Slurm 終止程序並清理 cgroup（COMPLETING），之後才會變成 {target}')
        raise
    evidence = {'ended': ended, 'processes_after': _process_check(data, gone=True)}
    if mode == 'cancel':
        evidence['before_cancel'] = _saved(data, 'cancel')
    else:
        require(not receipt(data, 'cancel'), 'timeout run 不可使用取消動作')
        for row in ended:
            require(row.get('start_time') and row.get('end_time')
                    and row['end_time'] - row['start_time'] >= 60, 'TIMEOUT 缺少自然執行滿一分鐘證據')
    return evidence


def _verify_lifecycle(data):
    def evidence():
        result = _lifecycle_reuse(data, {})
        result['before_reuse'] = _saved(data, 'reuse')
        result['reuse'] = state(data, 'reuse', 'COMPLETED')
        result['reuse_output'] = _identity(data, 'reuse', 'cpu01', 4)
        return result
    return [case('time-limit-descendant-cleanup' if data['parameters']['mode'] == 'timeout' else 'cancellation-descendant-cleanup', evidence)]


def _drain_pre(data, snapshot):
    holder = _holder(data, node='cpu02')
    node = _node(snapshot)
    require(not any('DRAIN' in s for s in node['state']), 'cpu02 原已 DRAIN，拒絕接管')
    return {'holder_before_drain': holder, 'node_before': node}


def _drain_waiter(data, snapshot):
    _done(data, 'drain')
    return {'holder_survived_drain': _holder(data, node='cpu02'), 'drained': _drained(data, snapshot)}


def _drain_release(data, snapshot):
    return {'holder': _holder(data, node='cpu02'), 'pending_before_release': _pending(data),
            'drained': _drained(data, snapshot)}


def _resume_pre(data, snapshot):
    return {'release_evidence': _saved(data, 'release-holder'),
            'holder_completed_while_drained': _released(data, 'holder', 'cpu02', 4),
            'pending_after_holder_completed': _pending(data), 'drained': _drained(data, snapshot)}


def _verify_drain(data):
    def evidence():
        result = {'drain': _saved(data, 'drain'), 'waiter_submission': _saved(data, 'waiter'),
                  'resume': _saved(data, 'resume'), 'holder': _released(data, 'holder', 'cpu02', 4),
                  'waiter': state(data, 'waiter', 'COMPLETED'), 'output': _identity(data, 'waiter', 'cpu02')}
        resumed_at = receipt(data, 'resume')['started']
        from datetime import datetime
        require(all(r['start_time'] >= int(datetime.fromisoformat(resumed_at).timestamp()) for r in result['waiter']),
                'waiter 早於 RESUME 開始執行')
        node = _node({})
        require(not any(any(bad in s for bad in ('DRAIN', 'DOWN', 'FAIL', 'UNKNOWN', 'NOT_RESPONDING'))
                        for s in node['state']), 'cpu02 未恢復健康狀態')
        result['node_after'] = node
        return result
    return [case('drain-resume', evidence)]


def _completed_pre(data, snapshot):
    return {'completed': state(data, 'completed', 'COMPLETED'),
            'output': _identity(data, 'completed', 'cpu02')}


def _restart_pre(data, snapshot):
    return {'completed': state(data, 'completed', 'COMPLETED'),
            'completed_output': text(data, 'completed'),
            'active': _holder(data, seconds=240),
            'pending': _pending(data, reasons={'Resources', 'Priority'})}


def _recovery_release(data, snapshot):
    before = _saved(data, 'restart')
    active = _holder(data, seconds=240)
    require(active['job']['start_time'] == before['active']['job']['start_time'], 'controller 重啟後 active StartTime 改變')
    completed = state(data, 'completed', 'COMPLETED')
    _identity(data, 'completed', 'cpu02')
    require(text(data, 'completed') == before['completed_output'], 'controller 重啟後已完成輸出改變')
    return {'before_restart': before, 'active_after_restart': active,
            'pending_after_restart': _pending(data, reasons={'Resources', 'Priority'}),
            'completed_after_restart': completed, 'completed_output': text(data, 'completed')}


def _verify_recovery(data):
    def evidence():
        result = {'preservation': _saved(data, 'release-holder'),
                  'holder': _released(data, 'holder', 'cpu01', 4),
                  'waiter': state(data, 'waiter', 'COMPLETED'), 'waiter_output': _identity(data, 'waiter', 'cpu01'),
                  'completed': state(data, 'completed', 'COMPLETED')}
        before = _saved(data, 'restart')
        require(text(data, 'completed') == before['completed_output'], '已完成輸出沒有保留')
        nodes = {}
        source = query_nodes()
        for name in ('cpu01', 'cpu02', 'gpu01'):
            node = _node({'sources': {'nodes': source}}, name)
            require(not any(any(bad in s for bad in ('DRAIN', 'DOWN', 'FAIL', 'UNKNOWN', 'NOT_RESPONDING'))
                            for s in node['state']), f'{name} 尚未重新連線健康')
            nodes[name] = node
        result['reconnected_nodes'] = nodes
        return result
    return [case('controller-restart-persistence', evidence)]


def get_lesson(chapter):
    if chapter == '07-memory':
        steps = {
            'neighbor': lab.Step('submit', lambda r: _hold_submit(r, 'neighbor', 'cpu01', exclusive=False)),
            'offender': lab.Step('submit', lambda r: submit(r, 'offender', options=['--nodelist=cpu01'],
                command='set +e; ' + probe('memory') + '; status=$?; python3 ' + PROBE + ' oom-events; exit "$status"'),
                _guard(lambda d, s: {'neighbor_before_oom': _holder(d, 'neighbor', node='cpu01', cpus=1)})),
            'release-neighbor': lab.Step('local', lambda r: _release(r, 'neighbor'), _guard(_memory_release)),
            'reuse': lab.Step('submit', lambda r: _affinity(r, 'reuse', exclusive=True), _guard(_memory_reuse)),
        }
        lesson = {'title': '07｜記憶體失敗與鄰居隔離', 'fields': {'memory_mib': [128]}, 'steps': steps,
                  'labels': {'neighbor': '1 啟動鄰居 holder（180 秒）', 'offender': '2 執行有界 128 MiB OOM 工作',
                             'release-neighbor': '3 證明 OOM 與鄰居存活，再釋放鄰居', 'reuse': '4 驗證資源重用'},
                  'verify': _verify_memory, 'cases': ['memory-oom-isolation'], 'holder_seconds': {'neighbor': 180},
                  'summaries': _oom_summary}
    elif chapter == '07-lifecycle':
        steps = {
            'descendants': lab.Step('submit', lambda r: submit(r, 'descendants',
                command=probe('descendants', '--marker', f'{r["container_dir"]}/process', '--seconds', 180),
                options=['--nodelist=cpu01', '--time=00:01:00' if r['parameters']['mode'] == 'timeout' else '--time=00:04:00'])),
            'cancel': lab.Step('cancel', lambda r: compose_argv('scancel', job_id(r, 'descendants')), _guard(_cancel_pre)),
            'reuse': lab.Step('submit', lambda r: _affinity(r, 'reuse', exclusive=True), _guard(_lifecycle_reuse)),
        }
        lesson = {'title': '07｜取消、限時與三代程序清理', 'fields': {'mode': ['timeout', 'cancel']}, 'steps': steps,
                  'labels': {'descendants': '1 啟動三代程序', 'cancel': '2 僅 cancel 模式：確認三代存活後取消',
                             'reuse': '3 確認相同 PID/starttime 已消失並重用四 CPU'},
                  'applicable': lambda r: ['descendants', 'cancel', 'reuse'] if r['parameters']['mode'] == 'cancel' else ['descendants', 'reuse'],
                  'timeline': ['descendants'],
                  'verify': _verify_lifecycle, 'cases': ['cancellation-descendant-cleanup', 'time-limit-descendant-cleanup']}
    elif chapter == '09-drain':
        steps = {
            'holder': lab.Step('submit', lambda r: _hold_submit(r, 'holder', 'cpu02')),
            'drain': lab.Step('drain', lambda r: compose_argv('scontrol', 'update', 'NodeName=cpu02',
                'State=DRAIN', f'Reason=demo-{r["run_id"]}', user='root'), _guard(_drain_pre)),
            'waiter': lab.Step('submit', lambda r: _affinity(r, 'waiter', 'cpu02'), _guard(_drain_waiter)),
            'release-holder': lab.Step('local', _release, _guard(_drain_release)),
            'resume': lab.Step('resume', lambda r: compose_argv('scontrol', 'update', 'NodeName=cpu02',
                'State=RESUME', user='root'), _guard(_resume_pre)),
        }
        lesson = {'title': '09｜DRAIN 排空與 RESUME', 'fields': {'node': ['cpu02']}, 'steps': steps,
                  'labels': {'holder': '1 啟動 cpu02 holder（180 秒）', 'drain': '2 DRAIN cpu02',
                             'waiter': '3 提交 waiter', 'release-holder': '4 保存等待證據並釋放 holder',
                             'resume': '5 holder 完成且 waiter 仍等待後 RESUME'},
                  'confirmations': {'drain': 'DRAIN cpu02', 'resume': 'RESUME cpu02'},
                  'verify': _verify_drain, 'cases': ['drain-resume'], 'holder_seconds': {'holder': 180}}
    elif chapter == '09-recovery':
        steps = {
            'completed': lab.Step('submit', lambda r: _affinity(r, 'completed', 'cpu02')),
            'holder': lab.Step('submit', lambda r: _hold_submit(r, 'holder', 'cpu01', seconds=240), _guard(_completed_pre)),
            'waiter': lab.Step('submit', lambda r: _affinity(r, 'waiter'),
                _guard(lambda d, s: {'active': _holder(d, seconds=240)})),
            'restart': lab.Step('restart-controller', lambda r: ['docker', 'compose', 'restart', 'controller'], _guard(_restart_pre)),
            'release-holder': lab.Step('local', _release, _guard(_recovery_release)),
            'restore': lab.Step('restore-controller', lambda r: ['docker', 'compose', 'up', '-d', '--no-build', 'controller']),
        }
        lesson = {'title': '09｜Controller 重啟與證據復原', 'fields': {'service': ['controller']}, 'steps': steps,
                  'labels': {'completed': '1 提交基準工作並等待完成', 'holder': '2 啟動 holder（240 秒）',
                             'waiter': '3 排入 waiter', 'restart': '4 保存證據並重啟 controller',
                             'release-holder': '5 查核狀態保存後釋放 holder', 'restore': '故障復原：啟動 controller'},
                  'confirmations': {'restart': 'RESTART controller', 'restore': 'RESTORE controller'},
                  'optional': {'restore'},
                  'verify': _verify_recovery, 'cases': ['controller-restart-persistence'], 'holder_seconds': {'holder': 240}}
    else:
        raise ValueError(f'Unknown lifecycle chapter: {chapter}')
    lesson.update(chapter=chapter, sources=['cpu_probe.py'])
    lab.register_chapter(chapter, steps, verify=lesson['verify'])
    return lesson
