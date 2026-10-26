"""Chapter 08: slurmdbd accounting.

Read-only helpers (status, sacct, sacctmgr show, earlier-chapter job lookup) run
on page load or explicit query buttons. The only mutations are the registered
run-owned steps: create account demo-<run>, add lab's association, submit one job
under it, then delete the association and account.
"""
import json
import re
import shlex

import notebook_lab as lab
from lesson_common import Pending, case, job_id, probe, receipt, require, state, submit
from slurm_cli import compose_argv, run_command

SACCT_FIELDS = ('JobID', 'JobName', 'User', 'Account', 'Partition', 'State', 'ExitCode', 'DerivedExitCode',
                'Elapsed', 'Timelimit', 'Submit', 'Start', 'End', 'NodeList', 'AllocCPUS', 'ReqMem',
                'MaxRSS', 'AveRSS', 'TotalCPU', 'ReqTRES', 'AllocTRES', 'WorkDir')
DEFAULT_FIELDS = ('JobID', 'JobName', 'Account', 'State', 'ExitCode', 'Elapsed', 'Timelimit', 'MaxRSS',
                  'ReqTRES', 'AllocTRES')
WINDOWS = {'最近 1 小時': 'now-1hours', '最近 6 小時': 'now-6hours', '最近 1 天': 'now-1days', '最近 7 天': 'now-7days'}
STATES = ('', 'COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED', 'OUT_OF_MEMORY', 'RUNNING', 'PENDING')
_JOB = re.compile(r'[0-9]+(_[0-9]+)?\Z')
EXAMPLES = (
    ('02-submit', 'batch', None, 'COMPLETED：第 02 章 cpu.sbatch'),
    ('07-memory', 'offender', None, 'FAILED（step OUT_OF_MEMORY）：第 07 章 OOM offender'),
    ('07-lifecycle', 'descendants', 'timeout', 'TIMEOUT：第 07 章自然限時'),
    ('07-lifecycle', 'descendants', 'cancel', 'CANCELLED：第 07 章手動取消'),
)


def _run(argv, timeout=15):
    try:
        result = run_command(argv, cwd=lab.ROOT, timeout=timeout)
    except Exception as exc:  # transport errors are shown, never turned into success
        return {'argv': argv, 'returncode': None, 'stdout': '', 'stderr': str(exc)}
    return {'argv': argv, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


def accounting_status():
    """Read-only: is slurmctld configured for slurmdbd, and are both services healthy?"""
    config = _run(compose_argv('scontrol', 'show', 'config'))
    values = dict(re.findall(r'^(\S+)\s*=\s*(.*?)\s*$', config['stdout'], re.MULTILINE))
    services = {}
    ps = _run(['docker', 'compose', 'ps', '--all', '--format', 'json'])
    for line in ps['stdout'].splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        for entry in item if isinstance(item, list) else [item]:
            if entry.get('Service') in {'mariadb', 'slurmdbd'}:
                services[entry['Service']] = f"{entry.get('State')} {entry.get('Health') or ''}".strip()
    enabled = values.get('AccountingStorageType') == 'accounting_storage/slurmdbd'
    healthy = enabled and all(services.get(name, '').endswith('healthy') and 'unhealthy' not in services.get(name, '')
                              for name in ('mariadb', 'slurmdbd'))
    return {'enabled': enabled, 'healthy': healthy, 'services': services,
            'config': {key: values.get(key) for key in ('AccountingStorageType', 'AccountingStorageHost',
                                                        'AccountingStorageEnforce', 'JobAcctGatherType',
                                                        'JobAcctGatherFrequency', 'MinJobAge')},
            'errors': [r['stderr'] for r in (config, ps) if r['returncode'] != 0]}


def sacct_argv(*, job_ids=(), window=None, state='', allocations=True, fields=DEFAULT_FIELDS):
    """Validated sacct argv as user lab; raises ValueError on anything outside the whitelist."""
    ids = [value.strip() for value in job_ids if value.strip()]
    if len(ids) > 20 or any(not _JOB.fullmatch(value) for value in ids):
        raise ValueError('Job ID 只接受最多 20 個數字或 數字_數字（array task）。')
    if window is not None and window not in WINDOWS.values():
        raise ValueError('時間範圍只能選擇預設選項。')
    if state not in STATES:
        raise ValueError('State 篩選只接受預設值。')
    fields = list(fields)
    if not fields or any(field not in SACCT_FIELDS for field in fields):
        raise ValueError('欄位只能從清單選擇。')
    argv = ['sacct', '--parsable2', f"--format={','.join(fields)}"]
    if ids:
        argv.append('--jobs=' + ','.join(ids))
    if window:
        argv.append('--starttime=' + window)
    if state:
        argv.append('--state=' + state)
    if allocations:
        argv.append('--allocations')
    return compose_argv(*argv)


def sacct_query(**options):
    """Read-only sacct as lab; rows are dicts keyed by the header sacct printed."""
    try:
        argv = sacct_argv(**options)
    except ValueError as exc:
        return {'status': 'invalid', 'error': str(exc), 'rows': [], 'command': None}
    result = _run(argv)
    lines = [line for line in result['stdout'].splitlines() if line.strip()]
    rows = [dict(zip(lines[0].split('|'), line.split('|'))) for line in lines[1:]] if lines else []
    return {'status': 'ok' if result['returncode'] == 0 else 'error', 'command': shlex.join(argv),
            'rows': rows, 'error': result['stderr'].strip()}


SHOW = {
    'cluster': ('cluster', 'format=Cluster,ControlHost,ControlPort,RPC'),
    'account': ('account', 'format=Account,Description,Organization'),
    'association': ('association', 'format=Cluster,Account,User,Partition,Share,DefaultQOS'),
}


def sacctmgr_show(kind):
    noun, fmt = SHOW[kind]
    argv = compose_argv('sacctmgr', '--parsable2', 'show', noun, fmt)
    result = _run(argv)
    lines = [line for line in result['stdout'].splitlines() if line.strip()]
    rows = [dict(zip(lines[0].split('|'), line.split('|'))) for line in lines[1:]] if lines else []
    return {'status': 'ok' if result['returncode'] == 0 else 'error', 'command': shlex.join(argv),
            'rows': rows, 'error': result['stderr'].strip()}


def earlier_jobs():
    """Most recent owned job per teaching example, from saved receipts only (no adoption)."""
    found = {}
    if not lab.DEMOS.is_dir():
        return []
    for directory in sorted(lab.DEMOS.iterdir(), reverse=True):
        try:
            run = lab.load_run(directory.name)
            receipts = lab.saved_receipts(directory.name)
        except (OSError, ValueError):
            continue
        for chapter, step, mode, label in EXAMPLES:
            if label in found or run['chapter'] != chapter:
                continue
            if mode and run['parameters'].get('mode') != mode:
                continue
            saved = next((r for r in receipts if r['step_id'] == step and r.get('job_id')), None)
            if saved:
                found[label] = {'example': label, 'job_id': saved['job_id'], 'run_id': run['run_id'],
                                'expected_name': lab.job_name(run['run_id'], step)}
    return [found[label] for _, _, _, label in EXAMPLES if label in found]


def compare_earlier():
    """sacct for the earlier-chapter jobs, with steps (MaxRSS lives on steps, not allocations)."""
    examples = earlier_jobs()
    if not examples:
        return {'examples': [], 'rows': [], 'command': None, 'status': 'empty'}
    fields = ('JobID', 'JobName', 'User', 'State', 'ExitCode', 'Elapsed', 'Timelimit', 'MaxRSS', 'ReqTRES', 'AllocTRES')
    result = sacct_query(job_ids=[e['job_id'] for e in examples], fields=fields, allocations=False)
    by_id = {e['job_id']: e for e in examples}
    rows = []
    for row in result['rows']:
        parent = row['JobID'].split('.', 1)[0]
        example = by_id.get(parent) if '.' not in row['JobID'] else None
        identity = ('符合' if row['JobName'] == example['expected_name'] and row['User'] == 'lab'
                    else '不符：ID 可能已重用') if example else ''
        rows.append({'教學對照': example['example'] if example else '', **{key: row[key] for key in
                     ('JobID', 'State', 'ExitCode', 'Elapsed', 'Timelimit', 'MaxRSS', 'ReqTRES', 'AllocTRES',
                      'JobName', 'User')}, '身分核對': identity})
    missing = [e for e in examples if not any(r['JobID'] == e['job_id'] for r in rows)]
    return {**result, 'rows': rows, 'examples': examples, 'missing': missing}

def tier_rows(rows, tier):
    """Filter rows by tier: 1=allocation only, 2=allocation+.0, 3=all. Preserve order."""
    if tier == 1:
        return [r for r in rows if '.' not in r['JobID']]
    elif tier == 2:
        return [r for r in rows if '.' not in r['JobID'] or r['JobID'].endswith('.0')]
    elif tier == 3:
        return rows
    else:
        raise ValueError(f'Invalid tier: {tier}; must be 1, 2, or 3')


# ---- run-owned account experiment -------------------------------------------------


def _ready(run, snapshot):
    status = accounting_status()
    if not status['enabled']:
        return 'accounting 未啟用：AccountingStorageType 不是 accounting_storage/slurmdbd（見本頁啟用說明）'
    if not status['healthy']:
        return f"slurmdbd／MariaDB 尚未 healthy：{status['services']}"
    current = lab.owned_account(run['run_id'])
    if current['exists']:
        return f"account {current['account']} 已存在；不能接管，請清理或建立新 run"
    return {'accounting': status, 'account_before': current}


def _account_ready(run, snapshot):
    done = receipt(run, 'add-account')
    if not done:
        raise Pending('請先建立 account')
    require(done['status'] == 'succeeded', f"add-account 未成功：{done['status']}")
    current = lab.owned_account(run['run_id'])
    require(current['exists'] and current['owned'], f'account 不存在或 Description 不屬於本次 run：{current}')
    return {'account': current}


def _associations(account):
    result = _run(compose_argv('sacctmgr', '--noheader', '--parsable2', 'show', 'association',
                               'where', f'account={account}', 'format=Cluster,Account,User'))
    require(result['returncode'] == 0, f"sacctmgr 查詢失敗：{result['stderr']}")
    return sorted(line for line in result['stdout'].splitlines() if line.strip())


def _association_ready(run, snapshot):
    account = lab.account_name(run['run_id'])
    done = receipt(run, 'add-user')
    if not done:
        raise Pending('請先建立 lab 的 association')
    require(done['status'] == 'succeeded', f"add-user 未成功：{done['status']}")
    rows = _associations(account)
    require(f'compose-lab|{account}|lab' in rows, f'找不到 lab 對 {account} 的 association：{rows}')
    return {'associations': rows}


def _recorded(run):
    account = lab.account_name(run['run_id'])
    rows = state(run, 'job', 'COMPLETED')
    result = sacct_query(job_ids=[job_id(run, 'job')], allocations=True,
                         fields=('JobID', 'JobName', 'User', 'Account', 'State', 'ExitCode', 'Elapsed', 'AllocTRES'))
    require(result['status'] == 'ok', f"sacct 查詢失敗：{result['error']}")
    expected = {'JobName': lab.job_name(run['run_id'], 'job'), 'User': 'lab', 'Account': account,
                'State': 'COMPLETED', 'ExitCode': '0:0'}
    if not result['rows']:
        raise Pending('slurmdbd 尚未收到這筆 job 的完成紀錄；稍候自動刷新')
    row = result['rows'][0]
    require(all(row.get(k) == v for k, v in expected.items()), f'sacct 紀錄不符：{row}，預期 {expected}')
    return {'scheduler': rows, 'sacct': result['rows'], 'command': result['command']}


def _delete_user_ready(run, snapshot):
    return {'recorded': _recorded(run), 'associations_before_delete': _associations(lab.account_name(run['run_id']))}


def _delete_account_ready(run, snapshot):
    done = receipt(run, 'delete-user')
    if not done:
        raise Pending('請先刪除 association')
    require(done['status'] == 'succeeded', f"delete-user 未成功：{done['status']}")
    account = lab.account_name(run['run_id'])
    rows = [row for row in _associations(account) if row.endswith('|lab')]
    require(not rows, f'lab association 仍存在：{rows}')
    current = lab.owned_account(run['run_id'])
    require(current['exists'] and current['owned'], f'account 狀態不符：{current}')
    return {'account_before_delete': current}


def _guard(check):
    def precondition(run, snapshot):
        try:
            return check(run, snapshot)
        except (Pending, AssertionError, ValueError, KeyError, OSError) as exc:
            return str(exc)
    return precondition


def _verify(data):
    def evidence():
        for step in ('add-account', 'add-user', 'job', 'delete-user', 'delete-account'):
            saved = receipt(data, step)
            require(saved and saved['status'] == 'succeeded', f'{step} 尚未成功')
        before = receipt(data, 'delete-user')['evidence']['recorded']
        account = lab.account_name(data['run_id'])
        after = lab.owned_account(data['run_id'])
        require(not after['exists'], f'account {account} 仍存在')
        require(not _associations(account), 'association 仍存在')
        history = sacct_query(job_ids=[job_id(data, 'job')], allocations=True,
                              fields=('JobID', 'Account', 'State', 'ExitCode'))
        require(history['rows'] and history['rows'][0]['Account'] == account,
                f'刪除 account 後 sacct 歷史仍應保留原 Account：{history}')
        return {'recorded_before_delete': before, 'account_after': after, 'history_after_delete': history}
    return [case('accounting-sacct-association', evidence)]


def get_lesson(chapter):
    if chapter != '08-accounting':
        raise ValueError(f'Unknown accounting chapter: {chapter}')
    steps = {
        'add-account': lab.Step('accounting', lambda r: lab.accounting_argv(r['run_id'], 'add-account'), _guard(_ready)),
        'add-user': lab.Step('accounting', lambda r: lab.accounting_argv(r['run_id'], 'add-user'), _guard(_account_ready)),
        'job': lab.Step('submit', lambda r: submit(r, 'job', command=probe('affinity'),
                                                   options=(f"--account={lab.account_name(r['run_id'])}",)),
                        _guard(_association_ready)),
        'delete-user': lab.Step('accounting', lambda r: lab.accounting_argv(r['run_id'], 'delete-user'),
                                _guard(_delete_user_ready)),
        'delete-account': lab.Step('accounting', lambda r: lab.accounting_argv(r['run_id'], 'delete-account'),
                                   _guard(_delete_account_ready)),
    }
    lesson = {'chapter': chapter, 'title': '08｜Accounting：sacct 歷史與 sacctmgr 帳戶', 'fields': {},
              'steps': steps,
              'labels': {'add-account': '1 建立本次專屬 account', 'add-user': '2 建立 lab ↔ account association',
                         'job': '3 以該 account 提交一個短工作', 'delete-user': '4 sacct 查到紀錄後刪除 association',
                         'delete-account': '5 刪除本次 account'},
              'verify': _verify, 'cases': ['accounting-sacct-persistence'], 'sources': ['cpu_probe.py']}
    lab.register_chapter(chapter, steps, verify=_verify)
    return lesson
