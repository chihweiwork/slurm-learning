import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="09｜取消、限時與三代程序清理")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_lifecycle import get_lesson
    lesson = get_lesson('09-lifecycle')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 09｜取消與限時：Job 結束之後，後代程序真的消失了嗎？

    **目標**：分別在兩個獨立 run 中觀察手動取消與自然超時。
    同一個 `cpu_probe.py descendants` 建立 parent、child、grandchild 三代程序，
    各自保存 **PID + `/proc/PID/stat` starttime + hostname + role**。
    只看到工作離開 queue 不代表清理完成，也不能把 PID 被重用誤判成殘留程序。

    ## 先選模式，再建立 run
    參數一經建立即凍結；要改模式請完成／清理後建立另一個 run。
    提交三代程序工作後按只讀刷新，確認 `RUNNING`，並在輸出看到三個不同 PID、
    三個角色和 starttime。每個程序最多存活 180 秒，不提供無限 holder。

    ### `cancel`：真正的取消
    等三代 marker 都寫好後，按「僅 cancel 模式：確認三代存活後取消」。
    按鈕在 claim 前使用 cpu01 外層的 root **只讀** `check-processes` 確認三代同時存活，
    然後僅執行 `scancel <本次 descendants job ID>`。預期狀態為 `CANCELLED`。
    如果三代已自然結束，不會把晚到的取消偽裝為本章成功。

    ### `timeout`：真正的一分鐘限時
    提交 argv 使用 `--time=00:01:00`；**不要按取消，也不要用 cleanup 代替 TIMEOUT**。
    本模式的取消按鈕會被前置條件阻擋。觀察 marker 後讓 Slurm 自然到期，
    等到 `TIMEOUT`。驗證同時要求 scheduler 的 start→end 至少 60 秒，
    不能用手動取消得到的 `CANCELLED` 冒充。

    ## 兩種模式共同的最後兩步
    1. 按「確認相同 PID/starttime 已消失並重用四 CPU」。
       它重新核對預期終態，讀取恰好三筆 marker，並在 cpu01 檢查 `/proc`。
       必須 `record_count=3`、`live=[]` 才提交四 CPU exclusive 的 affinity 工作。
       Zombie 不算 live；PID 相同但 starttime 改變代表不同程序。
    2. 重用工作完成、UID 1000、cpu01 四 CPU affinity、`sum=50005000`、ExitCode 0，
       再按「驗證並保存」及「只清理本次實驗」。兩種模式須各保存自己的 report。

    ## 診斷與界線
    - 只收到兩筆 marker：等待後刷新，不要猜第三代已存在。
    - 工作已結束但 `live` 尚未清空：讓 Slurm 的清理完成，再按步驟；不自行掃殺 PID。
    - `FAILED`、`NODE_FAIL`、缺失 scheduler 記錄都不是預期的取消／限時成功。
    - 完成前關頁不會取消。可由既有 run 選單恢復並清理，重載不會重送工作。
    - 不操作其他使用者的 jobs；不要使用 `pkill`、`scancel --all` 或重啟 compute
      來「修好」驗證結果。root 診斷只檢查本次 marker 對應的三筆身分。

    **獨立終端驗收**（先清理 notebook 工作）：
    ```bash
    python3 scripts/smoke.py --case cancellation-descendant-cleanup
    python3 scripts/smoke.py --case time-limit-descendant-cleanup
    ```
    下方提供凍結參數的實際 argv、共用 probe 原始碼及每個步驟的 receipt。
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
