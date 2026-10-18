"""Small shared workload/evidence vocabulary; no implicit mutations."""
import json
import shlex
from notebook_lab import read_run, job_name, TERMINAL
from slurm_cli import compose_argv

PROBE = '/opt/lab/examples/cpu_probe.py'


class Pending(Exception):
    """Required observation has not happened yet, rather than a failed proof."""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def submit(run, step_id, *, script=None, args=(), command=None, options=(), array=False):
    if (script is None) == (command is None):
        raise ValueError('Choose a public script or fixed wrap workload')
    suffix = '%A_%a' if array else '%j'
    base = ['sbatch', '--parsable', f'--job-name={job_name(run["run_id"], step_id)}',
            f'--chdir={run["container_dir"]}',
            f'--output={run["container_dir"]}/{step_id}-{suffix}.out',
            f'--error={run["container_dir"]}/{step_id}-{suffix}.err']
    if command is not None:
        aliases = {'-p': '--partition', '-N': '--nodes', '-n': '--ntasks', '-c': '--cpus-per-task', '-t': '--time'}
        supplied = {aliases.get(option.split('=', 1)[0], option.split('=', 1)[0])
                    for option in options if option.startswith('-')}
        defaults = ['--partition=cpu', '--nodes=1', '--ntasks=1', '--cpus-per-task=1', '--mem=128M', '--time=00:02:00']
        base += [option for option in defaults if option.split('=', 1)[0] not in supplied]
    base += list(options)
    if script is not None:
        base += [script if script.startswith('/') else '/opt/lab/examples/' + script, *args]
    else:
        base += ['--wrap', 'set -eu; ' + command]
    return compose_argv(*base)


def probe(mode, *args):
    return shlex.join(['srun', '--cpu-bind=threads', 'python3', PROBE, mode, *map(str, args)])


def view(run):
    return read_run(run['run_id'])


def receipt(data, step_id):
    if 'receipts' not in data:
        data = view(data)
    return next((r for r in data['receipts'] if r['step_id'] == step_id), None)


def job_id(run, step_id):
    r = receipt(run, step_id)
    if not r or r['status'] != 'succeeded' or not r.get('job_id'):
        raise ValueError(f'{step_id}: 尚無已確認的提交 ID')
    return r['job_id']


def records(data, step_id):
    if 'receipts' not in data:
        data = view(data)
    r = receipt(data, step_id)
    if not r or not r.get('job_id'):
        return []
    observation = data['jobs'].get(r['job_id'], {})
    if observation.get('status') == 'identity-mismatch':
        raise AssertionError(observation['error'])
    return observation.get('records', [])


def text(data, step_id):
    if 'receipts' not in data:
        data = view(data)
    r = receipt(data, step_id)
    if not r:
        return ''
    identifier = r.get('job_id')
    parts = [r.get('stdout', ''), r.get('stderr', '')] if r['effect'] == 'interactive' else []
    for key, logs in data['outputs'].items():
        if identifier and (key == identifier or key.startswith(identifier + '_')):
            parts.extend(log['text'] for log in logs if log['status'] == 'ok' and log['text'] is not None)
    return '\n'.join(parts)


def json_lines(output):
    values = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def exit_ok(code):
    return (code['return_code'] == 0 and code['signal']['id'] in (None, 0)
            and 'SUCCESS' in code['status'])


def exit_failed(code):
    return any(type(value) is int and value != 0
               for value in (code['return_code'], code['signal']['id']))


def state(data, step_id, expected):
    rows = records(data, step_id)
    if not rows:
        raise Pending(f'{step_id}: 尚無可核對的 scheduler 紀錄；缺失不是成功')
    allowed = {expected} if isinstance(expected, str) else set(expected)
    for row in rows:
        actual = set(row['job_state'])
        if not actual & allowed:
            if actual & TERMINAL:
                raise AssertionError(f'{step_id}: 預期 {allowed}，實際 {actual}')
            raise Pending(f'{step_id}: 等待 {allowed}，目前 {actual}')
        if 'COMPLETED' in actual:
            require(exit_ok(row['exit_code']),
                    f'{step_id}: completed 但 exit code 非零：{row["exit_code"]}')
    return rows


def case(name, callback):
    try:
        return {'name': name, 'status': 'passed', 'evidence': callback()}
    except Pending as exc:
        return {'name': name, 'status': 'running', 'reason': str(exc), 'evidence': {'observation': str(exc)}}
    except (AssertionError, ValueError, KeyError, OSError) as exc:
        return {'name': name, 'status': 'failed', 'error': str(exc), 'evidence': {'error': str(exc)}}
