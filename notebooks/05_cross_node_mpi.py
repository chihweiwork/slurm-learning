import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="05 跨節點 MPI")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_cpu import get_lesson
    lesson = get_lesson('05-mpi')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md("""
    ## 目標：公開 MPI workload 的雙 rank Allreduce
    建立實驗後提交公開 `mpi.sbatch`。腳本以 mpicc 編譯 mpi_sum.c，再以 `srun --mpi=pmix --cpu-bind=threads` 執行。
    固定兩個 CPU 節點 cpu01／cpu02、兩個 rank、每節點一個 task；不能只在同一 hostname 上跑兩個程序冒充跨節點。

    ### 預期結果與證據
    刷新至 COMPLETED／exit 0，UID=1000。stdout 必須恰有 rank 0、rank 1 各一筆，hostname 集合是 cpu01／cpu02、size=2、sum=3、valid=true。
    每個 rank 提供 rank+1，MPI_Allreduce 讓兩者都取得 1+2=3。
    查看實際提交 argv、公開 sbatch／C source、scheduler job ID 與兩筆 rank JSON，再按「驗證並保存」。

    ### 限制、診斷與清理
    這兩個 Slurm 節點是同主機上的容器，證明通訊與排程拓樸，**不代表跨實體機器效能**。
    Pending 先看兩節點資源；非零退出先看 mpicc／PMIx／srun 的 stderr，缺少任一 rank 不通過。
    僅查不到 retained record 不代表完成。離開頁面不取消工作；載入原 run 可繼續觀察或「只清理本次實驗」。
    完成後驗證並清理。獨立驗收：`python3 scripts/smoke.py --case cross-node-mpi`，先確保 notebook jobs 已結束。
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
