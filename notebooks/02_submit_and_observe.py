import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="02 提交與觀察")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_cpu import get_lesson
    lesson = get_lesson('02-submit')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md("""
    ## 目標：把 allocation、job 與 task 分清楚
    選擇 cpu01／cpu02、1／4 CPU；RAM 固定 **128 MiB**。先提交參數，再「建立實驗」，參數即凍結。
    兩個獨立按鈕分別執行短 `srun --immediate=5` 與公開 `cpu.sbatch`，不是執行 smoke 套件。
    `srun` 在 callback 同步執行，上限 15 秒；batch 只取得 job ID，不等待完成。

    ### 觀察與驗證
    重新整理只讀狀態，查看實際 argv、job ID、scheduler exit code 與 probe JSON。
    兩條路徑均須 COMPLETED／exit 0，UID=1000、hostname 為所選節點、affinity 為申請的 CPU 數且落在節點 cpuset，`sum=50005000`。
    `cpu_probe.py` 在 Slurm task step 內執行；job allocation 與 srun step 不是兩次獨立 batch 提交。
    單執行緒 Python 加總**不會**因申請四 CPU 自動平行或變快。

    ### 診斷與清理
    PENDING 先看 Reason、節點與資源；非零 exit 再看 stdout/stderr。查不到紀錄不等於成功。
    全部完成後按「驗證並保存」，再「只清理本次實驗」。重開頁可載入原 run；不會重送。
    已消耗的失敗或 unknown 步驟不能重試，請先核對唯一 job name，必要時清理後建立新 run。
    終端獨立驗收：`python3 scripts/smoke.py --case cpu-affinity`；執行前先結束 notebook jobs。
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
