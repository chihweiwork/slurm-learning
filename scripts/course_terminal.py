"""The in-page mini terminal: one whitelisted command per line, never through a shell.

parse() splits a line like a shell would but refuses pipes, redirection and command
substitution outside quotes; check() decides which user runs it (and for how long) or
raises Denied with a hint; execute() runs it with `docker compose exec -w <練習目錄>` and
appends the result to shared/course/<token>/terminal.jsonl.
"""
from datetime import datetime, timezone
import json
import re
import shlex
import subprocess
import time

from course_progress import _token, container_dir, host_dir
from notebook_queries import ROOT
from slurm_cli import compose_argv, run_command

METACHARS = set('|;&<>`')
ALLOWED = frozenset({'sinfo', 'squeue', 'sprio', 'sstat', 'sacct', 'hostname', 'scontrol', 'sbatch', 'srun',
                     'scancel', 'sacctmgr', 'cat', 'head', 'tail', 'ls', 'wc', 'pwd'})
READ_ONLY = frozenset({'sinfo', 'squeue', 'sprio', 'sstat', 'sacct', 'hostname'})
FILES = frozenset({'cat', 'head', 'tail', 'ls', 'wc', 'pwd'})
LIMIT = 16 * 1024
EXAMPLES = '/opt/lab/examples/'
_JOB_ID = re.compile(r'[0-9]+(_[0-9]+)?\Z')
_SLUG = r'[a-z0-9][a-z0-9-]{0,19}'
MODES = ('user', 'accounting', 'ops')


class Denied(ValueError):
    """The line was refused before anything ran; the message is the hint shown to the learner."""


def _unquoted_metachar(line):
    quote, escaped = None, False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in '"\'':
            quote = char
        elif char in METACHARS or (char == '$' and line[index + 1:index + 2] == '('):
            return True
    return False


def parse(line):
    """argv for one line; pipes, redirection, `;`, `&` and command substitution outside quotes are refused."""
    if _unquoted_metachar(line or ''):
        raise Denied('這個終端不支援管線、重導向與子 shell；請用指令自己的選項，例如 squeue --format="%i %T %R"')
    try:
        argv = shlex.split(line or '')
    except ValueError as exc:
        raise Denied(f'引號沒有成對：{exc}') from None
    if not argv:
        raise Denied('請輸入指令')
    return argv


def _positional(argv):
    return [arg for arg in argv[1:] if not arg.startswith('-')]


def _path_ok(token, value):
    if value.startswith('/'):
        return (value.startswith(container_dir(token)) or value.startswith(EXAMPLES)) and '..' not in value.split('/')
    return '..' not in value.split('/')


def _check_path(token, value):
    if not _path_ok(token, value):
        raise Denied(f'路徑 {value} 不在你的練習目錄：只能用相對路徑（不含 ..），或 {container_dir(token)}、{EXAMPLES} 底下的檔案')


def _has_flag(argv, *names):
    """True when any argument is one of names, `name=…`, or a short flag with an attached value (-Dx)."""
    for arg in argv[1:]:
        for name in names:
            if arg == name or arg.startswith(name + '=') or (len(name) == 2 and not name.startswith('--') and arg.startswith(name)):
                return True
    return False


def _check_scontrol(token, argv, mode):
    words = _positional(argv)
    verb = words[0].lower() if words else ''
    if verb in {'show', 'ping'}:
        return 'lab', 10
    if verb == 'update' and mode == 'ops':
        if any(arg.startswith('-') for arg in argv[1:]):
            raise Denied('scontrol update 不接受其他旗標')
        pairs = {}
        for word in words[1:]:
            key, _, value = word.partition('=')
            if not value or key.lower() in pairs:
                raise Denied(f'看不懂 {word}：格式是 Key=Value，例如 NodeName=cpu02')
            pairs[key.lower()] = value
        state = pairs.get('state', '').upper()
        reason = pairs.get('reason')
        if pairs.get('nodename') != 'cpu02' or state not in {'DRAIN', 'RESUME'} or set(pairs) - {'nodename', 'state', 'reason'}:
            raise Denied('第 09 章只開放 scontrol update NodeName=cpu02 State=DRAIN Reason=course-<代碼>… 與 State=RESUME')
        if state == 'DRAIN' and not (reason or '').startswith(f'course-{token}'):
            raise Denied(f'DRAIN 必須寫 Reason，並以 course-{token} 開頭（這是你對這次維護的所有權標記）')
        if reason is not None and not reason.startswith(f'course-{token}'):
            raise Denied(f'Reason 必須以 course-{token} 開頭')
        return 'root', 15
    raise Denied('scontrol 只開放 show／ping（第 09 章另開放 DRAIN／RESUME cpu02）')


def _check_sbatch(token, argv):
    if _has_flag(argv, '--uid', '--gid'):
        raise Denied('不能用 --uid／--gid 冒充別的使用者')
    if _has_flag(argv, '--chdir', '-D'):
        raise Denied('工作目錄已固定為你的練習目錄，不需要 --chdir／-D')
    if _has_flag(argv, '--wrap'):
        return 'lab', 15
    words = _positional(argv)
    if not words:
        raise Denied('要給一個腳本，例如 sbatch job.sbatch，或用 --wrap "指令"')
    for word in words:
        if '/' in word or word == words[-1]:
            _check_path(token, word)
    return 'lab', 15


def _check_scancel(argv):
    forbidden = ('-u', '--user', '--me', '-A', '--account', '-p', '--partition', '-t', '--state',
                 '-n', '--name', '--signal', '-s', '-q', '--qos', '-w', '--nodelist', '-M', '--clusters')
    hint = 'scancel 只接受你自己的 job ID，例如 scancel 123；先用 squeue --me 查 ID'
    if _has_flag(argv, *forbidden):
        raise Denied(hint + '（篩選條件會一次取消很多工作，這裡不開放）')
    words = _positional(argv)
    if not words or not all(_JOB_ID.fullmatch(word) for word in words):
        raise Denied(hint)
    return 'lab', 10


def _check_sacctmgr(token, argv, mode):
    words = _positional(argv)
    verb = words[0].lower() if words else ''
    if verb in {'show', 'list'}:
        return 'lab', 10
    hint = (f'sacctmgr 只開放 show／list（第 08 章另開放 add／delete account name=course-{token}-<名稱>、'
            f'add／delete user name=lab account=course-{token}-<名稱>）')
    if mode != 'accounting' or verb not in {'add', 'delete'} or len(words) < 3:
        raise Denied(hint)
    if any(arg.startswith('-') and arg not in {'-i', '--immediate'} for arg in argv[1:]):
        raise Denied('add／delete 不接受其他旗標')
    noun = words[1].lower()
    pairs = {}
    for word in words[2:]:
        key, _, value = word.partition('=')
        if not value or key.lower() in pairs:
            raise Denied(f'看不懂 {word}：格式是 key=value')
        pairs[key.lower()] = value
    account = re.compile(f'course-{token}-{_SLUG}')
    if noun == 'account':
        allowed = {'name'} | ({'description', 'organization', 'cluster'} if verb == 'add' else set())
        ok = account.fullmatch(pairs.get('name', '').lower()) and not set(pairs) - allowed
    elif noun == 'user':
        allowed = {'name', 'account'} | ({'cluster'} if verb == 'add' else set())
        ok = (pairs.get('name') == 'lab' and account.fullmatch(pairs.get('account', '').lower())
              and not set(pairs) - allowed)
    else:
        ok = False
    if not ok:
        raise Denied(hint)
    return 'root', 20


def _check_files(token, argv):
    for word in _positional(argv):
        _check_path(token, word)
    return 'lab', 5


def check(token, argv, *, mode):
    """(user, timeout) for an allowed argv; raises Denied(hint) otherwise."""
    _token(token)
    if mode not in MODES:
        raise ValueError(f'未知的終端模式：{mode}')
    command = argv[0]
    if command in READ_ONLY:
        return 'lab', 10
    if command == 'scontrol':
        return _check_scontrol(token, argv, mode)
    if command == 'sbatch':
        return _check_sbatch(token, argv)
    if command == 'srun':
        if _has_flag(argv, '--pty'):
            raise Denied('這個終端不是互動式 shell，不支援 --pty；直接在 srun 後面寫要執行的程式')
        if _has_flag(argv, '--uid', '--gid'):
            raise Denied('不能用 --uid／--gid 冒充別的使用者')
        return 'lab', 60
    if command == 'scancel':
        return _check_scancel(argv)
    if command == 'sacctmgr':
        return _check_sacctmgr(token, argv, mode)
    if command in FILES:
        return _check_files(token, argv)
    raise Denied(f"這個終端只開放 Slurm 指令與檔案查看：{'、'.join(sorted(ALLOWED))}")


def _clip(text):
    text = text or ''
    return text if len(text) <= LIMIT else text[:LIMIT] + '\n…（已截斷）'


def _append(token, entry):
    with (host_dir(token) / 'terminal.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')


def execute(token, line, *, mode='user'):
    """Run one line; every attempt (including refused ones) is appended to terminal.jsonl."""
    _token(token)
    entry = {'at': datetime.now(timezone.utc).isoformat(), 'command': line, 'argv': [], 'user': None,
             'returncode': None, 'stdout': '', 'stderr': '', 'seconds': None, 'denied': None}
    try:
        argv = parse(line)
        entry['argv'] = argv
        user, timeout = check(token, argv, mode=mode)
    except Denied as exc:
        entry['denied'] = str(exc)
        _append(token, entry)
        return entry
    entry['user'] = user
    final = ['sacctmgr', '-i', *argv[1:]] if argv[0] == 'sacctmgr' and user == 'root' else argv
    started = time.monotonic()
    try:
        result = run_command(compose_argv(*final, user=user, workdir=container_dir(token)), cwd=ROOT, timeout=timeout)
        entry.update(returncode=result.returncode, stdout=_clip(result.stdout), stderr=_clip(result.stderr))
    except subprocess.TimeoutExpired:
        entry['stderr'] = f'超過 {timeout} 秒沒有結束，已中止。長時間工作請改用 sbatch 提交。'
    except OSError as exc:
        entry['stderr'] = f'無法執行：{exc}'
    entry['seconds'] = round(time.monotonic() - started, 2)
    _append(token, entry)
    return entry


def transcript(token, limit=None):
    """Saved terminal entries, oldest first; unreadable lines are skipped."""
    path = host_dir(token) / 'terminal.jsonl'
    if path.is_symlink() or not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('argv'), list):
            entries.append(value)
    return entries[-limit:] if limit else entries
