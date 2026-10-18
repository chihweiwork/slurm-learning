import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="10｜DRAIN 排空與 RESUME")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_lifecycle import get_lesson
    lesson = get_lesson('10-drain')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 10｜DRAIN：拒絕新工作，不殺既有工作

    **目標**：在 cpu02 先建立執行中的 holder，觀察 DRAIN 不會殺死它；
    holder 結束後，新 waiter 仍不能啟動，直到明確 RESUME。
    單看「有工作 PENDING」不足以證明 DRAIN：它也可能只是在等 CPU。

    ## 嚴格依序執行
    1. 建立 run，提交 cpu02 **四 CPU exclusive holder**，等 `RUNNING`、`started: true`。
       holder 操作窗口 **180 秒**，Slurm 上限四分鐘；過期未完成請清理後開新 run。
    2. 確認 cpu02 原先沒有 DRAIN，再輸入 **`DRAIN cpu02`** 並按危險動作。
       claim 保存原節點狀態、holder 身分與本次 `Reason=demo-<run-id>`。
    3. holder 在 DRAIN 後仍需保持 RUNNING，才可提交 waiter。
       只讀刷新看到 waiter `PENDING`、Reason，且沒有執行輸出。
    4. 按「保存等待證據並釋放 holder」。此時重新核對 holder 未過期、waiter 仍等待、
       cpu02 的 Reason 仍屬本次 run，才寫 release marker。
    5. 等 holder `COMPLETED` 並輸出 `released: true`。**此刻必須再看到 waiter PENDING**，
       即使四 CPU 已空出，DRAIN 仍阻擋新工作。
    6. 輸入 **`RESUME cpu02`**，按 RESUME。此動作保存「holder 已完成、waiter 仍等待」的
       claim 證據後才恢復節點。等 waiter 完成、cpu02 UID 1000、`sum=50005000`、
       零退出碼，再「驗證並保存」與「只清理本次實驗」。

    ## 預期狀態與原因
    DRAIN 可與 ALLOCATED/MIXED/IDLE 等狀態並列，不必只等某個精確顯示字串。
    waiter 可能先呈現 `Resources`／`Priority`，排空後常見 `ReqNodeNotAvail`；
    畫面保留實際 Reason，不把所有 PENDING 都說成相同原因。
    驗證要求動作順序與具體證據：DRAIN 前 holder 已活、DRAIN 後仍活、
    release 後 holder 真正完成、RESUME 前 waiter 還沒執行、RESUME 後才完成。

    ## 診斷與安全復原
    預先已 DRAIN 的節點屬於別的維護者，本章拒絕接管。若操作中 Reason 被改成別人的，
    後續 RESUME 與 cleanup 都不得盲目恢復；保留狀態與錯誤，先與管理者核對。
    正常中止時使用「只清理本次實驗」，取消精確 owned ID，且只恢復 Reason 仍屬本次的 cpu02。
    即使外部 job 後來加入，仍可清理自己的資源，但不能清場。
    關頁不是 cleanup；重開後選回原 run。禁止 `scancel --all`、全域 Docker prune、
    `down --volumes` 或為此重啟其他服務。

    **獨立終端驗收**（先清理 notebook，節點恢復後）：
    ```bash
    python3 scripts/smoke.py --case drain-resume
    ```
    下方提供本次實際 argv、共用 holder 程式碼，以及保存的動作前後證據。
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
