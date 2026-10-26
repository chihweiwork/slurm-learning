"""Learner progress for the course: one token per learner under shared/course/<token>/progress.json.

Pure bookkeeping on the host filesystem; nothing here talks to Slurm.
"""
from datetime import datetime, timezone
import json
import os
import re
import tempfile
import uuid

from notebook_queries import ROOT

COURSE = ROOT / 'shared' / 'course'
TOKEN = re.compile(r'c[0-9a-f]{8}\Z')


def _token(token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError(f'無效的學習紀錄代碼：{token!r}')
    return token


def _now():
    return datetime.now(timezone.utc).isoformat()


def host_dir(token):
    path = COURSE / _token(token)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f'學習目錄不安全：{path}')
    return path


def container_dir(token):
    return f'/shared/course/{_token(token)}/'


def save(token, progress):
    directory = host_dir(token)
    fd, temporary = tempfile.mkstemp(prefix='.progress-', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(progress, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, directory / 'progress.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def start():
    token = 'c' + uuid.uuid4().hex[:8]
    host_dir(token).mkdir(parents=True, exist_ok=False)
    save(token, {'token': token, 'created': _now(), 'chapters': {}})
    return token


def load(token):
    path = host_dir(token) / 'progress.json'
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f'找不到學習紀錄：{path}')
    progress = json.loads(path.read_text(encoding='utf-8'))
    progress.setdefault('chapters', {})
    return progress


def list_tokens():
    if not COURSE.is_dir():
        return []
    found = []
    for path in COURSE.iterdir():
        if not TOKEN.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
            continue
        try:
            found.append((load(path.name).get('created', ''), path.name))
        except (OSError, ValueError):
            continue
    return [token for _, token in sorted(found, reverse=True)]


def _chapter(progress, chapter):
    if not re.fullmatch(r'[0-9]{2}', chapter):
        raise ValueError(f'章號必須是兩位數字：{chapter!r}')
    return progress['chapters'].setdefault(chapter, {})


def record(token, chapter, key, value):
    progress = load(token)
    _chapter(progress, chapter)[key] = value
    save(token, progress)
    return progress


def mark_task(token, chapter, task_id, verdict):
    """Record a check. A task that already passed stays passed: a later failing recheck (e.g. checking the DRAIN
    task after RESUME) is kept as last_check instead of revoking the earlier pass."""
    progress = load(token)
    tasks = _chapter(progress, chapter).setdefault('tasks', {})
    entry = {'passed': bool(verdict['passed']), 'at': _now(), 'items': verdict['items']}
    previous = tasks.get(task_id)
    if previous and previous.get('passed') and not entry['passed']:
        tasks[task_id] = {**previous, 'last_check': entry}
    else:
        tasks[task_id] = entry
    save(token, progress)
    return progress


def mark_quiz(token, chapter, result, key='quiz'):
    progress = load(token)
    _chapter(progress, chapter)[key] = {'correct': result['correct'], 'total': result['total'], 'at': _now()}
    save(token, progress)
    return progress


def chapter_status(progress, chapter, required_tasks, *, has_quiz=True):
    """'未開始' when the chapter key is absent; '完成' when every required task passed and the quiz (if any) is perfect."""
    data = (progress or {}).get('chapters', {}).get(chapter)
    if data is None:
        return '未開始'
    tasks = data.get('tasks') or {}
    quiz = data.get('quiz')
    done = all((tasks.get(task) or {}).get('passed') for task in required_tasks)
    quizzed = not has_quiz or bool(quiz and quiz['correct'] == quiz['total'])
    return '完成' if done and quizzed else '進行中'
