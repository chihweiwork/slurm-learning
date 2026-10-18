import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="11｜Controller 重啟與證據復原")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_lifecycle import get_lesson
    lesson = get_lesson('11-recovery')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 11｜Controller 重啟：保存的狀態與仍在執行的程序

    **目標**：真正重啟本專案 controller，分別證明 completed 輸出、running StartTime
    與 pending waiter 都保留。控制器不是計算程序所在處；**本章不重啟 compute**。
    單一 Docker 主機上的多個節點不是跨實體機器的高可用叢集。

    ## 操作順序與 240 秒窗口
    1. 建立 run，提交 cpu02 基準計算，刷新並等待 `COMPLETED`、`sum=50005000`。
    2. 啟動 cpu01 四 CPU exclusive holder，`--seconds=240`、Slurm 上限五分鐘。
       等 `RUNNING`、`started: true`；頁面顯示的剩餘窗口只供操作，不能延長 holder。
    3. 提交 cpu01 waiter，等 `PENDING`、Reason `Resources` 或 `Priority`，且尚無輸出。
    4. 輸入 **`RESTART controller`**，按「保存證據並重啟 controller」。
       動作前 claim 保存 completed 全部已知輸出、active 的 StartTime、pending 狀態。
       只執行 `docker compose restart controller`，最長 90 秒，不在 callback 等待 readiness。
    5. 只讀刷新觀察 controller 恢復。短暫失聯應顯示 error/stale，而非把舊資料當新資料。
       按「查核狀態保存後釋放 holder」時會重新確認：
       **active 仍 RUNNING 且 StartTime 完全不變、completed 輸出逐字相同、waiter 仍 PENDING**。
       三者都成立且 holder 未過期，才寫 release marker。
    6. 等 holder 收到 release 並成功完成、waiter 成功完成、三個 compute 節點恢復健康，
       按「驗證並保存」，再「只清理本次實驗」。

    holder 過期、缺失 job 記錄或 restart 結果不確定都不能算通過。
    清理後建立新 run，不能重放已消耗的 restart step。重新開頁只讀取舊 receipt，
    不會重新提交、重啟或自動取消。

    ## 故障復原按鈕
    如果本次 restart 後 controller 無法查詢，輸入 **`RESTORE controller`** 再按
    「故障復原：啟動 controller」，執行：
    ```bash
    docker compose up -d --no-build controller
    ```
    只恢復 controller，不重建映像、不啟動其他服務。控制器正常時不需要此操作。
    若按鈕回報 unknown，先查 Compose 與 daemon logs，不把不確定性當成重試授權。
    ping 正常後才處理 owned jobs 與本次 DRAIN。
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Runbook｜先證據、再最小範圍復原

    ### 1. JobState / Reason / ExitCode
    所有指令在專案根目錄執行。先看完整 active queue；有外來工作時不做新實驗或干擾性維護。
    `JOB_ID` 請換成本次 report／receipt 中的精確數字，**不要猜 ID 或依使用者掃殺**。
    ```bash
    docker compose ps
    docker compose exec -T -u lab controller scontrol ping
    docker compose exec -T -u lab controller squeue --all --array --long
    docker compose exec -T -u lab controller scontrol show job JOB_ID -o
    ```
    - `Resources` / `Priority`：查有效 CPU、memory/GRES 配置與前面的 holder；本章 release
      是正常解法，不用重啟 scheduler。
    - `Dependency` / `DependencyNeverSatisfied`：查前置 job ExitCode；第 04 章示範修復 shard，
      只重送失敗片與新的 aggregate，不重跑已成功工作。
    - `ReqNodeNotAvail` / DRAIN：查節點 Reason，只有本次精確 Reason 才可恢復。
    - `FAILED` / `OUT_OF_MEMORY`：查 stderr、128 MiB `memory.max` 與 `memory.events.oom_kill`。
      第 08 章的 kernel event 才能證明 OOM；不是任何 FAILED 都是 OOM。
    - `TIMEOUT`：比對 TimeLimit、StartTime/EndTime，再以第 09 章的 PID/starttime 證明清理。
    - 缺 GRES：第 07 章須在存在的 `/dev/nvidia*` 上看到 `EPERM` / `EACCES`；`ENOENT`
      只證明裝置不存在。`CUDA_VISIBLE_DEVICES` 不提供授權，申請 RAM 也不等於 VRAM 配額。

    ### 2. 讀 stdout/stderr 與身分
    由本頁下方本次已登記輸出讀取，不開放任意主機檔案瀏覽。檢查 job name、UID 1000、
    working directory、SubmitTime 與 receipt，避免叢集重設後數字 ID 重用。
    完整輸出可下載；預覽最多末 64 KiB，截斷會明示。
    沒有檔案、記錄過期、JSON 損壞、query error 要分開處理，不可補成 COMPLETED。

    ### 3. 節點與 daemon logs
    ```bash
    docker compose exec -T -u lab controller sinfo -Nel
    docker compose exec -T -u lab controller scontrol show nodes -o
    docker compose logs --no-color --tail=100 controller
    docker compose exec -T -u root cpu01 journalctl -u slurmd -u munge --no-pager -n 100
    docker compose exec -T -u root cpu02 journalctl -u slurmd -u munge --no-pager -n 100
    docker compose exec -T -u root gpu01 journalctl -u slurmd -u munge --no-pager -n 100
    ```
    controller 直接啟動 slurmctld，因此用 **Compose logs**，不是查不存在的 controller
    systemd slurmctld unit。compute 才查 slurmd/MUNGE journal。
    CPU 判讀看 `CPUEfctv` 與配置，不把 `CPUTot=16` 當成每個節點都可排程 16 CPU。

    ### 4. 只恢復本次所有資源
    優先用頁面的「恢復 controller」與「只清理本次實驗」，它們在動作前重新核對所有權。
    UI 無法使用時，先 ping 正常，再人工核對本次 claim/receipt：
    ```bash
    # 僅在本次 controller restart 故障且明確確認後：
    docker compose up -d --no-build controller
    docker compose exec -T -u lab controller scontrol ping
    # 核對精確 owned ID、name、UID、workdir、SubmitTime 後才可取消：
    docker compose exec -T -u lab controller scancel JOB_ID
    # 僅 cpu02 Reason 完全等於本次 demo-<run-id> 才可恢復：
    docker compose exec -T -u root controller scontrol update NodeName=cpu02 State=RESUME
    ```
    若 Reason 被另一位維護者改變，停止並保留現況，不盲目 RESUME。
    外部工作加入不授權你取消它；不要用 `scancel --all`、user/partition 掃殺、
    `docker system prune`、`docker compose down --volumes`，也不要停止 Ollama。

    ### 5. unknown receipt／中斷後人工核對
    每個固定 step 在外部命令前建立 exclusive claim。若 process 被殺死、連線中斷或提交逾時，
    claim 沒有成功 receipt 就是 **unknown**，不是「未提交」。以該 claim 的唯一
    `demo-<run-id>-<step-id>` job name 找候選，再核對 UID、working directory、提交時間與 ID。
    多個或不明候選需人工處理，不能自動認領或重新按提交。不要刪除 claim 來強制重試。
    保留現有 report 與輸出，確定 owned job 已結束後才開新 run。

    ### 6. 哪些資料會留下？
    - `controller-state` volume 保存 scheduler 狀態，使 controller 重啟後能找回 jobs；
      不是永久的 accounting 資料庫。
    - MUNGE volume 保存認證材料；不要重建或分享 key。
    - `shared/` 保存本次 `run.json`、claims、receipts、`report.json`、工作輸出與 markers。
      清理只回收 owned scheduler 資源，不刪除證據。
    - compute 上的程序不在 controller 中。**重啟 compute 會失去該節點正在執行的程序**，
      不能用本章的 controller restart 結果宣稱 compute restart 也無損。
    - 沒有 slurmdbd/MariaDB；`MinJobAge=3600` 不是永久歷史。查不到 retained record
      時顯示未知，只有已保存的證據可追溯，不能憑空補時間或成功狀態。

    **獨立終端驗收**（清理所有 notebook 工作並恢復節點後）：
    ```bash
    python3 scripts/smoke.py --case controller-restart-persistence
    ```
    本頁所有變更都由明確按鈕執行；刷新、表單、切頁與讀程式碼不會重啟或提交。
    下方提供本次實際 argv、共用 probe 原始碼與動作前後證據。
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
