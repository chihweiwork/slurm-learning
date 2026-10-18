import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="08｜記憶體失敗與鄰居隔離")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_lifecycle import get_lesson
    lesson = get_lesson('08-memory')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 08｜記憶體失敗：限制的是工作，不是整台主機

    **目標**：讓一個 `--mem=128M` 的工作真正觸發 Linux cgroup OOM，
    證明同節點的鄰居仍存活，最後以新工作證明資源可重用。
    這裡的記憶體是 **RAM，不是 GPU VRAM**；不是以任意 `FAILED` 當成功。

    ## 操作順序
    1. 提交參數表單後按「建立實驗」。這只建立目錄，不提交工作。
    2. 啟動 cpu01 的鄰居 holder。按只讀刷新，等到 `RUNNING` 與 `started: true`。
       鄰居只申請一個 CPU，操作窗口 **180 秒**；Slurm 上限四分鐘。
    3. 啟動 offender：它最多配置 **256 MiB**，避免把主機當壓力測試目標。
       工作先輸出自身的 affinity 與 cgroup 上限，`srun` 結束後 batch shell 讀取
       `memory.events`，並保留原始非零退出碼。
    4. 等 offender 結束，再按「證明 OOM 與鄰居存活，再釋放鄰居」。
       此按鈕會重新查詢，只有找到 128 MiB cgroup 的 `oom_kill > 0`、swap 上限 0、
       非零 ExitCode，且鄰居仍 `RUNNING`、未逾期時，才寫入 release marker。
    5. 等鄰居 `COMPLETED` 且輸出 `released: true`，提交四 CPU exclusive 的重用工作。
       最後按「驗證並保存」，再「只清理本次實驗」。

    ## 預期證據
    - offender 可以是 `FAILED` 或 `OUT_OF_MEMORY`；有些 Slurm 設定只把 step OOM
      顯示為 batch `FAILED`。**實際 kernel event 與非零退出碼缺一不可**。
    - offender 的最小數值 `memory.max` 是 `134217728`；同層 `memory.swap.max=0`。
    - release claim 保存 OOM 後鄰居仍活的證據，不能用稍早的畫面代替。
    - 重用工作在 cpu01、UID 1000、四 CPU affinity，計算 `sum=50005000` 並以零退出碼完成。

    ## 診斷與限制
    若只有 `FAILED` 而沒有 `oom_kill`，先讀 stdout/stderr、JobState/ExitCode 與 cgroup
    紀錄，不能猜測是 OOM。`unexpected_allocation_success_mib` 表示隔離未得到證實。
    缺檔、記錄過期、鄰居自然逾期或鄰居被取消，都不能通過本章；清理後建立新 run。
    按鈕不等待長工作，使用只讀刷新觀察。重新開頁可載入既有 run，不會重送；
    關閉網頁也不會取消工作。只清理本次 owned ID，不要使用 `scancel --all`。

    **獨立終端驗收**（結束 notebook 工作並清理後）：
    ```bash
    python3 scripts/smoke.py --case memory-oom-isolation
    ```
    下方列出本次凍結參數產生的實際 argv、共用 `cpu_probe.py` 原始碼及保存證據。
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
