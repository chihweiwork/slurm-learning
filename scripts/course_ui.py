"""Page components for the course notebooks. Every function takes `mo` first.

marimo reactivity contract used by every chapter:
- State lives in one "state cell" per chapter (`mo.state(..., allow_self_loops=True)`); a widget's view
  cell creates its own buttons and re-renders when its setter is called from those buttons.
- Demo buttons are created by demo_controls() in a cell that does NOT depend on the auto-refresh, so a
  periodic refresh never drops a click or a typed confirmation; demo() cards re-render on every refresh.
"""
from datetime import datetime
from html import escape
import json
import shlex
import weakref

import course_files
import course_progress
import course_quiz
import course_tasks
import course_runner
import course_terminal
from closing import closing_panel
from notebook_queries import ROOT
from notebook_views import CHAPTERS, chapter_entry, navigation, next_chapter_link, result_table
from slurm_cli import compose_argv, run_command

NEED_TOKEN = '請先在左側「開始新的學習紀錄」'

# Prefix → meaning, matched against each argv element (and two-word commands) of a demo step.
ANNOTATIONS = [
    ('docker compose exec -T -u root controller', '在 controller 容器以 root（管理者）身分執行'),
    ('docker compose exec -T -u lab controller', '在 controller 容器（登入節點）以一般使用者 lab 執行'),
    ('docker compose restart', '重啟 controller 容器（模擬 slurmctld 當掉重啟）'),
    ('docker compose up', '把 controller 容器重新啟動起來（故障復原）'),
    ('scontrol update', '管理者改節點狀態'),
    ('sbatch', '提交批次工作，立刻回傳 JobID'),
    ('srun', '在 allocation 裡啟動一個 step'),
    ('scancel', '終止工作'),
    ('sacctmgr', '管理 accounting 的帳戶與關聯'),
    ('--parsable', '只印 JobID，方便程式讀取'),
    ('--job-name', '工作名稱，squeue／sacct 都看得到'),
    ('--chdir', '工作目錄（相對路徑都從這裡算）'),
    ('--output', 'stdout 寫到哪；%j 是 JobID，%A_%a 是 array 母 ID 與 task 編號'),
    ('--error', 'stderr 寫到哪'),
    ('--partition', '要排到哪個節點群'),
    ('--nodelist', '指定一定要用哪些節點'),
    ('--nodes', '要幾個節點'),
    ('--ntasks', '總共啟動幾個 task（程序）'),
    ('--cpus-per-task', '每個 task 要幾個 CPU'),
    ('--mem', '記憶體上限，超過會被 OOM-kill'),
    ('--time', '時間上限，超過會 TIMEOUT'),
    ('--gres', '一般資源，這裡是 GPU'),
    ('--array', '一次送多個 task'),
    ('--dependency', '等另一個工作結束後才排程'),
    ('--kill-on-invalid-dep', '相依條件不可能滿足時要不要直接取消'),
    ('--wrap', '直接把一行命令包成腳本'),
    ('--exclusive', '獨佔整個節點'),
    ('--immediate', '資源不夠就在幾秒內放棄，不排隊'),
    ('--cpu-bind', '把程序綁在分到的 CPU 上'),
    ('--account', '這個工作記在哪個 account'),
    ('--container-image', 'Pyxis：在這個容器 image 裡執行'),
    ('NodeName=', '要改哪個節點'),
    ('State=', '要改成什麼狀態'),
    ('Reason=', '維護原因；也是「這是誰的維護」的所有權標記'),
]
STATE_KIND = {'尚未就緒': 'warn', '可執行': 'success', '執行中': 'info', '已消耗': 'neutral'}


# marimo's UI registry holds only weak references: an element that no global refers to is collected
# after its cell runs, and its clicks are silently dropped. Views built here are kept alive per
# (session runtime, cell) until that cell runs again.
_KEEP = {}


def _retain(view):
    try:
        from marimo._runtime.context import get_context
        context = get_context()
        execution = context.execution_context
    except Exception:
        return view
    if execution is None:
        return view
    for key in [key for key, (alive, _) in _KEEP.items() if alive() is None]:
        del _KEEP[key]
    _, cells = _KEEP.setdefault(id(context), (weakref.ref(context), {}))
    run, views = cells.get(execution.cell_id, (None, []))
    if run is not execution:
        views = []
    views.append(view)
    cells[execution.cell_id] = (execution, views)
    return view


def local_time(iso):
    """'2026-10-24 23:17:33' in the viewer's local zone from a stored UTC ISO timestamp."""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return str(iso)


def _clock():
    return datetime.now().astimezone().strftime('%H:%M:%S')


def output_box(mo, text, *, pretty_json=False):
    """Full text in a wrapping, scrollable box (long lines wrap instead of being cut off at the card edge).

    pretty_json indents lines that are JSON objects, which is what the lab's probes print."""
    if pretty_json:
        lines = []
        for line in text.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                lines.append(line)
                continue
            lines.append(json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else line)
        text = '\n'.join(lines)
    return mo.Html('<pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:28rem;overflow:auto;'
                   'margin:0;padding:0.5rem 0.75rem;border:1px solid rgba(127,127,127,0.35);border-radius:6px;'
                   f'font-size:0.85em">{escape(text)}</pre>')


def need_token(mo):
    return mo.callout(mo.md(NEED_TOKEN), kind='warn')


# ---- sidebar / header ------------------------------------------------------------------

def token_state(mo):
    """(get_token, set_token): starts at the newest learning record, or None."""
    tokens = course_progress.list_tokens()
    return mo.state(tokens[0] if tokens else None, allow_self_loops=True)


def chapter_todo(progress, chapter):
    """What this chapter still needs before the sidebar shows ✓ (required tasks, then a perfect quiz)."""
    from notebook_views import NO_QUIZ
    data = ((progress or {}).get('chapters') or {}).get(chapter) or {}
    tasks = data.get('tasks') or {}
    missing = ['任務 ' + task.split('-', 1)[0] for task in chapter_entry(chapter)[3] if not (tasks.get(task) or {}).get('passed')]
    quiz = data.get('quiz')
    if chapter not in NO_QUIZ and not (quiz and quiz['correct'] == quiz['total']):
        missing.append('小測驗全對' if quiz else '小測驗（按「對答案」並全對）')
    return missing


def sidebar(mo, chapter, get_token, set_token, *graded):
    """`graded` are the chapter's task/quiz view getters: passing them makes the sidebar re-render (and its ✓／●
    marks update) right after a 「檢查」 or 「對答案」, instead of only on the next page load."""
    for getter in graded:
        getter()
    token = get_token()
    progress = None
    if token:
        try:
            progress = course_progress.load(token)
        except (OSError, ValueError):
            progress = None
    tokens = course_progress.list_tokens()

    def create(_):
        new = course_progress.start()
        set_token(new)
        return new

    items = [navigation(mo, chapter, progress), mo.md('---\n**學習紀錄**')]
    if tokens:
        items.append(mo.ui.dropdown(tokens, value=token if token in tokens else None, label='使用中的紀錄',
                                    on_change=lambda value: set_token(value) if value else None, full_width=True))
    items.append(mo.ui.button(label='開始新的學習紀錄', kind='success', on_click=create, full_width=True))
    if token:
        missing = chapter_todo(progress, chapter)
        items.append(mo.md('**本章**：' + ('✓ 完成' if not missing else '還差 ' + '、'.join(missing))))
        items.append(mo.md(f'目前：`{token}`\n\n你的檔案、終端紀錄與進度都在主機 `shared/course/{token}/`'
                           f'（節點裡是 `{course_progress.container_dir(token)}`）。'))
    else:
        items.append(mo.md('還沒有學習紀錄：按上面的按鈕開始。'))
    return _retain(mo.sidebar(mo.vstack(items), width=300))


def header(mo, chapter, *, learn, before):
    _, title, minutes, _ = chapter_entry(chapter)
    lines = [f'# {title}', f'⏱ 約 {minutes} 分鐘', '### 你會學到'] + [f'- {item}' for item in learn]
    lines += ['### 開始前'] + [f'- {item}' for item in before]
    return mo.md('\n'.join(lines)).callout(kind='neutral')


# ---- animated diagrams ----------------------------------------------------------------

def diagram_state(mo):
    """One per diagram, in the chapter's state cell: None = autoplay, k = static step k."""
    return mo.state(None, allow_self_loops=True)


def animated(mo, diagram, get_step, set_step):
    step = get_step()
    total = len(diagram.steps)

    def move(delta):
        def click(_):
            set_step(lambda current: (0 if delta > 0 else total - 1) if current is None
                     else max(0, min(total - 1, current + delta)))
        return click

    switch = mo.ui.switch(value=step is None, label='自動播放', on_change=lambda on: set_step(None if on else 0))
    previous = mo.ui.button(label='◀ 上一步', on_click=move(-1), disabled=step == 0)
    following = mo.ui.button(label='下一步 ▶', on_click=move(1), disabled=step == total - 1)
    where = '自動播放中（每步約 2.5 秒）' if step is None else f'第 {step + 1}／{total} 步'
    if step is None:
        caption = mo.md('\n'.join(f'{i}. **{s.caption}** — {s.detail}' for i, s in enumerate(diagram.steps, 1))).callout(kind='info')
    else:
        current = diagram.steps[step]
        caption = mo.md(f'**{step + 1}. {current.caption}**\n\n{current.detail}').callout(kind='info')
    return _retain(mo.vstack([
        mo.md(f'### {diagram.title}'),
        mo.hstack([switch, previous, following, mo.md(f'**{where}**')], justify='start', align='center', gap=1),
        mo.Html(diagram.render(step)),
        caption,
    ]))


# ---- demos ------------------------------------------------------------------------------

def demo_refresh(mo):
    return mo.ui.refresh(options=['3s', '10s'], default_interval='3s', label='狀態自動更新')


def actions_state(mo):
    """Chapter-wide demo state: a click counter and the confirmation phrases the backend has received."""
    return mo.state({'tick': 0, 'typed': {}}, allow_self_loops=True)


def demo_controls(mo, lessons, runs, token, actions, set_actions):
    """Stable buttons for every demo step plus verify/cleanup, keyed '<lesson chapter>:<action>'.

    Re-created only after an explicit action (the actions state) or when lesson_states() notices that a
    background action finished (a step became consumed, or the run is no longer busy); never by the
    auto-refresh itself, so a refresh never drops a click.
    """
    controls = {BUILT: {}}
    for lesson in lessons:
        run_id = runs.get(lesson['chapter'])
        if not run_id:
            continue
        busy = course_runner.busy(run_id)
        consumed = _consumed(run_id)
        controls[BUILT][lesson['chapter']] = (consumed, bool(busy))

        def click(action, lesson=lesson, run_id=run_id):
            def handler(_):
                key = f"{lesson['chapter']}:{action}"
                status, message = course_runner.start(lesson, run_id, action, typed=actions['typed'].get(key, ''))
                mo.status.toast({'started': '已送出', 'busy': '還在忙', 'blocked': '未執行'}[status], message,
                                kind=None if status == 'started' else 'danger')
                set_actions(lambda value: {**value, 'tick': value['tick'] + 1})
            return handler

        for step_id, step in lesson['steps'].items():
            key = f"{lesson['chapter']}:{step_id}"
            phrase = lesson.get('confirmations', {}).get(step_id)
            confirmed = not phrase or actions['typed'].get(key) == phrase
            controls[key] = mo.ui.button(label=lesson['labels'].get(step_id, step_id), on_click=click(step_id),
                                         disabled=step_id in consumed or bool(busy) or not confirmed,
                                         kind='danger' if phrase or step.effect == 'cancel' else 'neutral')
            if phrase:
                controls[key + ':confirm'] = mo.ui.text(
                    value=actions['typed'].get(key, ''), placeholder=phrase, label=f'輸入 {phrase} 後按 Enter 解鎖',
                    disabled=step_id in consumed,
                    on_change=lambda value, key=key: set_actions(lambda v: {**v, 'typed': {**v['typed'], key: value}}))
        controls[f"{lesson['chapter']}:verify"] = mo.ui.button(label='驗證並保存', kind='success', on_click=click('verify'),
                                                               disabled=bool(busy))
        controls[f"{lesson['chapter']}:cleanup"] = mo.ui.button(label='只清理本次實驗', kind='danger', on_click=click('cleanup'),
                                                                disabled=bool(busy))

        def renew(_, lesson=lesson, run_id=run_id):
            course_runner.reset_run(lesson, token)
            set_actions(lambda value: {**value, 'tick': value['tick'] + 1})

        if token:
            controls[f"{lesson['chapter']}:renew"] = mo.ui.button(label='重新開始示範（建立新的 run）', on_click=renew,
                                                                  disabled=bool(busy))
    return controls


BUILT = '__built__'


def _consumed(run_id):
    try:
        return frozenset(r['step_id'] for r in course_runner.lab.saved_receipts(run_id))
    except (OSError, ValueError):
        return frozenset()


def annotate(argv):
    """Bullet lines explaining the recognisable parts of a command."""
    text = shlex.join(argv)
    notes, seen = [], set()
    for prefix, meaning in ANNOTATIONS:
        if ' ' in prefix:
            hit = prefix in text
            shown = prefix
        else:
            matches = [arg for arg in argv if arg == prefix or arg.startswith(prefix + '=') or (prefix.endswith('=') and arg.startswith(prefix))]
            hit, shown = bool(matches), (matches[0] if matches else prefix)
        if hit and meaning not in seen:
            seen.add(meaning)
            notes.append(f'- `{shown if len(shown) < 70 else shown[:67] + "…"}` — {meaning}')
    if argv and 'python' in argv[0].rsplit('/', 1)[-1]:
        notes.insert(0, '- 這一步在主機上執行教材的輔助程式（例如寫入 release 標記檔、準備 CSV），不經過 Slurm')
    return '\n'.join(notes)


def _event(mo, run_id):
    event = course_runner.last_event(run_id)
    if not event:
        return None
    status = event.get('status', 'unknown')
    parts = [f"**最近動作**：{event['label']} → **{course_runner.EVENT_TEXT.get(status, status)}**"]
    if event.get('job_id'):
        parts.append(f"JobID `{event['job_id']}`")
    if event.get('finished_at'):
        parts.append(f"{event['finished_at']} 結束")
    elif event.get('submitted_at'):
        parts.append(f"{event['submitted_at']} 送出（最長 {event.get('timeout', '?')} 秒）")
    message = event.get('reason') or event.get('error') or ''
    if event.get('cleanup_errors'):
        message = '；'.join(event['cleanup_errors'])
    kind = {'succeeded': 'success', 'passed': 'success', 'submitted': 'info', 'blocked': 'warn'}.get(
        status, 'danger' if status in {'failed', 'unknown'} else 'info')
    return mo.md(' · '.join(parts) + (f'\n\n{message}' if message else '')).callout(kind=kind)


def demo(mo, lesson, run_id, step_id, controls, states, *, what, why, watch, expect=()):
    """One demo card: what/why/where to look, the real command with annotations, button, status, output."""
    key = f"{lesson['chapter']}:{step_id}"
    info = (states or {}).get(step_id)
    parts = [mo.md(f'### {what}\n\n**為什麼：** {why}\n\n**看哪裡：** {watch}')]
    if info and info.get('argv'):
        parts.append(mo.md('**指令**\n\n```bash\n' + shlex.join(info['argv']) + '\n```\n\n' + annotate(info['argv'])))
    phrase = lesson.get('confirmations', {}).get(step_id)
    if phrase and key + ':confirm' in controls:
        parts.append(mo.hstack([controls[key + ':confirm']], justify='start'))
    if key in controls:
        parts.append(mo.hstack([controls[key]], justify='start'))
    if info:
        parts.append(mo.md(f"**狀態：【{info['state']}】** {info['badge']} — {info['detail']}").callout(kind=STATE_KIND[info['state']]))
        if info.get('timeline'):
            parts.append(mo.md(info['timeline']))
        receipt = info.get('receipt') or {}
        outputs = []
        if receipt.get('stdout', '').strip():
            outputs.append(('指令的 stdout' + ('（sbatch 回傳的 JobID）' if receipt.get('effect') == 'submit' else ''), receipt['stdout']))
        if receipt.get('stderr', '').strip():
            outputs.append(('指令的 stderr', receipt['stderr']))
        for log in info.get('outputs') or []:
            if (log['text'] or '').strip():
                outputs.append((f"工作輸出 {log['name']}" + ('（只顯示最後 64 KiB）' if log.get('truncated') else ''), log['text']))
        # Plain blocks, not an accordion: this card re-renders every refresh and would re-collapse what you opened.
        for title, text in outputs:
            parts.append(mo.vstack([mo.md(f'**{title}**'), output_box(mo, text, pretty_json=True)], gap=0.25))
    elif states is None:
        parts.append(mo.md('狀態讀取中…'))
    if expect:
        parts.append(mo.md('**你應該看到**\n\n' + '\n'.join(f'- {item}' for item in expect)))
    return mo.callout(mo.vstack(parts), kind='neutral')


def lesson_states(lessons, runs, controls=None, set_actions=None):
    """{lesson chapter: step_states} — one scheduler read per lesson per refresh.

    When the buttons in `controls` were built before a background action finished, ask the controls cell to
    rebuild them (so a consumed step disables and a finished run re-enables verify/cleanup)."""
    result, stale = {}, False
    for lesson in lessons:
        run_id = runs.get(lesson['chapter'])
        if run_id:
            try:
                result[lesson['chapter']] = course_runner.step_states(lesson, run_id)
            except (OSError, ValueError) as exc:
                result[lesson['chapter']] = {'_error': str(exc)}
            built = (controls or {}).get(BUILT, {}).get(lesson['chapter'])
            if built is not None and built != (_consumed(run_id), bool(course_runner.busy(run_id))):
                stale = True
    if stale and set_actions is not None:
        set_actions(lambda value: {**value, 'tick': value['tick'] + 1})
    return result


def ensure_runs(lessons, token):
    return {lesson['chapter']: course_runner.ensure_run(lesson, token) for lesson in lessons} if token else {}


def queue_table(mo, title='我的工作（隨狀態自動更新）'):
    argv = compose_argv('squeue', '--me', '--format=%i|%j|%T|%M|%l|%R')
    try:
        result = run_command(argv, cwd=ROOT, timeout=5)
        lines = [line.split('|') for line in result.stdout.splitlines() if line.strip()]
        rows = [dict(zip(lines[0], line)) for line in lines[1:]] if lines else []
        view = ((mo.ui.table(rows, selection=None) if rows else
                 mo.md('目前沒有你的工作在 queue 中（已結束的工作不會出現在 squeue）。'))
                if result.returncode == 0 else mo.md(result.stderr).callout(kind='danger'))
    except Exception as exc:
        view = mo.md(f'查詢失敗：{exc}').callout(kind='danger')
    return mo.vstack([mo.md(f'**{title}** · `squeue --me --format=%i|%j|%T|%M|%l|%R` · {_clock()}'), view])


# ---- terminal / editor / tasks / quiz ------------------------------------------------

def view_state(mo, value=None):
    """Generic widget state for terminal, editor, task and quiz view cells."""
    return mo.state(value, allow_self_loops=True)


def terminal(mo, token, get_view, set_view, *, mode='user', suggestions=()):
    if not token:
        return need_token(mo)
    view = get_view() or {}
    if view.get('token') != token:
        view = {'token': token, 'cleared': 0}

    def run(value):
        line = (value or '').strip()
        if not line:
            return
        course_terminal.execute(token, line, mode=mode)
        set_view(lambda current: {**(current or view), 'token': token, 'tick': (current or {}).get('tick', 0) + 1})

    def clear(_):
        set_view({**view, 'cleared': len(course_terminal.transcript(token))})

    form = mo.ui.text(placeholder='輸入指令後按「執行」（或 Ctrl＋Enter），例如 squeue --me', full_width=True).form(
        submit_button_label='執行', bordered=False, clear_on_submit=True, on_change=run)
    entries = course_terminal.transcript(token)[view.get('cleared', 0):][-20:]
    shown = []
    for entry in entries:
        head = f"$ {entry['command']}"
        if entry.get('denied'):
            shown.append(mo.md(f"`{head}`\n\n⛔ {entry['denied']}").callout(kind='danger'))
            continue
        body = (entry.get('stdout') or '') + (('\n' if entry.get('stdout') else '') + entry['stderr'] if entry.get('stderr') else '')
        status = '' if entry.get('returncode') == 0 else f"（結束碼 {entry.get('returncode')}）"
        block = mo.vstack([mo.md(f'`{head}` {status}'), output_box(mo, body or '（沒有輸出）')])
        shown.append(block if entry.get('returncode') == 0 else mo.callout(block, kind='warn'))
    tips = ('**可以直接複製的指令**（`<JobID>` 換成你的數字）：\n\n' + '\n'.join(f'- `{s}`' for s in suggestions)) if suggestions else ''
    note = (f'工作目錄固定在 `{course_progress.container_dir(token)}`；以 **lab** 身分在 controller 執行（等於登入節點）。'
            '不支援管線 `|`、重導向 `>`、`;` 與 `$(…)`。')
    return _retain(mo.vstack([
        mo.md('### 迷你終端\n' + note),
        mo.md(tips) if tips else mo.md(''),
        form,
        mo.vstack(shown) if shown else mo.md('（還沒有輸出）'),
        mo.ui.button(label='清除畫面（不刪紀錄）', on_click=clear),
    ]))


def file_editor(mo, token, name, get_view, set_view, *, language, template, note):
    if not token:
        return need_token(mo)
    saved = course_files.read_file(token, name)
    editor = mo.ui.code_editor(value=saved if saved is not None else template, language=language, min_height=200,
                               label=f'`{name}`')
    view = get_view() or {}

    def save(_):
        try:
            size = course_files.write_file(token, name, editor.value)
            set_view({'message': f'已儲存 {_clock()}，{size} bytes', 'ok': True})
        except (OSError, ValueError) as exc:
            set_view({'message': f'儲存失敗：{exc}', 'ok': False})

    status = view.get('message') or ('尚未儲存：目前顯示的是範本' if saved is None else '這是已儲存的內容')
    return _retain(mo.vstack([
        mo.md(f'### 編輯 `{name}`\n{note}'),
        editor,
        mo.hstack([mo.ui.button(label=f'儲存到 shared/course/{token}/{name}', kind='success', on_click=save),
                   mo.md(status)], justify='start', align='center'),
    ]))


def task(mo, token, chapter, task_id, get_view, set_view, *, title, steps_md, check=None, ask=None):
    """A practice task card. check(value) → verdict; default course_tasks.check. `ask` labels an input field (e.g. 'JobID')."""
    if not token:
        return need_token(mo)
    view = get_view() or {}
    field = mo.ui.text(value=view.get('input', ''), label=ask, placeholder='例如 123') if ask else None

    def run(_):
        value = field.value.strip() if field is not None else None
        try:
            verdict = (check or (lambda v: course_tasks.check(chapter, task_id, token, v)))(value)
        except Exception as exc:
            verdict = {'passed': False, 'pending': False, 'advice': None,
                       'items': [{'項目': '檢查', '結果': '✗', '說明': f'{type(exc).__name__}: {exc}'}]}
        if not verdict.get('pending'):
            course_progress.mark_task(token, chapter, task_id, verdict)
        set_view({'verdict': verdict, 'input': value or '', 'at': _clock()})

    saved = ((course_progress.load(token)['chapters'].get(chapter) or {}).get('tasks') or {}).get(task_id)
    parts = [mo.md(f'### 任務 {title}\n\n{steps_md}')]
    if saved and saved.get('passed'):
        parts.append(mo.md(f"✓ 已通過（{local_time(saved['at'])}）").callout(kind='success'))
    controls = [field] if field is not None else []
    parts.append(mo.hstack(controls + [mo.ui.button(label='檢查', kind='success', on_click=run)], justify='start', align='end'))
    verdict = view.get('verdict')
    if verdict:
        parts.append(result_table(mo, verdict['items'], title=f"檢查結果（{view.get('at')}）"))
        if verdict.get('pending'):
            parts.append(mo.md('還沒結束，稍後再按一次「檢查」。').callout(kind='info'))
        elif verdict['passed']:
            parts.append(mo.md('通過！').callout(kind='success'))
        else:
            hints = [i['說明'] for i in verdict['items'] if i['結果'] == '✗']
            parts.append(mo.md('**下一步**：' + (hints[0] if hints else '依上表修正後再檢查')).callout(kind='warn'))
        advice = verdict.get('advice')
        if advice and advice.get('text'):
            parts.append(mo.md(f"**建議**：{advice['text']}").callout(kind='info'))
    return _retain(mo.callout(mo.vstack(parts), kind='neutral'))


def quiz(mo, token, chapter, questions, get_view, set_view, *, key='quiz', title='小測驗'):
    if not token:
        return need_token(mo)
    view = get_view() or {}
    chosen = dict(view.get('chosen') or {})

    def plain(text):
        return text.replace('`', '')  # radio labels are not Markdown; keep code spans readable

    radios = {q['id']: mo.ui.radio(options={plain(option): index for index, option in enumerate(q['options'])},
                                   label=f"**{i}. {q['prompt']}**",
                                   value=plain(q['options'][chosen[q['id']]]) if chosen.get(q['id']) is not None else None)
              for i, q in enumerate(questions, 1)}
    answers = mo.ui.dictionary(radios)

    def check(_):
        values = answers.value
        picked = {q['id']: values.get(q['id']) if isinstance(values.get(q['id']), int) else None for q in questions}
        result = course_quiz.grade(questions, picked)
        course_progress.mark_quiz(token, chapter, result, key=key)
        set_view({'chosen': picked, 'result': result})

    parts = [mo.md(f'## {title}'), mo.vstack([answers[q['id']] for q in questions]),
             mo.ui.button(label='對答案', kind='success', on_click=check)]
    result = view.get('result')
    if result:
        for i, item in enumerate(result['items'], 1):
            question = next(q for q in questions if q['id'] == item['id'])
            mine = question['options'][item['chosen']] if item['chosen'] is not None else '（未作答）'
            mark = '✓' if item['correct'] else '✗'
            parts.append(mo.md(f"{mark} **{i}.** 你的答案：{mine}" + ('' if item['correct'] else f"；正確答案：{question['options'][item['answer']]}")
                               + f"\n\n{item['explain']}").callout(kind='success' if item['correct'] else 'danger'))
        if result['correct'] == result['total']:
            parts.append(mo.md(f"🎉 本章{title}通過（{result['correct']}／{result['total']}）").callout(kind='success'))
        else:
            parts.append(mo.md(f"{result['correct']}／{result['total']} 題正確；看完解釋後改答案再按一次「對答案」。").callout(kind='warn'))
    return _retain(mo.vstack(parts))


# ---- closing ----------------------------------------------------------------------------

CLOSING_WHY = """## 收尾
離開本章前做三件事：

1. **驗證並保存**：核對這次示範的證據（JobID、狀態、輸出）並寫進 `report.json`，結果是 passed／failed。
2. **只清理本次實驗**：只取消這次示範自己的工作、恢復這次 DRAIN 的節點、刪掉這次建立的 account；不碰別人的東西。
3. **清理不會刪證據**：receipt、輸出檔與報告都留在 `shared/demos/<run>/`，之後仍可回來看。

清理後如果想再做一次示範，按「重新開始示範」會建立新的 run。"""


def closing_actions(mo, lessons, runs, controls):
    """Verify / cleanup / renew buttons per lesson with the latest event and report status."""
    parts = [mo.md(CLOSING_WHY)]
    for lesson in lessons:
        run_id = runs.get(lesson['chapter'])
        if not run_id:
            continue
        info = course_runner.report(run_id)
        prefix = lesson['chapter']
        buttons = [controls[f'{prefix}:{name}'] for name in ('verify', 'cleanup', 'renew') if f'{prefix}:{name}' in controls]
        status = f"Report **{info.get('status')}** · " + ('已清理' if info.get('cleaned') else '尚未清理')
        verified = bool(info.get('verification'))
        if not info.get('acted'):
            hint = '還沒按過任何示範按鈕，不需要收尾。'
        elif not verified:
            hint = ('**下一步：按「驗證並保存」**。它會核對這次示範的證據並把結果（passed／failed）寫進報告；'
                    '清理只取消工作、不做驗證。工作結束後約 1 小時內（`MinJobAge`）都還能補按，超過就查不到排程紀錄了。')
        elif info.get('status') == 'running':
            hint = '驗證結果是 running：還有步驟沒做，或還有工作沒結束。做完、等工作結束後再按一次「驗證並保存」。'
        elif not info.get('cleaned'):
            hint = '**下一步：按「只清理本次實驗」**。'
        else:
            hint = '這次示範已驗證並清理完成。'
        parts.append(mo.callout(mo.vstack([mo.md(f"### {lesson['title']} · run `{run_id}`\n{status}\n\n{hint}"),
                                           mo.hstack(buttons, justify='start'), _event(mo, run_id) or mo.md('')]),
                                kind='success' if info.get('cleaned') and info.get('status') == 'passed'
                                else 'warn' if info.get('acted') and not verified else 'neutral'))
    return _retain(mo.vstack(parts))


def recheck_button(mo):
    return mo.ui.button(label='重新檢查收尾', value=0, on_click=lambda count: (count or 0) + 1)


def closing(mo, chapter, recheck_value):
    """The read-only closing checklist plus the next-chapter link (re-runs when 重新檢查收尾 is pressed)."""
    return mo.vstack([closing_panel(mo, chapter, recheck_value), next_chapter_link(mo, chapter)])


def course_map(mo, progress):
    from notebook_views import chapter_mark
    lines = ['| 狀態 | 章 | 時間 |', '| :---: | :--- | ---: |']
    for name, title, minutes, _ in CHAPTERS:
        lines.append(f'| {chapter_mark(progress, name[:2])} | [{title}](/?file={name}) | {minutes} 分 |')
    return mo.md('\n'.join(lines) + '\n\n✓ 完成（任務全過＋測驗全對）　● 進行中　○ 未開始')


# ---- scheduler simulator ---------------------------------------------------------------

CUSTOM = '自訂：三個節點，從空的開始'


def simulator_state(mo, preset='先來先服務／回填', backfill=False):
    return mo.state({'preset': preset, 'backfill': backfill, 'extra': []}, allow_self_loops=True)


def simulator(mo, get_sim, set_sim):
    """Preset or custom queue → schedule() → Gantt chart and placement table."""
    import course_sim
    sim = get_sim()
    jobs, nodes = course_sim.PRESETS.get(sim['preset'], ([], course_sim.NODES))
    extra = [course_sim.Job(**job) for job in sim['extra']]
    all_jobs = list(jobs) + extra
    placements = course_sim.schedule(all_jobs, backfill=sim['backfill'], nodes=nodes)
    preset = mo.ui.dropdown([*course_sim.PRESETS, CUSTOM], value=sim['preset'], label='情境',
                            on_change=lambda value: set_sim({**sim, 'preset': value, 'extra': []}))
    backfill = mo.ui.switch(value=sim['backfill'], label='開啟回填 backfill',
                            on_change=lambda value: set_sim({**sim, 'backfill': value}))
    cpus = mo.ui.number(start=1, stop=4, step=1, value=1, label='CPU')
    minutes = mo.ui.number(start=1, stop=10, step=1, value=2, label='分鐘')
    partition = mo.ui.dropdown(['cpu', 'gpu'], value='cpu', label='partition')
    gpus = mo.ui.dropdown(['0', '1'], value='0', label='GPU')

    def add(_):
        name = f'J{len(sim["extra"]) + 1}'
        job = {'id': name, 'cpus': int(cpus.value), 'minutes': int(minutes.value),
               'gpus': int(gpus.value), 'partition': partition.value}
        set_sim({**sim, 'extra': [*sim['extra'], job]})

    rows = []
    for job, place in zip(all_jobs, placements):
        rows.append({'工作': job.id, '要求': f'{job.cpus} CPU' + (f'＋{job.gpus} GPU' if job.gpus else '') + f'，{job.minutes} 分，{job.partition}',
                     '節點': place.node or '—', '開始': '—' if place.start is None else place.start,
                     '結束': '—' if place.end is None else place.end, 't=0 的 Reason': place.reason or '（立刻開始）'})
    nodes_text = '、'.join(f"{name}（{spec['cpus']} CPU{'、' + str(spec['gpus']) + ' GPU' if spec['gpus'] else ''}）"
                           for name, spec in nodes.items())
    return _retain(mo.vstack([
        mo.md(f'**模擬的節點**：{nodes_text}。時間以分鐘計；工作依提交順序排隊。'),
        mo.hstack([preset, backfill], justify='start', align='center', gap=2),
        mo.hstack([cpus, minutes, partition, gpus,
                   mo.ui.button(label='加入一個 job', on_click=add),
                   mo.ui.button(label='清空加入的 job', on_click=lambda _: set_sim({**sim, 'extra': []}))],
                  justify='start', align='end', gap=1),
        mo.Html(course_sim.gantt_svg(placements, nodes=nodes)),
        mo.ui.table(rows, selection=None, pagination=False),
    ]))
