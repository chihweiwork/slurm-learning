import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="03 資源與排隊")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_cpu import get_lesson
    lesson = get_lesson('03-queue')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md("""
    ## 目標：真正觀察資源競爭，而不是瞬間完成的工作
    本章固定 cpu01：四 CPU exclusive holder → RUNNING／started marker → waiter → PENDING → release → 兩工作完成。
    holder 最多 **180 秒**，batch 限時四分鐘；畫面可由開始時間判斷剩餘操作窗口，過期即須重新建立 run，不能跳過排隊證據。

    ### 操作順序與必要證據
    1. 建立實驗，提交 holder；只讀刷新至 RUNNING 且輸出 `started: true`。
    2. 提交公開 `cpu.sbatch` waiter。確認 PENDING Reason 為 Resources 或 Priority。
    3. 按「保存 PENDING 證據並釋放 holder」；按鈕會重新查詢並把兩工作狀態保存在 action receipt，然後建立本次 release marker。
    4. 刷新直到兩者 COMPLETED。holder 必須輸出 `released: true`，不是自然過期；waiter 必須算出 50005000。
    驗證亦檢查 UID、job ID、cpu01 hostname 與四／一 CPU affinity。

    ### 診斷、限制與復原
    沒有 RUNNING 或沒有 PENDING 證據時不允許釋放；過期 holder 不會自動重建。
    查看實際 argv、公開腳本、Reason 與 stderr。這是排程資源限制，不是主機負載或效能 benchmark。
    關閉頁面不會取消 holder；重新載入 run 後可按「只清理本次實驗」，只取消本次 ID，不清場。
    完成後「驗證並保存」，再清理。獨立驗收：`python3 scripts/smoke.py --case resource-queue-release`。
    """)
    return


@app.cell
def _(lesson, mo, setup_controls):
    setup = setup_controls(mo, lesson)
    get_run = setup['get_run']
    get_event = setup['get_event']
    set_event = setup['set_event']
    refresh = setup['refresh']
    setup['view']
    return get_event, get_run, refresh, set_event


@app.cell
def _(action_controls, get_event, get_run, lesson, mo, refresh, set_event):
    get_event()
    refresh.value
    run_id = get_run()
    actions = action_controls(mo, lesson, run_id, set_event)
    actions
    return (run_id,)


@app.cell
def _(get_event, lesson, mo, refresh, run_id, status_panel):
    refresh.value
    event = get_event()
    status_panel(mo, lesson, run_id, event)
    return


if __name__ == "__main__":
    app.run()
