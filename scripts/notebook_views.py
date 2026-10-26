"""Presentation shared by the marimo notebooks; no external effects."""
from html import escape
from urllib.parse import quote

CHAPTERS = [
    ('00_start.py', '00｜從這裡開始', 10, ['t0-sinfo']),
    ('01_architecture.py', '01｜Slurm 架構與運作原理', 30, []),
    ('02_basic_usage.py', '02｜基本用法：提交、查看、取消', 30, ['t1-submit', 't2-squeue', 't3-show-job', 't4-sacct', 't5-cancel']),
    ('03_sbatch_resources.py', '03｜寫好一個 sbatch：資源怎麼申請', 30, ['t1-files', 't2-first', 't3-second']),
    ('04_scheduling.py', '04｜排程與等待：為什麼我的工作在 PENDING', 25, ['t1-reason']),
    ('05_parallel.py', '05｜平行與多節點：array、dependency、MPI', 30, ['t1-array', 't2-dependency']),
    ('06_gpu_containers.py', '06｜GPU 與容器', 20, ['t1-gpu-job']),
    ('07_troubleshooting.py', '07｜失敗排查：OOM、TIMEOUT、取消', 25, ['t1-oom', 't2-timeout']),
    ('08_accounting.py', '08｜用量與 accounting', 20, ['t1-sacct-usage', 't2-assoc']),
    ('09_operations.py', '09｜維運入門：DRAIN／RESUME 與何時停手', 30, ['t1-drain', 't2-resume']),
    ('10_capstone.py', '10｜總結與綜合練習', 30, ['t1-files', 't2-first', 't3-second', 't4-failure']),
]
# Chapters without a quiz: 00 (orientation only). Every other chapter's completion needs a perfect quiz.
NO_QUIZ = {'00'}
STATUS_MARKS = {'完成': '✓', '進行中': '●', '未開始': '○'}


def chapter_entry(chapter):
    """(filename, title, minutes, required_tasks) for a two-digit chapter number."""
    return next(entry for entry in CHAPTERS if entry[0].startswith(chapter + '_'))


def chapter_mark(progress, chapter):
    import course_progress
    if progress is None:
        return STATUS_MARKS['未開始']
    status = course_progress.chapter_status(progress, chapter, chapter_entry(chapter)[3], has_quiz=chapter not in NO_QUIZ)
    return STATUS_MARKS[status]


COMMAND_KINDS = {
    'required': ('必做', 'success'),
    'diagnostic': ('只讀診斷', 'info'),
    'recovery': ('故障時才做', 'warn'),
    'forbidden': ('禁止：不要執行', 'danger'),
}


def command_block(mo, kind, command, note=''):
    """One copyable terminal command per block, labelled by when it may be run."""
    label, callout = COMMAND_KINDS[kind]
    return mo.md(f'**【{label}】** {note}\n\n```bash\n{command}\n```').callout(kind=callout)


def navigation(mo, current_chapter, progress=None):
    """Use native links: nav_menu rewrites Gallery query-string routes. ✓ 完成、● 進行中、○ 未開始."""
    links = ['<a href="/" target="_self">Gallery</a>']
    for name, title, minutes, _ in CHAPTERS:
        chapter = name[:2]
        current = chapter == current_chapter
        attribute = ' aria-current="page"' if current else ''
        label = (f'{chapter_mark(progress, chapter)} {escape(title)} <small>{minutes} 分</small>'
                 + (' <small>（目前頁面）</small>' if current else ''))
        links.append(f'<a href="/?file={quote(name)}" target="_self"{attribute}>{label}</a>')
    return mo.Html(
        '<style>.lab-navigation a {display:block;padding:0.45rem 0.6rem;'
        'border-left:3px solid transparent;color:inherit;text-decoration:none;}'
        '.lab-navigation a:hover {text-decoration:underline;}'
        '.lab-navigation a[aria-current="page"] {border-left-color:currentColor;font-weight:700;}'
        '</style><nav class="lab-navigation" aria-label="課程章節">'
        + ''.join(links) + '</nav>'
    )


def next_chapter_link(mo, current_chapter):
    names = [entry[0] for entry in CHAPTERS]
    index = next(i for i, name in enumerate(names) if name.startswith(current_chapter + '_'))
    if index + 1 == len(CHAPTERS):
        return mo.md('這是最後一章。')
    name, title = CHAPTERS[index + 1][:2]
    return mo.md(f'[下一章 → {title}](/?file={quote(name)})')


def json_view(mo, value):
    import json
    text = json.dumps(value, ensure_ascii=False, indent=2)
    preview = mo.plain_text(text[:65536])
    if len(text) <= 65536:
        return preview
    return mo.vstack([mo.md('JSON 預覽截斷至前 65536 字元；完整證據可下載。'), preview,
                      mo.download(lambda: text.encode('utf-8'), filename='evidence.json',
                                  mimetype='application/json', label='下載完整 JSON 證據')])


def table_rows(rows):
    import json
    return [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
             for k, v in row.items() if k != 'raw'} for row in rows]


def result_table(mo, items, title='檢查結果'):
    """Grader items as a plain Markdown table: no search box that could be mistaken for an answer field."""
    def cell(value):
        return str(value if value not in (None, '') else '').replace('|', '\\|').replace('\n', ' ')
    lines = ['| 項目 | 結果 | 說明 |', '| :--- | :---: | :--- |']
    lines += [f"| {cell(i.get('項目'))} | {cell(i.get('結果'))} | {cell(i.get('說明'))} |" for i in items]
    return mo.md(f'---\n\n**{title}**（唯讀，不是作答欄）\n\n' + '\n'.join(lines))


RETENTION = [
    # (資料, 存在哪裡, 保存多久, 誰清理, 怎麼查)
    ('controller retained record', 'slurmctld 記憶體與 `controller-state` volume',
     '工作結束後約 `MinJobAge=3600` 秒（1 小時）', 'slurmctld 自動移除', '`squeue`、`scontrol show job`'),
    ('slurmdbd job 歷史（accounting）', 'MariaDB（`accounting-db` volume）',
     '本 lab 沒有設定任何 `Purge*`：保存到管理者清除；`docker compose down --volumes` 會連 volume 一起刪掉',
     '管理者', '`sacct`、`sacctmgr`'),
    ('教材 receipt／report／輸出', '主機 `shared/demos/<run-id>/`',
     '永久，直到你自己刪除；「只清理本次實驗」只取消工作、恢復節點，不刪證據', '你（手動刪除）', '各章證據區、`report.json`'),
    ('學習紀錄、練習檔與 smoke 報告', '主機 `shared/course/<代碼>/`、`shared/results/`',
     '永久，直到你自己刪除', '你（手動刪除）', '檔案本身'),
]


def retention_table(mo):
    """Single source for 'how long is what kept, and who removes it' (chapters 08 and 09)."""
    lines = ['| 資料 | 存在哪裡 | 保存多久 | 誰清理 | 怎麼查 |', '| :--- | :--- | :--- | :--- | :--- |']
    lines += ['| ' + ' | '.join(row) + ' |' for row in RETENTION]
    return mo.md('**三種紀錄各自的保存期限**\n\n' + '\n'.join(lines) +
                 '\n\n正式叢集的 slurmdbd 通常設定 `PurgeJobAfter` 等清除規則（常見數月到一年），以站台公告為準。')
