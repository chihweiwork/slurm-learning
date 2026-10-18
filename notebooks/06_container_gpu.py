import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="06｜獨立容器與真實 CUDA 計算")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, status_panel
    from lessons_gpu import get_lesson

    lesson = get_lesson('06-container-gpu')
    return action_controls, lesson, mo, setup_controls, status_panel


@app.cell
def _(mo):
    mo.md(r"""
    # 06｜獨立容器與真實 CUDA 計算

    **目標：**比較同一份 CUDA Driver API vector-add 在直接 Slurm job 與獨立
    OCI job image 內的執行證據；不是用 `nvidia-smi` 顯示卡名就算通過。

    ## 操作順序與參數
    1. 確認 Dashboard 沒有其他人的 active jobs，GPU image 已由既有準備流程建立。
       表單固定本叢集的 `gpu01`；兩種計算都申請 **1 CPU、1 GPU、512 MiB RAM**。
       表單提交只保存候選參數，再按「建立實驗」凍結本 run。
    2. 按「提交直接 CUDA 計算」，以只讀刷新觀察 job 從 PENDING/RUNNING 到 COMPLETED。
    3. 按「提交公開 container-gpu.sbatch」，讀下方實際 argv 與公開腳本原文。
       可以比較兩份輸出的 `gpu_environment`、`gpu_device`、`gpu_compute` JSON。
    4. 兩份工作完成後按「驗證並保存」，再按「只清理本次實驗」。
       按鈕不執行完整 smoke suite，也不在 callback 等待 batch 完成。

    ## 應看到的結果
    - 兩份 `gpu_compute` 都必須 `status=PASS`、`elements=verified_elements=65539`，
      且 `kernel_launched=true`、`synchronized=true`；元素數刻意不是 block 大小的倍數。
      CUDA 初始化／kernel／任何一個元素驗算失敗都是失敗，**沒有 CPU fallback**。
    - `gpu_environment.uid=1000`、affinity 只有一個 CPU，且屬於此叢集允許的
      `{4,5,12,13}`；`SLURM_JOB_ID` 必須與本次提交 ID 相同。
    - 直接版 `image=null` 且 cgroup 有 `slurmstepd`；容器版 image name 必須是
      `slurm-lab-gpu-job`，Python 位於 `/usr/local/bin/python…`。
      `gpu_device` 顯示真實型號與恰好一個可見裝置，不寫死特定顯示卡型號。
    - 兩個 retained job 都必須 COMPLETED 且 exit code/signal 為零。
      缺輸出、unknown receipt、已過期 scheduler 紀錄都不會補成成功。

    ## 容器與資源語意
    Pyxis/Enroot 執行 `/shared/images/gpu-job.sqsh`，不是在 job 裡啟動 Docker daemon，
    也不掛 Docker socket。公開腳本明確設定環境與命令，因為 Docker export 不保留
    image 的 ENV/CMD/ENTRYPOINT 執行語意。容器內 cgroup 顯示 `/` 可能是 namespace
    視圖，不能據此宣稱逃離 Slurm；下一章會從 gpu01 外層查 PID/cgroup。

    `--gres=gpu:1` 才是 Slurm 配額；可見裝置環境變數不是授權。
    `--mem=512M` 限制 **RAM，不是 VRAM**。本機只有一張實體卡，主機桌面與 Ollama
    仍可能使用它；GPU 利用率既非本 job 專屬，也不能替代數值驗算或效能保證。

    ## 診斷與復原
    先看 JobState/Reason/ExitCode，再看本次 stdout/stderr；缺 image、Pyxis/Enroot
    錯誤、libcuda 載入失敗或 CUDA driver 錯誤均保留原證據，不能改跑 CPU 掩蓋。
    Resources/Priority 表示等待，不代表 kernel 壞掉。重開頁面可選回既有 run，
    刷新、改參數及讀 source 不會提交；已消耗步驟不能重試，需建立新 run。
    unknown 表示提交結果未確認，先人工核對唯一 job name、UID、工作目錄及時間，
    不要重送。關閉頁面不會 scancel；清理只處理本次精確 owned IDs 並保留報告。

    下方列出可複製的實際命令、完整 source 與獨立終端驗收 CLI。
    終端驗收須在 notebook jobs 清理後執行，結果與 UI 的實驗報告分開保存。
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
