"""Stable Chapter 03 controls with independent, small reactive outputs."""
import notebook_lab as lab
from environment_view import _terminal
from lesson_common import receipt
from notebook_views import table_rows
from queue_view import job_rows, sample_queue


STEPS = {
    'holder': ('1．啟動 A，讓它先取得資源',
               'cpu01 可分配 4 CPU，A 申請全部 4 CPU 與 128 MiB RAM。'
               '它輸出 `started: true` 後等待，最多 10 分鐘；保留資源不代表 CPU 一直滿載。'
               '按下後查看提交回應，再到步驟 2 確認 A 已啟動。'),
    'waiter': ('2．確認 A 已啟動，再提交 B',
               '先按「查看目前 A／B 狀態」，確認 A RUNNING 且已輸出 started，再按「提交工作 B」。'
               '若 A 還沒準備好，提交會被擋下，可以稍後再按，不會消耗提交機會。'
               'B 申請 cpu01 的 1 CPU、128 MiB RAM；A 已拿走全部 4 CPU，沒有剩餘 CPU 可分配，B 只能排隊，不能改派到 cpu02。'
               'B 啟動後計算加總，再保留資源 60 秒，方便你觀察 RUNNING。'),
    'before': ('3．先看 queue：A 在跑，B 在等',
               '按「查看取消前的 queue」保存取樣。預期 A RUNNING、B PENDING，等待原因為 Resources 或 Priority。'
               '必須先查到這份證據，才能執行下一步取消；若尚未就緒，等幾秒再按本段按鈕。'),
    'cancel-holder': ('4．取消 A，把資源讓給 B',
               '按「取消工作 A，釋出資源」，執行 `scancel A的JobID`。'
               '這會取消 A 與其工作步驟，不必等到時間上限。操作前會重新核對 A／B 的身分與目前排隊狀態。'
               '你以 lab 使用者取消自己提交的 A，不需要管理員權限。'),
    'after': ('5．再看 queue：B 取得資源開始跑',
               '取消 A 後按「查看取消後的 queue」。A 可能先經過 COMPLETING，B 也可能短暫維持 PENDING；隔幾秒可以再按。'
               '預期 B 變成 RUNNING，約 60 秒後 COMPLETED。結束的工作會從 squeue 消失；'
               '結果下方另外顯示 Slurm 保留紀錄，A 應為 CANCELLED，B 最後為 COMPLETED。'),
}


def queue_controls(mo, lesson, run_id):
    """Create once per run. Callbacks update only their own result state.

    No rendering cell for these buttons reads these states or the shared event.
    Permissions/readiness are rechecked on click, never inferred from button color.
    """
    getters, setters, buttons = {}, {}, {}
    initial = {}
    if run_id:
        try:
            initial = lab.read_run(run_id)
        except Exception:
            pass  # Each click reports its own fresh query error below.
    for key in (*STEPS, 'status', 'results'):
        previous = receipt(initial, key) if initial.get('receipts') and key in lesson['steps'] else None
        getters[key], setters[key] = mo.state(previous)

    def action(step_id):
        def callback(_):
            try:
                if step_id == 'cancel-holder':
                    before = getters['before']() or {}
                    # Repeated clicks return the durable receipt instead of resubmitting.
                    data = lab.read_run(run_id)
                    if not receipt(data, step_id) and not (before.get('ready') and before.get('run_id') == run_id):
                        setters[step_id]({'status': 'blocked', 'reason': '先在步驟 3 查到 A RUNNING、B PENDING 的 queue。'})
                        return
                run = lab.load_run(run_id)
                step = lesson['steps'][step_id]
                result = lab.execute_once(run_id, step_id, step.argv(run), effect=step.effect)
            except Exception as exc:
                result = {'status': 'failed', 'error': str(exc)}
            setters[step_id](result)
        return callback

    def observe(key):
        def callback(_):
            try:
                data = lab.read_run(run_id)
                if key == 'before' and receipt(data, 'cancel-holder'):
                    # Keep the historical before sample when this button is pressed late.
                    previous = getters['before']()
                    notice = 'A 已執行過取消；取消前取樣保留不變，請使用步驟 5。'
                    setters[key]({**previous, 'notice': notice} if previous else {'error': notice})
                    return
                if key == 'after' and not (receipt(data, 'cancel-holder') or {}).get('status') == 'succeeded':
                    setters[key]({'error': '先在步驟 4 成功取消 A，再查看取消後的 queue。'})
                    return
                sample = sample_queue(run_id)
                setters[key]({**sample, 'run_id': run_id})
            except Exception as exc:
                # A failed query replaces only this result, never the other snapshot.
                setters[key]({'error': str(exc)})
        return callback

    def status(_):
        try:
            data = lab.read_run(run_id)
            setters['status']({'rows': job_rows(data), 'observed_at': data.get('observed_at'),
                               'holder_ready': _holder_ready(data)})
        except Exception as exc:
            setters['status']({'error': str(exc)})

    for key in STEPS:
        label = lesson['labels'][key] if key in lesson['steps'] else (
            '查看取消前的 queue' if key == 'before' else '查看取消後的 queue')
        buttons[key] = mo.ui.button(label=label, disabled=not run_id,
                                    on_click=action(key) if key in lesson['steps'] else observe(key))
    buttons['status'] = mo.ui.button(label='查看目前 A／B 狀態', disabled=not run_id, on_click=status)
    buttons['results'] = mo.ui.button(label='更新輸出與驗證報告', disabled=not run_id,
                                      on_click=lambda _: setters['results'](lambda value: (value or 0) + 1))
    return {'buttons': buttons, 'getters': getters}


def _holder_ready(data):
    from lessons_cpu import _holder
    from lesson_common import Pending
    try:
        _holder(data)
    except (AssertionError, ValueError, KeyError, Pending):
        return False
    return True


def step_heading(mo, step_id, button, *, leading_button=None):
    title, explanation = STEPS[step_id]
    return mo.vstack([mo.md(f'## {title}\n\n{explanation}'),
                       *([] if leading_button is None else [leading_button]), button])


def action_result(mo, step_id, result):
    if not result:
        return mo.md('尚未操作。')
    panels = [mo.plain_text('操作結果：' + result.get('status', '未確認') + ' · ' + str(
        result.get('reason') or result.get('error') or
        ('Job ID：' + str(result['job_id']) if result.get('job_id') else '指令已返回，請查看工作狀態。')))]
    if result.get('argv'):
        panels.append(_terminal(mo, 'scancel / 取消 A' if step_id == 'cancel-holder' else 'sbatch / 提交工作', result,
                                 note='提交成功不代表工作完成；重按同一提交按鈕只會讀回原紀錄，不會建立新工作。'))
    return mo.vstack(panels)


def snapshot_result(mo, key, sample):
    if not sample:
        return mo.md('尚未取樣；按上方本段的 queue 按鈕查詢。')
    if sample.get('error'):
        return mo.plain_text('查詢未完成：' + sample['error'])
    panels = [mo.plain_text('取樣時間：' + sample['observed_at']),
              _terminal(mo, 'squeue / ' + ('取消前' if key == 'before' else '取消後'), sample['command'],
                        note='只查本次 A／B 的 Job ID。下表另外查詢 scontrol 保留紀錄，兩次查詢之間狀態可能改變。'),
              mo.ui.table(table_rows(sample['rows']), selection=None)]
    if sample.get('notice'):
        panels.append(mo.plain_text(sample['notice']))
    if key == 'before':
        panels.append(mo.plain_text('已確認 A RUNNING、B PENDING，可以進入步驟 4。' if sample['ready']
                                     else '尚未確認排隊證據；等幾秒再按本段 queue 按鈕，並查看狀態與等待原因。'))
    return mo.vstack(panels)


def status_result(mo, result):
    if not result:
        return mo.md('按「查看目前 A／B 狀態」確認 A 是否已啟動。')
    if result.get('error'):
        return mo.plain_text('查詢未完成：' + result['error'])
    return mo.vstack([mo.plain_text('查詢時間：' + str(result['observed_at'])),
                       mo.ui.table(table_rows(result['rows']), selection=None),
                       mo.plain_text('A 已 RUNNING 且有 started 輸出，可以提交 B。' if result['holder_ready']
                                     else 'A 目前未處於已確認啟動的 RUNNING 狀態；若剛提交，等幾秒再查一次。')])
