"""第 09 章維運練習：學員自己下指令；本模組只負責檢查。

評分是純函式（觀察資料進、判定出），可單元測試。I/O 只以 lab 身分做唯讀查詢。
"""
from datetime import datetime

import course_progress
from notebook_queries import ROOT
from slurm_cli import compose_argv, run_command

TOKEN = course_progress.TOKEN
_token = course_progress._token
BAD_NODE = ('DOWN', 'FAIL', 'NOT_RESPONDING', 'NO_RESPOND', 'UNKNOWN')


def reason_for(token):
    return f'course-{_token(token)}'


def probe_name(token):
    return f'course-{_token(token)}-probe'


def _item(name, ok, detail):
    return {'項目': name, '結果': '✓' if ok else '✗', '說明': detail}


def _verdict(items, stop=None):
    return {'passed': bool(items) and all(i['結果'] == '✓' for i in items) and not stop,
            'items': items, 'stop': stop}


def _node(nodes, name):
    return next((n for n in nodes if n.get('name') == name), None)


def _drained(node):
    return any('DRAIN' in state for state in node.get('state', []))


# ---- pure graders ---------------------------------------------------------------------

def grade_nodes(answers, nodes):
    items = []
    cpu01, cpu02, gpu01 = (_node(nodes, n) for n in ('cpu01', 'cpu02', 'gpu01'))
    value = str(answers.get('cpu01_cpuefctv', '')).strip()
    if cpu01 is None:
        items.append(_item('cpu01 CPUEfctv', False, '查不到 cpu01；先確認 controller 正常'))
    else:
        items.append(_item('cpu01 CPUEfctv', value == str(cpu01['effective_cpus']),
                           '正確' if value == str(cpu01['effective_cpus']) else
                           ('未填' if not value else '不對：看的是 CPUEfctv（可排程數），不是 CPUTot（拓樸）')))
    value = str(answers.get('cpu02_state', '')).strip().upper()
    if cpu02 is None:
        items.append(_item('cpu02 State', False, '查不到 cpu02'))
    else:
        states = [s.upper() for s in cpu02.get('state', [])]
        ok = bool(value) and (value in states or value.split('+')[0] in states)
        items.append(_item('cpu02 State', ok, '正確' if ok else
                           ('未填' if not value else '不對：填主要狀態一個詞，例如 IDLE、ALLOCATED、MIXED')))
    value = str(answers.get('gpu01_gres', '')).strip()
    if gpu01 is None:
        items.append(_item('gpu01 Gres', False, '查不到 gpu01'))
    else:
        ok = bool(value) and value == gpu01.get('gres', '')
        items.append(_item('gpu01 Gres', ok, '正確' if ok else
                           ('未填' if not value else '不對：抄節點欄位 Gres= 後面的值（格式 種類:數量）')))
    return _verdict(items)


def grade_controller(answers, pings):
    primary = next((p for p in pings if p.get('primary')), None)
    if primary is None or not primary.get('responding'):
        return _verdict([_item('controller', False, '查不到回應中的 primary controller')],
                        stop='controller 無法確認：停手，依第 09 章停手規則找管理者')
    host = str(answers.get('primary_host', '')).strip()
    status = str(answers.get('status', '')).strip().upper()
    return _verdict([
        _item('primary 主機', host == primary['hostname'], '正確' if host == primary['hostname'] else
              ('未填' if not host else '不對：看輸出中 primary 後面的主機名')),
        # `scontrol ping` prints UP/DOWN from `responding`; the JSON `status` field is an error string.
        _item('狀態', status == 'UP', '正確' if status == 'UP' else
              ('未填' if not status else '不對：看輸出最後的狀態字')),
    ])


def grade_accounting(answers, cluster_name, default_account):
    if not cluster_name or not default_account:
        return _verdict([_item('sacctmgr', False, '查不到 cluster 或 DefaultAccount；accounting 可能未啟用（見第 08 章）')])
    cluster = str(answers.get('cluster_name', '')).strip()
    account = str(answers.get('default_account', '')).strip()
    return _verdict([
        _item('cluster 名稱', cluster == cluster_name, '正確' if cluster == cluster_name else
              ('未填' if not cluster else '不對：用 sacctmgr 列出 cluster')),
        _item('lab 的 DefaultAccount', account == default_account, '正確' if account == default_account else
              ('未填' if not account else '不對：用 sacctmgr 查使用者 lab 的 DefaultAccount 欄')),
    ])


def drain_preflight(token, nodes, queue):
    cpu02 = _node(nodes, 'cpu02')
    if cpu02 is None:
        return _verdict([_item('cpu02', False, '查不到 cpu02')], stop='節點資訊不完整：停手找管理者')
    states = cpu02.get('state', [])
    items = []
    if any(bad in s for s in states for bad in BAD_NODE):
        return _verdict([_item('cpu02 健康', False, f"狀態 {'+'.join(states)}")],
                        stop='cpu02 不健康（DOWN/FAIL/NOT_RESPONDING）：停手找管理者，不要 RESUME')
    if _drained(cpu02):
        if not owns_reason(token, cpu02.get('reason')):
            return _verdict([_item('cpu02 Reason', False, f"已被 DRAIN，Reason={cpu02.get('reason') or '（空）'}")],
                            stop='cpu02 已在別人的維護中（Reason 不是你的）：停手找管理者，不要 RESUME')
        items.append(_item('cpu02 Reason', True, '已是你的 DRAIN（可直接進入下一步）'))
    else:
        items.append(_item('cpu02 未在維護中', True, f"狀態 {'+'.join(states)}，Reason 空"))
    external = [row['job_id'] for row in queue]
    probe = probe_name(token)
    if external:
        return _verdict(items + [_item('queue 沒有其他工作', False, f'目前有 {", ".join(external)}')],
                        stop=f'queue 裡有工作：可能是別人的，不能 DRAIN 干擾。等它們結束或找管理者（你的 probe 名稱是 {probe}）')
    items.append(_item('queue 沒有其他工作', True, '可以開始'))
    return _verdict(items)


def owns_reason(token, value):
    """The learner's Reason is course-<token> or course-<token>-<note>."""
    reason = reason_for(token)
    return isinstance(value, str) and (value == reason or value.startswith(reason + '-'))


def grade_drained(token, nodes, events=()):
    """cpu02 is (or, per accounting events, was) drained with the learner's Reason.

    events lets the check pass after the learner already RESUMEd: the DRAIN is still on record in sacctmgr."""
    cpu02 = _node(nodes, 'cpu02')
    if cpu02 is None:
        return _verdict([_item('cpu02', False, '查不到 cpu02')])
    if not _drained(cpu02):
        mine = [e for e in events if owns_reason(token, e.get('reason'))]
        if mine:
            return _verdict([_item('你 DRAIN 過 cpu02', True,
                                   f"accounting 事件：{mine[-1]['time_start']} 起，Reason={mine[-1]['reason']}（之後已 RESUME）")])
        return _verdict([_item('cpu02 DRAIN', False, f"還沒 DRAIN，狀態 {'+'.join(cpu02.get('state', []))}；"
                                                     f"先在終端執行 `scontrol update NodeName=cpu02 State=DRAIN Reason={reason_for(token)}-practice`")])
    if not owns_reason(token, cpu02.get('reason')):
        return _verdict([_item('cpu02 Reason', False, f"Reason={cpu02.get('reason')}")],
                        stop='DRAIN 的 Reason 不是你的：可能是別人的維護，停手找管理者')
    return _verdict([_item('cpu02 DRAIN', True, f"狀態 {'+'.join(cpu02['state'])}"),
                     _item('Reason 所有權', True, f"Reason={cpu02.get('reason')}")])


def grade_probe_pending(token, probe_rows):
    if not probe_rows:
        return _verdict([_item('probe 在 queue', False, '沒看到 probe：還沒提交，或已經結束（若在 RESUME 後才提交就看不到等待）')])
    row = probe_rows[-1]
    pending = row['state'] == 'PENDING'
    reason = row['reason']
    return _verdict([
        _item('probe PENDING', pending, f"job {row['job_id']} 狀態 {row['state']}"),
        _item('等待原因', pending and 'ReqNodeNotAvail' in reason,
              f'Reason={reason}' + ('：節點在維護，不收新工作' if 'ReqNodeNotAvail' in reason else
                                    '；Reason 可能還沒更新（Resources/Priority/None），稍候再檢查')),
    ])


def parse_events(stdout):
    rows = []
    for line in stdout.splitlines():
        parts = line.split('|')
        if len(parts) >= 6:
            rows.append({'node': parts[0], 'time_start': parts[1], 'time_end': parts[2],
                         'state': parts[3], 'reason': parts[4], 'user': parts[5]})
    return rows


def parse_probe_sacct(stdout):
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split('|')
    return [dict(zip(header, line.split('|'))) for line in lines[1:]]


def _time(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def grade_resumed(token, nodes, events, probe_rows):
    cpu02 = _node(nodes, 'cpu02')
    items = []
    if cpu02 is None:
        return _verdict([_item('cpu02', False, '查不到 cpu02')])
    still = _drained(cpu02) or owns_reason(token, cpu02.get('reason'))
    items.append(_item('cpu02 已 RESUME', not still,
                       f"還在維護：狀態 {'+'.join(cpu02.get('state', []))}、Reason={cpu02.get('reason') or '（空）'}；"
                       '先在終端執行 `scontrol update NodeName=cpu02 State=RESUME`，再按「檢查」' if still
                       else f"狀態 {'+'.join(cpu02.get('state', []))}"))
    mine = [e for e in events if owns_reason(token, e['reason'])]
    closed = [e for e in mine if _time(e['time_end'])]
    items.append(_item('accounting 事件紀錄', bool(closed),
                       f"DRAIN {closed[-1]['time_start']} → {closed[-1]['time_end']}" if closed else
                       ('DRAIN 事件還沒結束（TimeEnd=Unknown）：RESUME 之後才會記下結束時間' if mine
                        else '查不到 Reason 為你的 DRAIN 事件：先做完任務 t1 的 DRAIN')))
    finished = [r for r in probe_rows if r.get('State')]
    if not probe_rows:
        pass  # probe is optional in the course: no rows means it was not part of this check
    elif not finished:
        items.append(_item('probe 在 RESUME 後執行', False, '查不到 probe 的 accounting 紀錄'))
    else:
        probe = max(finished, key=lambda r: int(r['JobID']) if r['JobID'].isdigit() else -1)
        start, end = _time(probe.get('Start')), _time(closed[-1]['time_end']) if closed else None
        ok = probe['State'] == 'COMPLETED' and start is not None and end is not None and start >= end
        detail = f"job {probe['JobID']} {probe['State']}，Start={probe.get('Start')}"
        if probe['State'] != 'COMPLETED':
            detail += '；等它完成再檢查'
        elif start is not None and end is not None and start < end:
            detail += '；比 RESUME 早開始，代表提交時節點並未維護中'
        items.append(_item('probe 在 RESUME 後執行', ok, detail))
    return _verdict(items)


# ---- read-only I/O (user lab) --------------------------------------------------------

def _lab(*args):
    """Read-only query as lab; a failed query yields '' so graders report it, not crash."""
    try:
        result = run_command(compose_argv(*args), cwd=ROOT, timeout=15)
    except OSError:
        return ''
    return result.stdout if result.returncode == 0 else ''


def cluster_facts():
    cluster = _lab('sacctmgr', '-nP', 'show', 'cluster', 'format=Cluster').strip().splitlines()
    account = _lab('sacctmgr', '-nP', 'show', 'user', 'lab', 'format=DefaultAccount').strip().splitlines()
    return {'cluster_name': cluster[0] if cluster else None, 'default_account': account[0] if account else None}


def node_events():
    return parse_events(_lab('sacctmgr', '-nP', 'show', 'event', 'Nodes=cpu02',
                             'format=NodeName,TimeStart,TimeEnd,State,Reason,User'))


def probe_queue(token):
    rows = []
    for line in _lab('squeue', '--noheader', f'--name={probe_name(token)}', '--format=%i|%T|%R').splitlines():
        parts = line.split('|')
        if len(parts) == 3:
            rows.append({'job_id': parts[0].strip(), 'state': parts[1].strip(), 'reason': parts[2].strip()})
    return rows


def probe_sacct(token):
    return parse_probe_sacct(_lab('sacct', '-X', '--parsable2', '--starttime=now-1days',
                                  f'--name={probe_name(token)}', '--format=JobID,State,Start,End,NodeList'))
