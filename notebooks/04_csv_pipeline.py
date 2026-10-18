import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="04 CSV 資料管線")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_cpu import get_lesson
    lesson = get_lesson('04-csv')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md("""
    ## 目標：真實 CSV array、afterok 與局部修復
    選擇 `success` 或 `failure-recovery` 並**分別建立獨立 run**；模式凍結後不能在同 run 切換。
    資料為四片各 1000 筆，id=1..4000、value=2*id。公開 pipeline.py 與兩個 sbatch 共用同一 workload；不使用替代 mock。

    ### 成功路徑
    準備四片 CSV → 提交 worker array `0-3%2` → 提交依賴整個 array parent 的 afterok aggregate。
    刷新至四個 task 與 aggregate 完成；查看實際輸入、partials 與 summary。
    預期 `shards=4`、`row_count=4000`、`value_sum=16004000`。每片 partial 也以封閉公式檢查。

    ### 壞輸入與修復路徑（不可跳步）
    準備 → 備份 shard 2 → 注入非數字 → array → afterok aggregate。
    等待 shard 2 FAILED、其他三片 COMPLETED；原 aggregate 保留 PENDING Dependency／DependencyNeverSatisfied，summary 不存在。
    接著明確執行「缺片 aggregate（無 dependency）」：它也必須 FAILED、非零退出，不能產生 summary。
    按「保存失敗證據並取消原 dependent」後，等待 CANCELLED，再還原輸入。
    只重送 `--array=2`，最後提交依賴修復工作的全新 aggregate。三個原本成功的 partial 不可重寫；最終總和與成功路徑一致。

    ### 觀察、診斷與清理
    sbatch 成功只是接受提交，不是 pipeline 完成。看每個 task 的 exit code、stderr、dependency 與缺片結果；任何 FAILED 都不是自動 PASS。
    UI 顯示的 argv 與公開 source 可複製；輸入／partial／summary 都保存在本次 `pipeline/`，不是臨時假資料。
    完成後按「驗證並保存」，再「只清理本次實驗」；不會刪除結果。重新開頁可載入同 run，不重送。
    獨立驗收：`python3 scripts/smoke.py --case csv-pipeline-success --case csv-pipeline-failure-recovery`。
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
