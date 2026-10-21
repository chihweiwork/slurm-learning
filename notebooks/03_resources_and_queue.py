import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="03 多個工作與資源排隊")


@app.cell
def _():
    import marimo as mo
    from environment_view import TERMINAL_CSS
    from lesson_ui import setup_controls, verification_controls
    from lessons_cpu import get_lesson
    from queue_interaction import queue_controls, step_heading, action_result, snapshot_result, status_result
    from queue_view import results_panel
    lesson = get_lesson('03-queue')
    return TERMINAL_CSS, action_result, lesson, mo, queue_controls, results_panel, setup_controls, snapshot_result, status_result, step_heading, verification_controls


@app.cell
def _(TERMINAL_CSS, mo):
    mo.vstack([mo.Html(TERMINAL_CSS), mo.md("""
    # 03 多個工作共享資源：A 先執行，B 為什麼要排隊？

    這一章同時有 **A 與 B 兩個工作**，都想使用 cpu01。資源有限，A 尚未釋放資源，B 就需要排隊。

    **啟動 A → 提交 B → 看 queue → 取消 A → 再看 queue。**

    | 工作 | 需求 | 觀察目標 |
    | --- | --- | --- |
    | A（holder） | cpu01、4 CPU、128 MiB RAM | 先取得並保留全部 4 CPU，最多等待 10 分鐘 |
    | B（waiter） | cpu01、1 CPU、128 MiB RAM | 先排隊；A 被取消後取得資源，啟動並保留約 60 秒供觀察 |

    cpu01 可分配 4 CPU，A 已申請全部 4 CPU，B 要的額外 1 CPU 就必須等 A 釋放資源。
    兩個工作都指定 cpu01，所以 cpu02 即使空閒也無法接手。保留 CPU 不代表它一直滿載。
    先清理前一章工作，再建立本章實驗。每個按鈕只更新自己下方的結果；說明與其他 queue 取樣保留。
    操作時機尚未就緒時，按鈕會在下方顯示原因，並阻止提交或取消。
    黑底區塊顯示實際指令與輸出；只有按鈕會執行操作，不需要重新整理瀏覽器。
    """)])
    return


@app.cell
def _(lesson, mo, setup_controls):
    setup = setup_controls(mo, lesson)
    get_run = setup['get_run']
    get_event = setup['get_event']
    set_event = setup['set_event']
    refresh = setup['refresh']
    parameter_form = setup['form']
    restore_run_menu = setup['restore_menu']
    setup['view']
    return get_event, get_run, parameter_form, refresh, restore_run_menu, set_event


@app.cell
def _(get_run):
    run_id = get_run()
    return (run_id,)


@app.cell
def _(mo, run_id):
    mo.md(f'### 目前實驗：`{run_id}`\n\n固定使用 cpu01，從下方步驟 1 開始。' if run_id else
          '先按上方「套用參數並建立實驗」。')
    return


@app.cell
def _(lesson, mo, queue_controls, run_id):
    _controls = queue_controls(mo, lesson, run_id)
    start_a_button = _controls['buttons']['holder']
    submit_b_button = _controls['buttons']['waiter']
    before_queue_button = _controls['buttons']['before']
    cancel_a_button = _controls['buttons']['cancel-holder']
    after_queue_button = _controls['buttons']['after']
    queue_refresh_button = _controls['buttons']['status']
    output_refresh_button = _controls['buttons']['results']
    get_a_result = _controls['getters']['holder']
    get_b_result = _controls['getters']['waiter']
    get_before_result = _controls['getters']['before']
    get_cancel_result = _controls['getters']['cancel-holder']
    get_after_result = _controls['getters']['after']
    get_status_result = _controls['getters']['status']
    get_output_refresh = _controls['getters']['results']
    return after_queue_button, before_queue_button, cancel_a_button, get_a_result, get_after_result, get_b_result, get_before_result, get_cancel_result, get_output_refresh, get_status_result, output_refresh_button, queue_refresh_button, start_a_button, submit_b_button


@app.cell
def _(mo, start_a_button, step_heading):
    step_heading(mo, 'holder', start_a_button)
    return


@app.cell
def _(action_result, get_a_result, mo):
    action_result(mo, 'holder', get_a_result())
    return


@app.cell
def _(mo, queue_refresh_button, step_heading, submit_b_button):
    step_heading(mo, 'waiter', submit_b_button, leading_button=queue_refresh_button)
    return


@app.cell
def _(get_status_result, mo, status_result):
    status_result(mo, get_status_result())
    return


@app.cell
def _(action_result, get_b_result, mo):
    action_result(mo, 'waiter', get_b_result())
    return


@app.cell
def _(before_queue_button, mo, step_heading):
    step_heading(mo, 'before', before_queue_button)
    return


@app.cell
def _(get_before_result, mo, snapshot_result):
    snapshot_result(mo, 'before', get_before_result())
    return


@app.cell
def _(cancel_a_button, mo, step_heading):
    step_heading(mo, 'cancel-holder', cancel_a_button)
    return


@app.cell
def _(action_result, get_cancel_result, mo):
    action_result(mo, 'cancel-holder', get_cancel_result())
    return


@app.cell
def _(after_queue_button, mo, step_heading):
    step_heading(mo, 'after', after_queue_button)
    return


@app.cell
def _(get_after_result, mo, snapshot_result):
    snapshot_result(mo, 'after', get_after_result())
    return


@app.cell
def _(mo):
    mo.md("""### queue 欄位怎麼看？

    | 欄位 | 意義 |
    | --- | --- |
    | JOBID | 對照 A／B 的工作編號 |
    | STATE | RUNNING＝執行中；PENDING＝等待；COMPLETING＝正在結束與回收資源 |
    | CPUS | 要求／分配的 CPU 數，不是即時使用率 |
    | TIME | 工作已執行多久；排隊時通常為 0:00 |
    | TIME_LIMIT | 工作時間上限；取消不必等到上限 |
    | NODELIST(REASON) | 執行時是節點；排隊時以括號顯示原因 |

    Resources 表示資源尚未可用；Priority 表示有優先處理的工作。
    A 即使在等待，保留的資源仍然不能分給 B。
    """)
    return


@app.cell
def _(lesson, mo, run_id, set_event, verification_controls):
    _buttons = {}
    _view = verification_controls(mo, lesson, run_id, set_event, buttons=_buttons)
    verify_run_button = _buttons.get('verify')
    cleanup_run_button = _buttons.get('cleanup')
    _view
    return cleanup_run_button, verify_run_button


@app.cell
def _(output_refresh_button):
    output_refresh_button
    return


@app.cell
def _(get_event, get_output_refresh, lesson, mo, refresh, results_panel, run_id):
    refresh.value
    get_output_refresh()
    results_panel(mo, lesson, run_id, get_event())
    return


if __name__ == "__main__":
    app.run()
