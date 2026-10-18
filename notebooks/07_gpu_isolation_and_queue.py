import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="07｜GPU 裝置隔離、排隊與取消")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_gpu import get_lesson

    lesson = get_lesson('07-gpu-isolation')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 07｜GPU 裝置隔離、排隊與取消

    **目標：**分別證明「看得到裝置名稱不等於有權限」、「CPU 節點根本沒有裝置」
    與「GPU 配額會讓第二個 job 等待」。最後必須證明 Slurm 取消第一個容器程序後，
    第二個容器能完成真實 CUDA 計算，而不是只看到 queue 清空。

    ## 第一階段：隔離證據（尚未啟動 holder）
    表單選本叢集的 `gpu01`，提交參數後明確建立 run。依序按前四個按鈕：
    1. 直接 Slurm job **不申請 GRES**，即使設定 `CUDA_VISIBLE_DEVICES=0`，
       `os.open('/dev/nvidia0', O_RDWR)` 仍須收到 **EPERM 或 EACCES**。
    2. 容器 job 也不申請 GRES，明確掛入 `/dev/nvidia0` 路徑，
       `NVIDIA_VISIBLE_DEVICES=void` 避免 runtime 以隱藏路徑掩蓋 cgroup 行為。
       同樣必須是 UID 1000 的 EPERM/EACCES，**ENOENT 不算權限隔離證明**。
    3. cpu01、cpu02 各提交一個 job，輸出對應 hostname 與 `gpu_device_absent=true`。
       這兩份證據說的是「裝置不存在」，與上面「存在但拒絕存取」不同。

    前四份工作必須 COMPLETED 且 exit code 為零才能建立 holder。程式把「符合預期的
    裝置拒絕」判為成功；並不是任意 FAILED 都算成功。可先刷新讀輸出，再開始計時階段。

    ## 第二階段：120 秒有限操作窗口
    5. 按「提交 GPU 容器 holder」。它申請 **1 CPU、1 GPU、512 MiB RAM**，
       先驗算全部 **65539** 個 vector-add 元素，再印出 **GPU_HELD**，最多持有 120 秒。
       batch 有額外啟動時間上限，並非無限暫停；頁面顯示依 StartTime 推估的保守剩餘秒數。
    6. 只讀刷新至 holder **RUNNING 且 GPU_HELD 已出現**，再按提交第二個 GPU job。
       按鈕即時重新查核；預覽或點擊時會從 gpu01 外層執行最多 5 秒的唯讀 root probe，
       保存 holder 的 **PID/starttime、SLURM_JOB_SLUID 所屬 cgroup、512 MiB memory.max**。
       容器內 `/proc/self/cgroup` 顯示 `/` 不能取代這份外層證據。
    7. 刷新直到第二個 job **PENDING，Reason=Resources 或 Priority**，再按取消本次 holder。
       取消前會再次確認 holder 仍 RUNNING、GPU_HELD 存在、PID/starttime 未變，
       並把 PENDING 與 cgroup 證據持久化。保守窗口不足 10 秒便拒絕繼續：
       請清理並新建 run，不會暗中重建 holder。
    8. holder 必須變成 **CANCELLED**，第二個 job 必須 **COMPLETED**。
       按「驗證並保存」會檢查原 PID/starttime 不再是 live 程序（PID 被重用不會誤判），
       並核對第二個 job 的全部 CUDA 元素、UID 1000、單 CPU affinity、獨立 image identity、
       GPU 型號及 job ID。最後按「只清理本次實驗」。

    若 holder 自然睡完或 TIMEOUT、尚未看見 PENDING 就清理、原程序仍活著、
    waiter 沒有通過 CUDA 驗算，都不能通過本章。僅看到 `nvidia-smi` 或 queue 空白不足以驗證。

    ## 限制與安全
    GRES 的排他只限 Slurm jobs；主機桌面／Ollama 不受此 queue 管理，不能用整卡利用率
    推論某個 job 的專屬負載。`--mem` 是 RAM 而非 VRAM，這不是 GPU 顯存切分實驗。
    NVIDIA_VISIBLE_DEVICES/CUDA_VISIBLE_DEVICES 不能授權；本課特意測試它們無法繞過 cgroup。
    程式只有既定 argv；root 只用來讀 gpu01 的單一 PID/cgroup，沒有任意 shell 輸入。

    ## 診斷、重開與清理
    先查 JobState/Reason/ExitCode，再查本次 stdout/stderr。若容器 image 缺失或 CUDA driver
    失敗，保留錯誤，不使用 CPU fallback。若第二個 job 已 RUNNING，代表 holder 已釋放或
    未取得預期資源，本章不能以「最後都完成」冒充排隊證據。若 root probe 失敗，先檢查
    gpu01 與 PID 是否仍在，而不是放寬驗證。

    刷新、表單與頁面重載沒有提交副作用；既有 run 可從選單恢復，每步 claim 只能消耗一次。
    關閉瀏覽器不會取消 holder。unknown receipt 請先人工核對唯一名稱、UID、工作目錄與時間，
    不自動重送或收編。清理只取消本次精確 owned IDs，保留報告，不掃殺其他人工作。
    scheduler 紀錄過期或缺失不能視為成功；需建立新 run 重做完整順序。

    下方提供實際 argv、公開 CUDA/source、輸出下載與逐案例 CLI；CLI 驗收在清理後於終端執行，
    不在頁面 callback 同步執行 smoke suite。
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
