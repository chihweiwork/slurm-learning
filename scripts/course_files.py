"""Learner files under shared/course/<token>/: plain names only, no symlinks, atomic writes."""
import os
import re
import tempfile

from course_progress import host_dir

NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\Z')
MAX_BYTES = 256 * 1024


def _path(token, name):
    if not isinstance(name, str) or not NAME.fullmatch(name) or '..' in name:
        raise ValueError(f'檔名只能用英數字、底線、點與減號：{name!r}')
    return host_dir(token) / name


def read_file(token, name):
    path = _path(token, name)
    if path.is_symlink() or not path.is_file():
        return None
    with path.open('rb') as stream:
        return stream.read(MAX_BYTES).decode('utf-8', errors='replace')


def write_file(token, name, text):
    path = _path(token, name)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f'拒絕覆寫非一般檔案：{path}')
    data = text.encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError(f'檔案超過 {MAX_BYTES // 1024} KiB')
    fd, temporary = tempfile.mkstemp(prefix='.edit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(data)


def list_files(token):
    directory = host_dir(token)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith('.') or path.is_symlink() or not path.is_file():
            continue
        info = path.stat()
        rows.append((path.name, info.st_size, info.st_mtime))
    return rows


def find_output(token, job_id):
    """A non-empty regular file whose name contains the job ID as a whole number (job-123.out, slurm-123.out)."""
    job_id = str(job_id).strip()
    if not re.fullmatch(r'[0-9]+', job_id):
        return None
    pattern = re.compile(rf'(?<![0-9]){job_id}(?![0-9])')
    directory = host_dir(token)
    if not directory.is_dir():
        return None
    for path in sorted(directory.iterdir()):
        if pattern.search(path.name) and path.is_file() and not path.is_symlink() and path.stat().st_size > 0:
            return path
    return None
