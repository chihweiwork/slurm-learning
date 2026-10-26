"""GPU lessons: explicit submissions and read-only, scenario-specific evidence."""
import errno
import json
import subprocess
import time

import notebook_lab as lab
from gpu_smoke import (
    GPU_OPTIONS, container_command, cpu_absent_command, denied_command,
    direct_command, holder_command, outer_cgroup_probe, pid_cleanup_probe,
    verify_compute_output,
)
from lesson_common import (
    Pending, case, job_id, json_lines, receipt, require, state, submit, text, view,
)
from slurm_cli import compose_argv, run_command


def _gpu_options(run):
    require(run['parameters'].get('node') == 'gpu01', '本課僅支援 gpu01')
    return (*GPU_OPTIONS, '--nodelist=' + run['parameters']['node'])


def _diagnostic(argv):
    """Only fixed read-only root probes; no scheduler wait or mutation."""
    try:
        result = run_command(argv, cwd=lab.ROOT, timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('gpu01 唯讀程序診斷逾時（5 秒）') from exc
    require(result.returncode == 0,
            f'gpu01 唯讀診斷失敗：{result.stderr}\n{result.stdout}')
    evidence = json.loads(result.stdout)
    require(isinstance(evidence, dict), 'GPU 診斷未回傳 JSON 物件')
    return evidence


def _compute(data, step, container):
    rows = state(data, step, 'COMPLETED')
    return {'jobs': rows,
            'events': verify_compute_output(text(data, step), job_id(data, step), container)}


def _denied(data, step):
    rows = state(data, step, 'COMPLETED')
    evidence = [item for item in json_lines(text(data, step)) if 'device_denied' in item]
    require(len(evidence) == 1, f'{step}: 缺少唯一的裝置拒絕證據')
    item = evidence[0]
    require(item.get('device_denied') is True and item.get('uid') == 1000
            and item.get('errno') in (errno.EPERM, errno.EACCES),
            f'{step}: 必須是 UID 1000 的 EPERM/EACCES，ENOENT 不算隔離證據')
    return {'jobs': rows, 'device': item}


def _cpu_absent(data, node):
    step = 'absent-' + node
    rows = state(data, step, 'COMPLETED')
    evidence = [item for item in json_lines(text(data, step)) if 'gpu_device_absent' in item]
    require(len(evidence) == 1 and evidence[0].get('gpu_device_absent') is True
            and evidence[0].get('hostname') == node, f'{node}: 未證明該節點沒有 GPU 裝置')
    return {'jobs': rows, 'device': evidence[0]}


def _isolation(data):
    return {'direct': _denied(data, 'deny-direct'),
            'container': _denied(data, 'deny-container'),
            'cpu01': _cpu_absent(data, 'cpu01'),
            'cpu02': _cpu_absent(data, 'cpu02')}


def _before_holder(run, snapshot):
    try:
        return {'isolation': _isolation(view(run))}
    except (Pending, AssertionError, ValueError, KeyError) as exc:
        return '先完成兩種無 GRES 拒絕及兩個 CPU 節點檢查：' + str(exc)


def _fresh_rows(snapshot, identifier, expected):
    source = snapshot.get('sources', {}).get('jobs', {})
    require(source.get('status') == 'ok', '目前無法取得新鮮 scheduler 紀錄')
    rows = [row for row in source['data'] if row['job_id'] == identifier]
    require(len(rows) == 1 and expected in rows[0]['job_state'],
            f'{identifier}: 必須仍為 {expected}；已過期的 holder 不可續做')
    return rows


def _held(run, snapshot):
    data = view(run)
    identifier = job_id(data, 'holder')
    state(data, 'holder', 'RUNNING')  # Also checks saved ownership identity.
    rows = _fresh_rows(snapshot, identifier, 'RUNNING')
    output = text(data, 'holder')
    require('GPU_HELD' in output.splitlines(), '等待 GPU_HELD：CUDA 計算尚未完成')
    record = verify_compute_output(output, identifier, True)
    start = rows[0]['start_time']
    require(start is not None, '缺少 holder StartTime，不能推算安全操作窗口')
    remaining = 120 - (time.time() - start)
    require(remaining > 10, 'holder 的保守 120 秒窗口已不足 10 秒；清理後建立新 run')
    observed = _diagnostic(outer_cgroup_probe(record['gpu_environment']['pid']))
    sluid = record['gpu_environment']['environment'].get('SLURM_JOB_SLUID')
    require(bool(sluid) and sluid in observed['cgroup'], '外層 cgroup 缺少本 job SLUID')
    require(observed['state'] not in ('Z', 'X'), 'holder PID 已不存活')
    require(any(item['memory.max'] == str(512 * 1024 * 1024)
                for item in observed['memory_limits']), '外層 cgroup 未套用 512 MiB RAM 上限')
    return {'holder': record, 'holder_jobs': rows, 'outer': observed,
            'remaining_seconds_conservative': round(remaining, 1)}


def _before_waiter(run, snapshot):
    try:
        return _held(run, snapshot)
    except (Pending, AssertionError, ValueError, KeyError, OSError) as exc:
        return str(exc)


def _before_cancel(run, snapshot):
    try:
        evidence = _held(run, snapshot)
        data = view(run)
        state(data, 'waiter', 'PENDING')
        rows = _fresh_rows(snapshot, job_id(data, 'waiter'), 'PENDING')
        require(rows[0]['state_reason'] in ('Resources', 'Priority'),
                'waiter 必須因 Resources/Priority 等待，不能以其他失敗原因當 GPU 排隊')
        queued = receipt(data, 'waiter')
        previous = queued['evidence']['outer']
        require(previous['pid'] == evidence['outer']['pid']
                and previous['starttime'] == evidence['outer']['starttime'],
                'holder 的 PID/starttime 在排隊期間改變')
        evidence['pending_waiter'] = rows
        return evidence
    except (Pending, AssertionError, ValueError, KeyError, OSError) as exc:
        return str(exc)


def _queue_result(data):
    cancelled = receipt(data, 'cancel-holder')
    if not cancelled:
        raise Pending('尚未在 holder 存活且 waiter PENDING 時執行取消')
    require(cancelled['status'] == 'succeeded', '取消步驟失敗或結果未確認')
    evidence = cancelled.get('evidence') or {}
    require(bool(evidence.get('pending_waiter')), '缺少取消前的 PENDING 證據')
    require(all('PENDING' in row['job_state']
                and row['state_reason'] in ('Resources', 'Priority')
                for row in evidence['pending_waiter']), '保存的 waiter 狀態不是資源排隊')
    state(data, 'holder', 'CANCELLED')
    released = _compute(data, 'waiter', True)
    outer = evidence['outer']
    cleanup = _diagnostic(pid_cleanup_probe(outer['pid'], outer['starttime']))
    require(cleanup.get('live') is False, '取消後原容器 PID 仍存活')
    return {'before_cancel': evidence, 'pid_cleanup': cleanup, 'released': released,
            'cancelled_job': job_id(data, 'holder'), 'queued_job': job_id(data, 'waiter')}


def _verify_compute(data):
    return [case('gpu_direct_cuda_numerical', lambda: _compute(data, 'direct', False)),
            case('gpu_independent_oci_cuda_numerical', lambda: _compute(data, 'container', True))]


def _verify_isolation(data):
    return [case('gpu_no_gres_direct_denied', lambda: _denied(data, 'deny-direct')),
            case('gpu_no_gres_container_denied', lambda: _denied(data, 'deny-container')),
            case('cpu_nodes_no_gpu_device', lambda: {
                node: _cpu_absent(data, node) for node in ('cpu01', 'cpu02')}),
            case('gpu_container_queue_cancel_release', lambda: _queue_result(data))]


def get_lesson(chapter):
    if chapter == '06-container-gpu':
        steps = {
            'direct': lab.Step('submit', lambda run: submit(
                run, 'direct', command=direct_command(), options=_gpu_options(run))),
            'container': lab.Step('submit', lambda run: submit(
                run, 'container', script='container-gpu.sbatch',
                options=('--nodelist=' + run['parameters']['node'],))),
        }
        labels = {'direct': '1. 提交直接 CUDA 計算',
                  'container': '2. 提交公開 container-gpu.sbatch'}
        title = '06｜獨立容器與真實 CUDA 計算'
        verify = _verify_compute
        cases = ['gpu_direct_cuda_numerical', 'gpu_independent_oci_cuda_numerical']
    elif chapter == '06-gpu-isolation':
        steps = {
            'deny-direct': lab.Step('submit', lambda run: submit(
                run, 'deny-direct', command=denied_command(False),
                options=('--partition=gpu', '--nodelist=' + run['parameters']['node'], '--mem=256M'))),
            'deny-container': lab.Step('submit', lambda run: submit(
                run, 'deny-container', command=denied_command(True),
                options=('--partition=gpu', '--nodelist=' + run['parameters']['node'], '--mem=256M'))),
            'absent-cpu01': lab.Step('submit', lambda run: submit(
                run, 'absent-cpu01', command=cpu_absent_command(), options=('--nodelist=cpu01',))),
            'absent-cpu02': lab.Step('submit', lambda run: submit(
                run, 'absent-cpu02', command=cpu_absent_command(), options=('--nodelist=cpu02',))),
            'holder': lab.Step('submit', lambda run: submit(
                run, 'holder', command=holder_command(),
                options=(*_gpu_options(run), '--time=00:04:00')), _before_holder),
            'waiter': lab.Step('submit', lambda run: submit(
                run, 'waiter', command=container_command(), options=_gpu_options(run)), _before_waiter),
            'cancel-holder': lab.Step('cancel', lambda run: compose_argv(
                'scancel', job_id(run, 'holder')), _before_cancel),
        }
        labels = {'deny-direct': '1. 直接執行：不申請 GRES，驗證拒絕',
                  'deny-container': '2. 容器執行：不申請 GRES，驗證拒絕',
                  'absent-cpu01': '3. 證明 cpu01 沒有 GPU 裝置',
                  'absent-cpu02': '4. 證明 cpu02 沒有 GPU 裝置',
                  'holder': '5. 提交 GPU 容器 holder（120 秒）',
                  'waiter': '6. GPU_HELD 後提交第二個 GPU job',
                  'cancel-holder': '7. waiter PENDING 後取消本次 holder'}
        title = '06｜GPU 裝置隔離、排隊與取消'
        verify = _verify_isolation
        cases = ['gpu_no_gres_direct_denied', 'gpu_no_gres_container_denied',
                 'cpu_nodes_no_gpu_device', 'gpu_container_queue_cancel_release']
    else:
        raise ValueError('Unknown GPU lesson: ' + chapter)
    lab.register_chapter(chapter, steps, verify=verify)
    lesson = {'chapter': chapter, 'title': title, 'fields': {'node': ['gpu01']},
              'steps': steps, 'labels': labels, 'verify': verify, 'cases': cases,
              'sources': ['gpu_compute.py', 'container-gpu.sbatch']}
    if chapter == '06-gpu-isolation':
        lesson.update(holder_seconds={'holder': 120}, markers={'holder': 'GPU_HELD'})
    return lesson
