"""Fixed CPU, queue, CSV and MPI lesson steps; imports have no effects."""
import csv
import json
from pathlib import Path

import notebook_lab as lab
from lesson_common import (Pending, case, exit_failed, exit_ok, job_id, json_lines, probe, receipt,
                           records, require, state, submit, text, view)
from slurm_cli import compose_argv
from smoke import CPUSETS


def _done(data, step):
    result = receipt(data, step)
    if not result:
        raise Pending(f'先執行 {step}')
    require(result['status'] == 'succeeded', f'{step} 未成功或結果不確定')
    return result


def _after(*steps):
    def check(run, snapshot):
        data = view(run)
        for step in steps:
            _done(data, step)
    return check


def _identity(data, step, node, cpus, *, released=False):
    state(data, step, 'COMPLETED')
    values = json_lines(text(data, step))
    values = [value for value in values if value.get('released')] if released else values
    require(len(values) == 1, f'{step}: 預期一筆運算結果：{values}')
    value = values[0]
    require(value.get('uid') == 1000 and value.get('hostname') == node and
            str(value.get('job_id')) == job_id(data, step), f'{step}: 工作身分不符：{value}')
    affinity = value.get('affinity', [])
    require(len(set(affinity)) == cpus and set(affinity) <= CPUSETS[node],
            f'{step}: CPU binding 不符：{value}')
    require(value.get('sum') == 50005000, f'{step}: 總和錯誤：{value}')
    return value


def _holder(data):
    rows = state(data, 'holder', 'RUNNING')
    started = [x for x in json_lines(text(data, 'holder')) if x.get('started')]
    require(len(started) == 1 and started[0].get('hostname') == 'cpu01' and
            started[0].get('uid') == 1000 and str(started[0].get('job_id')) == job_id(data, 'holder'),
            'holder 尚未印出正確 started marker；過期不可接續')
    return rows


def _pending(data, step, reasons):
    rows = state(data, step, 'PENDING')
    require(all(row.get('state_reason') in reasons for row in rows),
            f'{step}: 不是預期等待原因：{rows}')
    return rows


def _queue_ready(run, snapshot):
    data = view(run)
    return {'holder': _holder(data)}


def _release_ready(run, snapshot):
    data = view(run)
    return {'holder': _holder(data),
            'pending': _pending(data, 'waiter', {'Resources', 'Priority'})}


def _queue_verify(data):
    if receipt(data, 'cancel-holder'):
        cancel = _done(data, 'cancel-holder')
        evidence = cancel.get('evidence') or {}
        require(evidence.get('holder') and evidence.get('pending'), '缺少取消 A 前的 RUNNING/PENDING 證據')
        state(data, 'holder', 'CANCELLED')
        return {'before_cancel': evidence, 'holder': records(data, 'holder'),
                'waiter': _identity(data, 'waiter', 'cpu01', 1)}
    release = _done(data, 'release')
    evidence = release.get('evidence') or {}
    require(evidence.get('holder') and evidence.get('pending'), '缺少 release 前 RUNNING/PENDING 證據')
    return {'before_release': evidence,
            'holder': _identity(data, 'holder', 'cpu01', 4, released=True),
            'waiter': _identity(data, 'waiter', 'cpu01', 1)}


def _interactive(run):
    p = run['parameters']
    return compose_argv('srun', '--immediate=5', '--partition=cpu', '--nodes=1', '--ntasks=1',
                        f'--nodelist={p["node"]}', f'--cpus-per-task={p["cpus"]}', '--mem=128M',
                        '--time=00:01:00', '--cpu-bind=threads',
                        f'--job-name={lab.job_name(run["run_id"], "interactive")}',
                        f'--chdir={run["container_dir"]}',
                        'python3', '/opt/lab/examples/cpu_probe.py', 'affinity')


def _mpi_verify(data):
    rows = state(data, 'mpi', 'COMPLETED')
    values = json_lines(text(data, 'mpi'))
    require(len(values) == 2 and {v.get('rank') for v in values} == {0, 1}, '必須有 rank 0/1 各一筆')
    require({v.get('hostname') for v in values} == {'cpu01', 'cpu02'}, 'MPI ranks 必須在不同 CPU 節點')
    require(all(v.get('size') == 2 and v.get('sum') == 3 and v.get('valid') is True for v in values),
            f'MPI Allreduce 證據錯誤：{values}')
    require(all(row.get('user_id') == 1000 for row in rows), 'MPI 工作 UID 必須為 1000')
    return {'jobs': rows, 'ranks': values}


def _path(data, relative):
    root = Path(data['run_dir'])
    path = root / relative
    require(not root.is_symlink() and all(not part.is_symlink() for part in [path, *path.parents]),
            '拒絕 symlink 證據路徑')
    require(path.resolve().is_relative_to(root.resolve()), '證據路徑越界')
    return path


def _json(data, relative):
    path = _path(data, relative)
    if not path.is_file():
        raise Pending(f'尚缺 {relative}')
    return json.loads(path.read_text())


def _mode(run, mode):
    require(run['parameters']['mode'] == mode, f'此步只適用 {mode}；請另建實驗')


def _csv_prepare_ready(run, snapshot):
    require(run['parameters'].get('mode') in {'success', 'failure-recovery'}, '未知 CSV 模式')


def _csv_backup_ready(run, snapshot):
    _mode(run, 'failure-recovery')
    _after('prepare')(run, snapshot)


def _csv_array_ready(run, snapshot):
    _after('prepare', *(['inject'] if run['parameters']['mode'] == 'failure-recovery' else []))(run, snapshot)


def _csv_partial(data, index):
    value = _json(data, f'pipeline/partials/{index}.json')
    first, last = index * 1000 + 1, (index + 1) * 1000
    require(value == {'index': index, 'row_count': 1000, 'value_sum': (first + last) * 1000},
            f'shard {index} 數值錯誤：{value}')
    return value


def _csv_failed(data):
    rows = records(data, 'array')
    by_index = {int(row['array_task_id']): row for row in rows if row.get('array_task_id') is not None}
    if set(by_index) != {0, 1, 2, 3}:
        raise Pending('等待四個 array task 的實際 scheduler 紀錄')
    for index, row in by_index.items():
        expected = 'FAILED' if index == 2 else 'COMPLETED'
        if not set(row['job_state']) & lab.TERMINAL:
            raise Pending('等待 array tasks 結束')
        require(expected in row['job_state'], f'shard {index} 預期 {expected}：{row}')
        exit_code = row['exit_code']
        require(exit_failed(exit_code) if index == 2 else exit_ok(exit_code),
                f'shard {index} exit code 不符')
    require(not _path(data, 'pipeline/partials/2.json').exists(), '壞輸入不得產生 shard 2 partial')
    require(not _path(data, 'pipeline/summary.json').exists(), '失敗後不可有 summary')
    return {'tasks': rows, 'partials': [_csv_partial(data, i) for i in (0, 1, 3)]}


def _csv_missing_ready(run, snapshot):
    _mode(run, 'failure-recovery')
    data = view(run)
    with _path(data, 'pipeline/input/shard-2.csv').open(newline='') as stream:
        inputs = list(csv.DictReader(stream))
    require(len(inputs) == 1000 and inputs[0].get('value') == 'bad-value',
            '缺少本次刻意注入的非數字輸入證據')
    return {'failure': _csv_failed(data),
            'dependent': _pending(data, 'aggregate', {'Dependency', 'DependencyNeverSatisfied'})}


def _csv_cancel_ready(run, snapshot):
    evidence = _csv_missing_ready(run, snapshot)
    data = view(run)
    rows = state(data, 'missing-aggregate', 'FAILED')
    require(all(exit_failed(r['exit_code']) for r in rows),
            '缺片 aggregate 必須非零退出')
    evidence['missing_aggregate'] = rows
    evidence['missing_output'] = text(data, 'missing-aggregate')
    return evidence


def _csv_repair_ready(run, snapshot):
    _mode(run, 'failure-recovery')
    data = view(run)
    _done(data, 'cancel-dependent')
    state(data, 'aggregate', 'CANCELLED')
    # Preserve proof that the three good shards were not rewritten during repair.
    return {'partials': [_csv_partial(data, i) for i in (0, 1, 3)],
            'contents': {str(i): _path(data, f'pipeline/partials/{i}.json').read_text() for i in (0, 1, 3)}}


def _csv_submit(run, step, *, worker=False, repaired=False, missing=False):
    options = []
    if worker:
        options = ['--array=2' if repaired else '--array=0-3%2']
    elif not missing:
        options = [f'--dependency=afterok:{job_id(run, "repair-shard" if repaired else "array")}',
                   '--kill-on-invalid-dep=no']
    return submit(run, step, script='pipeline-worker.sbatch' if worker else 'pipeline-aggregate.sbatch',
                  args=(run['container_dir'] + '/pipeline',), options=options, array=worker)


def _csv_verify(data):
    failure = data['parameters']['mode'] == 'failure-recovery'
    final_step = 'aggregate-repaired' if failure else 'aggregate'
    state(data, final_step, 'COMPLETED')
    evidence = {}
    if failure:
        for step in ('backup', 'inject', 'missing-aggregate', 'cancel-dependent', 'repair-input', 'repair-shard'):
            _done(data, step)
        cancel = receipt(data, 'cancel-dependent')
        require(cancel.get('evidence', {}).get('failure') and cancel['evidence'].get('missing_aggregate'),
                '缺少失敗、dependency 阻擋與缺片拒絕的保存證據')
        state(data, 'aggregate', 'CANCELLED')
        state(data, 'missing-aggregate', 'FAILED')
        repaired = state(data, 'repair-shard', 'COMPLETED')
        require({r.get('array_task_id') for r in repaired} == {2}, '只能重送 shard 2')
        saved = _done(data, 'repair-input').get('evidence', {}).get('contents', {})
        require(set(saved) == {'0', '1', '3'}, '缺少修復前成功 partial 證據')
        require(all(_path(data, f'pipeline/partials/{i}.json').read_text() == contents for i, contents in saved.items()),
                '修復不應重寫其他三片')
        evidence['failure_and_recovery'] = cancel['evidence']
    else:
        rows = state(data, 'array', 'COMPLETED')
        require({row.get('array_task_id') for row in rows} == {0, 1, 2, 3}, '缺少四個完成的 array task')
    summary = _json(data, 'pipeline/summary.json')
    require(summary == {'shards': 4, 'row_count': 4000, 'value_sum': 16004000}, f'彙總結果錯誤：{summary}')
    return {**evidence, 'partials': [_csv_partial(data, i) for i in range(4)], 'summary': summary}


def get_lesson(chapter):
    if chapter == '02-submit':
        steps = {
            'interactive': lab.Step('interactive', _interactive),
            'batch': lab.Step('submit', lambda r: submit(r, 'batch', script='cpu.sbatch', options=(
                f'--nodelist={r["parameters"]["node"]}', f'--cpus-per-task={r["parameters"]["cpus"]}'))),
        }
        lesson = dict(title='02 提交與觀察', fields={'node': ['cpu01', 'cpu02'], 'cpus': [1, 4]},
                      labels={'interactive': '執行短 srun（最長 15 秒）', 'batch': '提交公開 cpu.sbatch'},
                      sources=['cpu.sbatch', 'cpu_probe.py'], cases=['cpu-affinity'],
                      verify=lambda d: [case(step, lambda step=step: _identity(d, step, d['parameters']['node'],
                                                                           int(d['parameters']['cpus']))) for step in steps])
    elif chapter == '03-queue':
        steps = {
            'holder': lab.Step('submit', lambda r: submit(r, 'holder', command=probe('hold', '--release',
                r['container_dir'] + '/queue.release', '--seconds', '600'),
                options=('--nodelist=cpu01', '--cpus-per-task=4', '--time=00:11:00'))),
            'waiter': lab.Step('submit', lambda r: submit(r, 'waiter', command=probe('affinity') + '; sleep 60',
                options=('--nodelist=cpu01',)), _queue_ready),
            'cancel-holder': lab.Step('cancel', lambda r: compose_argv('scancel', job_id(r, 'holder')), _release_ready),
        }
        lesson = dict(title='03 多個工作與資源排隊', fields={'實驗': ['A 佔用 cpu01 → B 排隊 → 取消 A']},
                      labels={'holder': '啟動工作 A', 'waiter': '提交工作 B', 'cancel-holder': '取消工作 A，釋出資源'},
                      sources=['cpu.sbatch', 'cpu_probe.py'], cases=['resource-queue-release'],
                      verify=lambda d: [case('resource-queue-release', lambda: _queue_verify(d))])
    elif chapter == '04-csv':
        steps = {
            'prepare': lab.Step('local', lambda r: lab.local_argv(r['run_id'], 'pipeline-prepare', 'pipeline'), _csv_prepare_ready),
            'backup': lab.Step('local', lambda r: lab.local_argv(r['run_id'], 'copy', 'pipeline/input/shard-2.csv', 'pipeline/shard-2.backup.csv'), _csv_backup_ready),
            'inject': lab.Step('local', lambda r: lab.local_argv(r['run_id'], 'csv-set', 'pipeline/input/shard-2.csv', '0', 'value', 'bad-value'), _after('backup')),
            'array': lab.Step('submit', lambda r: _csv_submit(r, 'array', worker=True), _csv_array_ready),
            'aggregate': lab.Step('submit', lambda r: _csv_submit(r, 'aggregate'), _after('array')),
            'missing-aggregate': lab.Step('submit', lambda r: _csv_submit(r, 'missing-aggregate', missing=True), _csv_missing_ready),
            'cancel-dependent': lab.Step('cancel', lambda r: compose_argv('scancel', job_id(r, 'aggregate')), _csv_cancel_ready),
            'repair-input': lab.Step('local', lambda r: lab.local_argv(r['run_id'], 'copy', 'pipeline/shard-2.backup.csv', 'pipeline/input/shard-2.csv'), _csv_repair_ready),
            'repair-shard': lab.Step('submit', lambda r: _csv_submit(r, 'repair-shard', worker=True, repaired=True), _after('repair-input')),
            'aggregate-repaired': lab.Step('submit', lambda r: _csv_submit(r, 'aggregate-repaired', repaired=True), _after('repair-shard')),
        }
        lesson = dict(title='04 CSV 資料管線', fields={'mode': ['success', 'failure-recovery']},
                      labels={'prepare': '準備四片 CSV', 'backup': '壞輸入：備份 shard 2', 'inject': '壞輸入：注入非數字',
                              'array': '提交 worker array 0–3', 'aggregate': '提交 afterok aggregate',
                              'missing-aggregate': '明確測試缺片 aggregate（無 dependency）', 'cancel-dependent': '保存失敗證據並取消原 dependent',
                              'repair-input': '還原 shard 2 輸入', 'repair-shard': '只重送 shard 2', 'aggregate-repaired': '提交修復後 afterok aggregate'},
                      sources=['pipeline.py', 'pipeline-worker.sbatch', 'pipeline-aggregate.sbatch'],
                      cases=['csv-pipeline-success', 'csv-pipeline-failure-recovery'],
                      verify=lambda d: [case('csv-pipeline-' + d['parameters']['mode'], lambda: _csv_verify(d))])
    elif chapter == '05-mpi':
        steps = {'mpi': lab.Step('submit', lambda r: submit(r, 'mpi', script='mpi.sbatch',
                                                           options=('--nodelist=cpu01,cpu02',)))}
        lesson = dict(title='05 跨節點 MPI', fields={}, labels={'mpi': '提交公開 mpi.sbatch（雙 rank）'},
                      sources=['mpi.sbatch', 'mpi_sum.c'], cases=['cross-node-mpi'],
                      verify=lambda d: [case('cross-node-mpi', lambda: _mpi_verify(d))])
    else:
        raise ValueError(f'Unknown CPU lesson: {chapter}')
    lesson.update(chapter=chapter, steps=steps)
    registered_steps = dict(steps)
    if chapter == '03-queue':
        # Retain the old release action for existing saved runs, outside the new UI.
        registered_steps['release'] = lab.Step('local', lambda r: lab.local_argv(
            r['run_id'], 'release', 'queue.release'), _release_ready)
    if chapter == '02-submit':
        from submit_observer import observer_steps
        from submit_serial import serial_steps
        registered_steps.update(observer_steps())
        registered_steps.update(serial_steps())
    lab.register_chapter(chapter, registered_steps, verify=lesson['verify'])
    return lesson
