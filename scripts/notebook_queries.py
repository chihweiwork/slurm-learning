"""Read-only, standard-library observations for the local Slurm learning lab.

Fresh query_* results never use cached records: mutation gates must require
status == 'ok'. Only read_snapshot retains the last successful observation,
marked stale after a failure. These sequential observations are not an atomic
scheduler snapshot. Importing this module neither queries nor creates files.
"""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import threading

from slurm_cli import compose_argv, run_command

ROOT = Path(__file__).resolve().parents[1]
QUERY_TIMEOUT = 5
LOG_PREVIEW_BYTES = 64 * 1024
_SNAPSHOT_LOCK = threading.Lock()
_LAST_SUCCESS = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value, *, timestamp=False):
    if isinstance(value, dict):
        if (type(value.get('set')) is not bool
                or type(value.get('infinite')) is not bool or 'number' not in value):
            raise ValueError(f'Invalid Slurm numeric wrapper: {value!r}')
        if not value['set'] or value['infinite']:
            return None
        value = value['number']
    if type(value) is not int or value < 0:
        raise ValueError(f'Expected a nonnegative Slurm integer: {value!r}')
    return None if timestamp and value == 0 else value


def _string(value):
    if not isinstance(value, str):
        raise ValueError(f'Expected a string: {value!r}')
    return value


def _states(value):
    if not isinstance(value, list) or not value or any(not isinstance(s, str) for s in value):
        raise ValueError(f'Expected a nonempty Slurm state list: {value!r}')
    return list(value)


def _job(record):
    if not isinstance(record, dict):
        raise ValueError(f'Expected a job object: {record!r}')
    job_id = _number(record['job_id'])
    if not job_id:
        raise ValueError(f'Invalid job ID: {job_id!r}')
    parent = _number(record['array_job_id'])
    result = {'job_id': str(job_id), 'array_job_id': str(parent) if parent else None,
              'array_task_id': _number(record['array_task_id']),
              'user_id': _number(record['user_id']), 'cpus': _number(record['cpus']),
              'job_state': _states(record['job_state']), 'raw': record}
    for key in ('name', 'state_reason', 'partition', 'nodes', 'array_task_string',
                'dependency', 'standard_output', 'standard_error', 'current_working_directory'):
        result[key] = _string(record[key])
    for key in ('submit_time', 'start_time', 'end_time'):
        result[key] = _number(record[key], timestamp=True)
    exit_code = record['exit_code']
    exit_status = exit_code['status']
    if not isinstance(exit_status, list) or any(not isinstance(s, str) for s in exit_status):
        raise ValueError(f'Invalid exit status: {exit_status!r}')
    result['exit_code'] = {
        'status': list(exit_status),
        'return_code': _number(exit_code['return_code']),
        'signal': {'id': _number(exit_code['signal']['id']),
                   'name': _string(exit_code['signal']['name'])},
    }
    return result


def _node(record):
    if not isinstance(record, dict):
        raise ValueError(f'Expected a node object: {record!r}')
    result = {'state': _states(record['state']), 'raw': record}
    for key in ('name', 'gres', 'gres_used', 'reason'):
        result[key] = _string(record[key])
    for key in ('effective_cpus', 'alloc_cpus', 'real_memory', 'alloc_memory'):
        result[key] = _number(record[key])
    partitions = record['partitions']
    if not isinstance(partitions, list) or any(not isinstance(p, str) for p in partitions):
        raise ValueError(f'Invalid node partitions: {partitions!r}')
    result['partitions'] = list(partitions)
    return result


def _ping(record):
    if not isinstance(record, dict) or type(record.get('responding')) is not bool:
        raise ValueError(f'Invalid controller ping: {record!r}')
    if type(record.get('primary')) is not bool:
        raise ValueError(f'Invalid controller ping: {record!r}')
    return {'hostname': _string(record['hostname']), 'responding': record['responding'],
            'primary': record['primary'], 'status': _string(record['status']), 'raw': record}


def _envelope(argv):
    return {'status': 'error', 'data': None, 'observed_at': _now(), 'last_success_at': None,
            'stale': False, 'errors': [], 'warnings': [], 'argv': argv,
            'returncode': None, 'stdout': '', 'stderr': '', 'raw': None}


def _text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')


def _query(argv, parser, *, json_key=None):
    result = _envelope(argv)
    try:
        process = run_command(argv, cwd=ROOT, timeout=QUERY_TIMEOUT)
        result.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
        if json_key is not None:
            payload = json.loads(process.stdout)
            result['raw'] = payload
            if not isinstance(payload, dict):
                raise ValueError('Slurm JSON root is not an object')
            for key in ('errors', 'warnings'):
                if not isinstance(payload.get(key), list):
                    raise ValueError(f'Slurm JSON {key} is not a list')
                result[key] = list(payload[key])
            if result['errors']:
                return result
            if process.returncode:
                raise ValueError(f'Command exited {process.returncode}: {process.stderr.strip()}')
            records = payload.get(json_key)
            if not isinstance(records, list):
                raise ValueError(f'Slurm JSON {json_key} is not a list')
            result['data'] = [parser(record) for record in records]
        else:
            if process.returncode:
                raise ValueError(f'Command exited {process.returncode}: {process.stderr.strip()}')
            result['data'] = parser(process.stdout)
        result.update(status='ok', last_success_at=_now())
    except subprocess.TimeoutExpired as exc:
        result.update(stdout=_text(exc.stdout), stderr=_text(exc.stderr))
        result['errors'].append(f'Query timed out after {QUERY_TIMEOUT}s: {exc}')
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
        result['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        result['observed_at'] = _now()
    return result


def query_controller():
    """Fresh controller ping; a nonresponding primary is an error, not green."""
    result = _query(compose_argv('scontrol', '--json', 'ping'), _ping, json_key='pings')
    if result['status'] == 'ok' and not any(p['primary'] and p['responding'] for p in result['data']):
        result['status'] = 'error'
        result['last_success_at'] = None
        result['errors'].append('The primary controller is not responding')
    return result


def query_nodes():
    """Fresh node records, preserving state flags and scheduler resource counts."""
    return _query(compose_argv('scontrol', '--json', 'show', 'nodes'), _node, json_key='nodes')


def query_jobs():
    """Fresh retained jobs; absence is not evidence of successful completion."""
    return _query(compose_argv('scontrol', '--json', 'show', 'jobs'), _job, json_key='jobs')


def _queue(stdout):
    rows = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split('|', 4)
        if len(fields) != 5:
            raise ValueError(f'Invalid squeue row: {line!r}')
        job_id, state, partition, cpus, reason = (field.strip() for field in fields)
        match = re.fullmatch(r'([0-9]+)(?:_([0-9]+|\[[0-9,%-]+\]))?', job_id)
        if not match or not state or not cpus.isdecimal():
            raise ValueError(f'Invalid squeue fields: {line!r}')
        rows.append({'job_id': job_id, 'state': state, 'partition': partition, 'cpus': int(cpus),
                     'reason': reason, 'parent_job_id': match[1], 'task_id': match[2]})
    return rows


def query_queue():
    """Fresh full active queue, including held jobs and individual array tasks."""
    return _query(compose_argv('squeue', '--all', '--array', '--noheader',
                              '--format=%i|%T|%P|%C|%R'), _queue)


def _gpu_number(value):
    value = value.strip()
    if value in ('N/A', '[N/A]', '[Not Supported]', 'Not Supported'):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'Invalid GPU metric: {value!r}')
    return number


def _gpus(stdout):
    result = []
    for row in csv.reader(io.StringIO(stdout), skipinitialspace=True):
        if not row:
            continue
        if len(row) != 5 or not row[0].strip() or not row[1].strip():
            raise ValueError(f'Invalid nvidia-smi CSV row: {row!r}')
        result.append({'name': row[0].strip(), 'uuid': row[1].strip(),
                       'utilization_gpu_percent': _gpu_number(row[2]),
                       'memory_used_mib': _gpu_number(row[3]),
                       'memory_total_mib': _gpu_number(row[4])})
    if not result:
        raise ValueError('nvidia-smi returned no GPU records')
    return result


def query_gpu():
    """Whole-card observations include non-Slurm users; these are not quotas."""
    return _query(compose_argv('nvidia-smi',
                              '--query-gpu=name,uuid,utilization.gpu,memory.used,memory.total',
                              '--format=csv,noheader,nounits', service='gpu01'), _gpus)


def _cached(name, result):
    if result['status'] == 'ok':
        _LAST_SUCCESS[name] = deepcopy(result)
    elif name in _LAST_SUCCESS:
        previous = _LAST_SUCCESS[name]
        result.update(data=deepcopy(previous['data']), stale=True,
                      last_success_at=previous['last_success_at'])
    return result


def _skipped(reason):
    result = _envelope([])
    result['errors'].append(reason)
    result['skipped'] = True
    return result


def _link_queue(sources):
    # Preserve the visible task ID; retained parent records may represent tasks
    # that Slurm has not materialized. Never add parents to the active count.
    jobs = sources['jobs']['data']
    queue = sources['queue']['data']
    if jobs is None or queue is None:
        return
    by_id = {job['job_id']: job for job in jobs}
    by_task = {(job['array_job_id'], str(job['array_task_id'])): job for job in jobs
               if job['array_job_id'] is not None and job['array_task_id'] is not None}
    for row in queue:
        job = by_task.get((row['parent_job_id'], row['task_id']))
        if job is None:
            job = by_id.get(row['job_id']) or by_id.get(row['parent_job_id'])
        row['retained_job_id'] = job['job_id'] if job else None
        row['retained_is_parent'] = bool(job and row['task_id'] is not None
                                         and job['array_task_id'] is None)


def read_snapshot():
    """Sequential, bounded queries plus read-only local history.

    A concurrent refresh returns an explicit busy error, not overlapping Docker
    work. Source status/errors describe this attempt; stale data and its own
    last_success_at describe the previous success. None means never observed.
    """
    names = ('controller', 'nodes', 'jobs', 'queue', 'gpu')
    if not _SNAPSHOT_LOCK.acquire(blocking=False):
        return {'status': 'busy', 'observed_at': _now(),
                'sources': {name: _cached(name, _skipped('A snapshot refresh is already running'))
                            for name in names},
                'history': read_history(),
                'counts': {'running': None, 'pending': None, 'healthy_nodes': None}}
    try:
        sources = {'controller': _cached('controller', query_controller())}
        scheduler_available = sources['controller']['status'] == 'ok'
        for name, query in (('nodes', query_nodes), ('jobs', query_jobs), ('queue', query_queue)):
            result = query() if scheduler_available else _skipped(
                'A preceding scheduler query failed; dependent query skipped')
            sources[name] = _cached(name, result)
            scheduler_available = result['status'] == 'ok'
        # GPU observations do not depend on slurmctld. Avoid another CLI call
        # if a preceding command could not complete or Docker is unreachable.
        transport_error = any(
            source['returncode'] is None or any(
                token in source['stderr'].lower()
                for token in ('cannot connect to the docker daemon', 'is the docker daemon running',
                              'permission denied while trying to connect'))
            for source in sources.values() if not source.get('skipped'))
        sources['gpu'] = _cached('gpu', _skipped('Transport unavailable; GPU query skipped')
                                if transport_error else query_gpu())
        _link_queue(sources)
        queue, nodes = sources['queue'], sources['nodes']
        counts = {'running': None, 'pending': None, 'healthy_nodes': None}
        if queue['status'] == 'ok':
            counts.update(running=sum(row['state'] == 'RUNNING' for row in queue['data']),
                          pending=sum(row['state'] == 'PENDING' for row in queue['data']))
        if nodes['status'] == 'ok':
            unhealthy = {'DOWN', 'DRAIN', 'DRAINED', 'DRAINING', 'FAIL', 'FAILING',
                         'NO_RESPOND', 'NOT_RESPONDING', 'UNKNOWN', 'INVAL', 'INVALID_REG'}
            counts['healthy_nodes'] = sum(bool(set(node['state']) & {'IDLE', 'ALLOCATED', 'MIXED'})
                                          and not set(node['state']) & unhealthy for node in nodes['data'])
        return {'status': 'ok' if all(source['status'] == 'ok' for source in sources.values()) else 'error',
                'observed_at': _now(), 'sources': sources, 'history': read_history(), 'counts': counts}
    finally:
        _SNAPSHOT_LOCK.release()


def _relative_run(run_dir):
    run_dir = Path(run_dir)
    if '..' in run_dir.parts:
        raise ValueError('Parent traversal is not allowed')
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    try:
        parts = run_dir.relative_to(ROOT).parts
    except ValueError as exc:
        raise ValueError('Run directory is outside the project') from exc
    if (len(parts) != 3 or parts[0] != 'shared' or parts[1] not in ('demos', 'results')
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', parts[2]) or '..' in parts[2]):
        raise ValueError('Expected a known shared/demos or shared/results run directory')
    return run_dir, parts


def _file_parts(run_dir, path):
    run_dir, run_parts = _relative_run(run_dir)
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('Parent traversal is not allowed')
    if path.is_absolute():
        if path.parts[:2] == ('/', 'shared'):
            path = ROOT / path.relative_to('/')
        try:
            path = path.relative_to(run_dir)
        except ValueError as exc:
            raise ValueError('File is outside the selected run') from exc
    if not path.parts:
        raise ValueError('A file path is required')
    return (*run_parts, *path.parts)


def _open_file(run_dir, path):
    """Open relative to trusted ROOT, rejecting symlinks at every component.

    dir_fd traversal also prevents swapping an already-checked directory for a
    symlink between resolution and open. FIFOs/devices cannot block this reader.
    """
    parts = _file_parts(run_dir, path)
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('Only regular run files can be read')
            return os.fdopen(descriptor, 'rb')
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(directory)


def read_log(run_dir, path):
    """Read at most the last 64 KiB of a caller-authorized run file.

    The caller must select known receipt/report paths, not external job paths.
    Missing, inaccessible and successful empty files have distinct statuses.
    """
    result = {'status': 'error', 'path': str(path), 'text': None,
              'size_bytes': None, 'truncated': False, 'error': None}
    try:
        with _open_file(run_dir, path) as stream:
            size = os.fstat(stream.fileno()).st_size
            stream.seek(max(0, size - LOG_PREVIEW_BYTES))
            contents = stream.read(LOG_PREVIEW_BYTES)
        result.update(status='ok', text=contents.decode('utf-8', errors='replace'),
                      size_bytes=size, truncated=size > LOG_PREVIEW_BYTES)
    except FileNotFoundError as exc:
        result.update(status='missing', error=str(exc))
    except (OSError, ValueError) as exc:
        result['error'] = str(exc)
    return result


def download_log(run_dir, path):
    """Return a full caller-authorized run file as bytes, with the same boundary."""
    with _open_file(run_dir, path) as stream:
        return stream.read()


def _history_entry(run_dir, source):
    entry = {'source': source, 'kind': 'notebook' if source == 'demos' else 'smoke',
             'run_id': run_dir.name, 'path': str(run_dir / 'report.json'),
             'status': 'error', 'report': None, 'error': None}
    try:
        with _open_file(run_dir, 'report.json') as stream:
            report = json.load(stream)
        if not isinstance(report, dict):
            raise ValueError('Report must be a JSON object')
        if report.get('run_id') != run_dir.name:
            raise ValueError('Report run_id does not match its directory')
        if not isinstance(report.get('cases'), list) or not isinstance(report.get('status'), str):
            raise ValueError('Report requires cases list and status string')
        if any(not isinstance(case, dict) for case in report['cases']):
            raise ValueError('Report cases must be objects')
        if source == 'results':
            case_count = sum(case.get('name') != 'nodes-partitions' for case in report['cases'])
            if report.get('full_suite') is True:
                entry['kind'] = 'smoke-full-suite'
            elif 'scope' in report:
                entry['kind'] = 'smoke-single-case' if case_count <= 1 else 'smoke-selected-cases'
            else:
                entry['kind'] = 'smoke-legacy-report'
        # Refresh carries an index, not every historical command/log repeatedly.
        summary = {key: report.get(key) for key in
                   ('run_id', 'started', 'finished', 'status', 'scope', 'full_suite', 'created_job_ids', 'cleanup_errors')}
        summary['cases'] = [{key: case.get(key) for key in ('name', 'status')} for case in report['cases']]
        entry.update(status='ok', report=summary, report_scope='index')
    except FileNotFoundError as exc:
        entry.update(status='missing', error=str(exc))
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        entry['error'] = f'{type(exc).__name__}: {exc}'
    return entry


def read_history():
    """Return independent report entries; absent history is an empty list.

    Corruption and unsafe paths remain visible alongside usable reports.
    Full-suite classification requires explicit report metadata; legacy is unknown.
    """
    entries = []
    for source in ('demos', 'results'):
        base = ROOT / 'shared' / source
        try:
            if (ROOT / 'shared').is_symlink() or base.is_symlink():
                raise ValueError(f'Refusing symlink history directory: {base}')
            if not base.exists():
                continue
            for run_dir in sorted(base.iterdir(), key=lambda path: path.name, reverse=True):
                if run_dir.name.startswith('.'):
                    continue
                if run_dir.is_dir() or run_dir.is_symlink():
                    entries.append(_history_entry(run_dir, source))
        except (OSError, ValueError) as exc:
            entries.append({'source': source, 'kind': 'history-error', 'run_id': None,
                            'path': str(base), 'status': 'error', 'report': None, 'error': str(exc)})
    return entries
