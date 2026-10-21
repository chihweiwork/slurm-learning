import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="04 CSV 資料管線與失敗修復")


@app.cell
def _():
    import marimo as mo
    from environment_view import TERMINAL_CSS
    from lesson_ui import setup_controls, verification_controls
    from lessons_cpu import get_lesson
    from csv_view import csv_controls, step_heading, step_result, observation_result, report_panel, source_panel
    lesson = get_lesson('04-csv')
    return TERMINAL_CSS, csv_controls, lesson, mo, observation_result, report_panel, setup_controls, source_panel, step_heading, step_result, verification_controls


@app.cell
def _(TERMINAL_CSS, mo):
    mo.vstack([mo.Html(TERMINAL_CSS), mo.md("""
    # 04 把資料拆成多個工作：分別計算、等待彙總、只修壞掉的一份

    第三章觀察兩個工作怎麼排隊；這一章讓多個工作**共同完成同一項資料處理任務**。
    我們把 4000 筆資料分成四份 CSV，讓 worker 各算一份，最後由 aggregate 合併結果。

    **先做 success 成功路徑，再另建 failure-recovery 實驗練習失敗與局部修復。**

    | 名詞 | 在這個實驗做什麼？ |
    | --- | --- |
    | shard（分片） | 一份 CSV 輸入；編號 0、1、2、3 |
    | worker | 處理一份 CSV，輸出該份的筆數與加總 |
    | job array | 用一次 sbatch 提交同一支腳本的四個 task，以 index 區分輸入 |
    | partial | 一個 worker 的部分結果，寫在 partials/編號.json |
    | aggregate | 讀取四份 partial，合併成 summary.json |
    | afterok | 前置工作全部成功，才允許後面的工作啟動 |

    每個 worker／aggregate 都只申請 **1 CPU、128 MiB RAM**，不使用 GPU，也不指定 cpu01 或 cpu02，
    由 Slurm 選擇可用節點。它們透過共享目錄讀寫同一批資料。
    這些小工作可能在第一次查詢時就已完成；本章重點是資料分工、依賴與修復。
    """)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 選擇這次要走的實驗路徑

    | 模式 | 操作順序 |
    | --- | --- |
    | success | 準備 CSV → 提交四個 worker → 提交 afterok 彙總 → 查看結果 |
    | failure-recovery | 準備／備份 → 弄壞分片 2 → worker → 等待中的彙總 → 確認缺片會失敗 → 取消原彙總 → 還原／只補跑分片 2 → 新彙總 |

    選好模式後按「套用參數並建立實驗」。建立實驗只保存設定；下方會先顯示 stdin 指令與空白 stdout，按鈕才會執行並填入實際回應。
    需要前一步 Job ID 的指令先顯示佔位文字，提交成功後會自動換成真正 ID。
    換模式需要建立新實驗；先清理舊實驗仍在等待的工作。
    """)
    return


@app.cell
def _(lesson, mo, setup_controls):
    setup = setup_controls(mo, lesson)
    get_run = setup['get_run']
    get_event = setup['get_event']
    set_event = setup['set_event']
    parameter_form = setup['form']
    restore_run_menu = setup['restore_menu']
    setup['view']
    return get_event, get_run, parameter_form, restore_run_menu, set_event


@app.cell
def _(get_run):
    run_id = get_run()
    return (run_id,)


@app.cell
def _(csv_controls, lesson, mo, run_id):
    _controls = csv_controls(mo, lesson, run_id)
    csv_mode = _controls['mode']
    csv_setup_error = _controls['setup_error']
    csv_prepare_button = _controls['buttons']['prepare']
    get_prepare_result = _controls['getters']['prepare']
    csv_backup_button = _controls['buttons']['backup']
    get_backup_result = _controls['getters']['backup']
    csv_inject_button = _controls['buttons']['inject']
    get_inject_result = _controls['getters']['inject']
    csv_array_button = _controls['buttons']['array']
    get_array_result = _controls['getters']['array']
    csv_aggregate_button = _controls['buttons']['aggregate']
    get_aggregate_result = _controls['getters']['aggregate']
    csv_missing_aggregate_button = _controls['buttons']['missing-aggregate']
    get_missing_aggregate_result = _controls['getters']['missing-aggregate']
    csv_cancel_dependent_button = _controls['buttons']['cancel-dependent']
    get_cancel_dependent_result = _controls['getters']['cancel-dependent']
    csv_repair_input_button = _controls['buttons']['repair-input']
    get_repair_input_result = _controls['getters']['repair-input']
    csv_repair_shard_button = _controls['buttons']['repair-shard']
    get_repair_shard_result = _controls['getters']['repair-shard']
    csv_aggregate_repaired_button = _controls['buttons']['aggregate-repaired']
    get_aggregate_repaired_result = _controls['getters']['aggregate-repaired']
    csv_initial_button = _controls['buttons']['observe-initial']
    get_initial_snapshot = _controls['getters']['observe-initial']
    csv_final_button = _controls['buttons']['observe-final']
    get_final_snapshot = _controls['getters']['observe-final']
    csv_report_button = _controls['buttons']['report']
    get_report_snapshot = _controls['getters']['report']
    return csv_mode, csv_setup_error, csv_prepare_button, get_prepare_result, csv_backup_button, get_backup_result, csv_inject_button, get_inject_result, csv_array_button, get_array_result, csv_aggregate_button, get_aggregate_result, csv_missing_aggregate_button, get_missing_aggregate_result, csv_cancel_dependent_button, get_cancel_dependent_result, csv_repair_input_button, get_repair_input_result, csv_repair_shard_button, get_repair_shard_result, csv_aggregate_repaired_button, get_aggregate_repaired_result, csv_initial_button, get_initial_snapshot, csv_final_button, get_final_snapshot, csv_report_button, get_report_snapshot


@app.cell
def _(csv_mode, csv_setup_error, mo, run_id):
    _panels = [mo.md(f"### 目前實驗：{csv_mode}\n\n編號：`{run_id}`。模式已保存，從步驟 1 開始；操作時機尚未就緒時，下方會顯示原因並阻止執行。"
                    if csv_mode else "先在上方選擇模式並建立實驗。")]
    if csv_setup_error:
        _panels.append(mo.plain_text('讀取實驗時發生錯誤：' + csv_setup_error))
    mo.vstack(_panels)
    return


@app.cell
def _(csv_prepare_button, csv_mode, mo, step_heading):
    step_heading(mo, 'prepare', csv_mode, csv_prepare_button)
    return


@app.cell
def _(csv_mode, get_prepare_result, lesson, mo, run_id, step_result):
    step_result(mo, 'prepare', csv_mode, get_prepare_result(), lesson, run_id)
    return


@app.cell
def _(csv_backup_button, csv_mode, mo, step_heading):
    step_heading(mo, 'backup', csv_mode, csv_backup_button)
    return


@app.cell
def _(csv_mode, get_backup_result, lesson, mo, run_id, step_result):
    step_result(mo, 'backup', csv_mode, get_backup_result(), lesson, run_id)
    return


@app.cell
def _(csv_inject_button, csv_mode, mo, step_heading):
    step_heading(mo, 'inject', csv_mode, csv_inject_button)
    return


@app.cell
def _(csv_mode, get_inject_result, lesson, mo, run_id, step_result):
    step_result(mo, 'inject', csv_mode, get_inject_result(), lesson, run_id)
    return


@app.cell
def _(csv_mode, mo):
    mo.md(r"""
    ## 一次提交多份計算：用 job array

    前面是一個一個提交工作。現在四份 CSV 都要跑**同一支程式，只換輸入編號**，
    可以用一次 `sbatch --array=0-3%2` 提交四個 array task，不用手動打四次指令。
    Slurm 不會自動切 CSV；本實驗已在準備步驟把資料切成四份。

    ### 提交設定：本章的 sbatch 參數集中在這裡

    先看整行的結構：`Docker 入口 → sbatch 選項 → 腳本 → 傳給腳本的參數`。
    `docker compose exec -T -u lab controller` 是本地實驗的 Docker 入口：
    在 controller 容器裡，以 lab 使用者執行指令，`-T` 不配置互動終端。
    `sbatch` 負責提交；後面的 `/opt/lab/examples/pipeline-worker.sbatch` 是要執行的腳本，
    最後的資料目錄是傳給腳本的第一個參數 `$1`。

    **下面這張表統一查「我要怎麼設定工作」**，包含 worker、彙總與修復用的 sbatch 選項。
    `RUN_DIR` 代稱 `/shared/demos/實驗編號`；`ID` 代稱前置工作的 Job ID。
    「設定位置」對照本實驗：命令列是黑底區塊中看得到的選項，腳本則是檔案裡的 `#SBATCH` 行。
    同一個選項兩邊都有寫時，以命令列為準。

    | 用途分類 | sbatch 選項 | 本實驗的設定位置 | 意義 |
    | --- | --- | --- | --- |
    | 提交回條 | `--parsable` | 命令列 | stdout 回傳方便程式讀取的 Job ID；有些叢集會附上 `;叢集名稱`，不代表工作完成 |
    | 工作辨識 | `--job-name=demo-…-array` | 命令列 | 設定工作名稱，方便查詢；不會指定執行節點 |
    | 路徑 | `--chdir=RUN_DIR` | 命令列 | 設定工作啟動目錄，相對路徑以這裡為基準 |
    | 輸出紀錄 | `--output=RUN_DIR/array-%A_%a.out` | 命令列 | 每個 array task 的 stdout 分開存檔；`%A` 是 array Job ID，`%a` 是 index |
    | 輸出紀錄 | `--error=RUN_DIR/array-%A_%a.err` | 命令列 | 每個 array task 的 stderr 分開存檔；一般非 array 工作改用 `%j` 代表 Job ID |
    | 批量與併發 | `--array=0-3%2` | worker 命令列與腳本 | 四個 array task，index 0 到 3，同時最多兩個；資源不足時可能更少 |
    | 批量與併發 | `--array=2` | 修復命令列 | 新提交只含 index 2；覆蓋 worker 腳本的 `0-3%2`，保留其他三份結果 |
    | 計算資源 | `--partition=cpu` | 腳本 | 從 cpu partition 選擇可用節點 |
    | 計算資源 | `--nodes=1` | 腳本 | 每個 array task 的 allocation 使用一個節點；四份工作可在相同或不同節點 |
    | 計算資源 | `--ntasks=1` | 腳本 | 每份工作配置一個 Slurm task；不決定 array 有幾份，也不會自動切 CSV |
    | 計算資源 | `--cpus-per-task=1` | 腳本 | 每個 Slurm task 申請 1 CPU；兩份 worker 同時執行時，共申請 2 CPU |
    | 計算資源 | `--mem=128M` | 腳本 | 每份工作每節點申請 128 MiB RAM；本章每份只用一個節點，兩份同跑合計 256 MiB |
    | 時間上限 | `--time=00:02:00` | 腳本 | 每份工作的執行上限兩分鐘，不包含排隊時間 |
    | 前後依賴 | `--dependency=afterok:ID` | 彙總命令列 | 前置工作成功才允許啟動；ID 是 array parent 時，必須全部 task 成功。適合彙總完整結果，詳細情境見下方 dependency 說明 |
    | 依賴失敗處理 | `--kill-on-invalid-dep=no` | 彙總命令列 | 依賴不可能成功時保留 PENDING，供本實驗觀察；改成 `yes` 可讓 Slurm 自動取消後續工作 |

    例如四份 worker、同時兩份、每份一核，分別由 `--array` 的範圍、`%2`、`--cpus-per-task` 控制。
    **要處理 100 份輸入、同時最多四份，可以改成 `--array=0-99%4`，並準備對應的資料與 index 處理方式。**
    本實驗只有四份，先保留 `0-3%2`。改成 `--ntasks=4` 不會建立四個 array index 或選擇四份 CSV。

    ### 四個 task 怎麼知道自己要讀哪份 CSV？

    Slurm 會替每個 task 設定 `SLURM_ARRAY_TASK_ID`。公開的 worker 腳本用這個值呼叫 Python：

    ```bash
    srun --cpu-bind=threads python3 /opt/lab/examples/pipeline.py worker \
        --run-dir "$1" --index "$SLURM_ARRAY_TASK_ID"
    ```

    `$1` 是剛剛傳入的資料目錄；`--index` 是 Python 程式自己的參數。
    程式根據 index 選檔案，例如 index 2 就讀 `input/shard-2.csv`，寫出 `partials/2.json`。
    四個 task 的啟動與完成順序不保證照編號排列。

    假設這次 sbatch 回傳的 array Job ID 是 **300**，檔名與工作編號會這樣對應：

    | Array task | 輸入 | 結果 | stdout／stderr |
    | --- | --- | --- | --- |
    | `300_0` | `input/shard-0.csv` | `partials/0.json` | `array-300_0.out`／`array-300_0.err` |
    | `300_1` | `input/shard-1.csv` | `partials/1.json` | `array-300_1.out`／`array-300_1.err` |
    | `300_2` | `input/shard-2.csv` | `partials/2.json` | `array-300_2.out`／`array-300_2.err` |
    | `300_3` | `input/shard-3.csv` | `partials/3.json` | `array-300_3.out`／`array-300_3.err` |

    `%A` 會被 Slurm 換成 array Job ID（300），`%a` 換成 task index（0 到 3）。
    這裡的 300 只是示例；實際編號要看提交後的 stdout。

    官方參考：[Job array](https://slurm.schedmd.com/job_array.html)、[sbatch 選項](https://slurm.schedmd.com/sbatch.html)。
    """) if csv_mode else mo.md('')
    return


@app.cell
def _(csv_array_button, csv_mode, mo, step_heading):
    step_heading(mo, 'array', csv_mode, csv_array_button)
    return


@app.cell
def _(csv_mode, get_array_result, lesson, mo, run_id, step_result):
    step_result(mo, 'array', csv_mode, get_array_result(), lesson, run_id)
    return


@app.cell
def _(csv_mode, mo):
    mo.md("""
    ## dependency：前一步發生什麼事，才讓下一步啟動？

    你可以在 worker 還沒跑完時就提交彙總，讓 Slurm 負責等候，不必守在終端手動接下一步。
    dependency 是提交設定表中的「前後依賴」；這裡比較它的條件與使用情境。
    下表的 ID 都是前置工作的 Job ID；本章彙總使用 array parent ID。

    | 依賴條件 | 什麼時候允許後續工作啟動？ | 適合的情境 |
    | --- | --- | --- |
    | `afterok:ID` | 前置工作成功結束；依賴整個 array 時，所有 task 都要成功 | 完整結果的彙總、訓練成功後才做評估。本章使用這個條件，避免拿缺片資料彙總 |
    | `afterany:ID` | 前置工作結束，成功、失敗或取消都可以 | 收集紀錄、通知結果，或無論結果都需要執行的清理；程式需自行判斷有哪些檔案可用 |
    | `afternotok:ID` | 前置工作以失敗狀態結束，例如非零退出碼、節點故障或逾時 | 失敗後才執行診斷、保存錯誤現場；不會自動修復前一步 |

    **因 dependency 等待而 PENDING 的工作，還沒取得計算節點的 CPU／RAM。**
    它只是保留在排程器的工作清單裡；仍受叢集提交數量等限制，但沒有占著已分配的 CPU 等待。

    如果前置 worker 失敗，`afterok` 已不可能成立，後續彙總該怎麼處理？
    由提交設定表中的 `--kill-on-invalid-dep` 決定：

    - **本實驗明確用 `no`：** 保留 PENDING，讓你看到 DependencyNeverSatisfied，再練習取消。短暫查詢也可能仍顯示 Dependency。
    - **想自動結束這條失敗分支時用 `yes`：** Slurm 判定依賴無法滿足後，取消後續工作，不必人工處理。
    - **沒有指定時：** 依叢集設定決定，不能假設每個 HPC 環境都相同。

    取消自己提交的工作不必找管理員，可以用 `scancel JobID`；本頁也提供本次實驗的取消按鈕。
    修好輸入再提交新的 worker，會取得新的 Job ID，**舊彙總的依賴不會自動改成新的 ID**；
    本章因此取消舊彙總，再提交依賴新修復工作的彙總。

    dependency 依據 Slurm 工作的結束狀態與退出碼判斷，不會檢查 CSV 內容。
    程式若漏算卻仍回傳 exit 0，`afterok` 也會放行，所以彙總程式還是要檢查四份 partial 是否齊全。

    官方說明：[dependency 條件](https://slurm.schedmd.com/sbatch.html#OPT_dependency)、
    [依賴失效時的處理](https://slurm.schedmd.com/sbatch.html#OPT_kill-on-invalid-dep)。
    """) if csv_mode else mo.md('')
    return


@app.cell
def _(csv_aggregate_button, csv_mode, mo, step_heading):
    step_heading(mo, 'aggregate', csv_mode, csv_aggregate_button)
    return


@app.cell
def _(csv_mode, get_aggregate_result, get_array_result, lesson, mo, run_id, step_result):
    step_result(mo, 'aggregate', csv_mode, get_aggregate_result(), lesson, run_id, prerequisite=get_array_result())
    return


@app.cell
def _(mo):
    mo.md("""
    ## 結果判讀：提交回條、工作狀態與資料是否正確

    sbatch 參數統一查前面的「提交設定」表；這裡只說明執行後看到的輸出與結果。

    | 結果／欄位 | 怎麼判讀？ |
    | --- | --- |
    | sbatch 的 stdout／exit 0 | 是提交回條，只代表成功提交，尚未證明計算成功；例如第 6 步提交成功，但計算預期 FAILED |
    | Task 顯示 `300_2` | array 300 的 index 2；對照前面的輸入／輸出表，應處理 shard-2.csv |
    | 工作狀態 `COMPLETED`／`FAILED` | 是 Slurm 對計算工作的觀察結果；預期失敗的實驗還要核對錯誤原因 |
    | 等待原因 `Dependency`／`DependencyNeverSatisfied` | 依賴尚未滿足／已無法滿足；詳細處理方式見前面的 dependency 說明 |
    | `.out`／`.err` 的內容 | 程式輸出與錯誤；FAILED 時先對照 .err，空白 .err 不足以證明成功 |
    | `partials/編號.json` | 每份 worker 的筆數與加總；缺少一份時不應產生完整彙總 |
    | `summary.json` | 最終資料結果，應對照下表的份數、筆數與總和，再按「驗證並保存」核對完整證據 |

    每份 CSV 的 value 都是 2 × id。以下是結果的對照，資料與檔案都留在本次實驗的 pipeline/ 目錄：

    | index | id 範圍 | 筆數 | 預期 value_sum |
    | --- | --- | --- | --- |
    | 0 | 1–1000 | 1000 | 1001000 |
    | 1 | 1001–2000 | 1000 | 3001000 |
    | 2 | 2001–3000 | 1000 | 5001000 |
    | 3 | 3001–4000 | 1000 | 7001000 |
    | 合計 | 1–4000 | 4000 | 16004000 |

    Slurm 管理工作與依賴；CSV 的分片、驗證與加總由 pipeline.py 實作。
    """)
    return


@app.cell
def _(csv_initial_button, csv_mode, mo):
    mo.vstack([mo.md("""
    ## 觀察第一階段：worker 做完了嗎？彙總為什麼等待？

    按本段按鈕查看工作狀態、輸入檔、四份 partial 與 summary；只會更新下方這份取樣。
    準備完 CSV 就能先查看輸入，提交 worker 與彙總後再按一次。
    worker 跑完可能很快，第一次查詢就看到 COMPLETED 也正常。

    - **success：** 四個 task 與 aggregate 最後都應 COMPLETED；summary 應為 4 份、4000 筆、總和 16004000。
    - **failure-recovery：** task 2 應 FAILED，其餘三個 COMPLETED；原 aggregate 應 PENDING，原因為 Dependency 或 DependencyNeverSatisfied，summary 不存在。
    - 尚未到上述狀態時，稍後再按本段按鈕。FAILED 不會自動等於實驗成功，還要核對失敗原因與修復證據。
    """), csv_initial_button]) if csv_mode else mo.md('')
    return


@app.cell
def _(csv_mode, get_initial_snapshot, mo, observation_result):
    observation_result(mo, get_initial_snapshot()) if csv_mode else mo.md('')
    return


@app.cell
def _(csv_mode, mo):
    mo.md("""
    ## 接著修復：保留三份成功結果，只重算壞掉的一份

    以下只在 failure-recovery 模式顯示。先確認上方的預期失敗，再依序操作。
    步驟 6 的缺片測試與步驟 7 的取消完成後，都可以回到上方「查看第一階段工作與檔案」更新證據。
    """) if csv_mode == 'failure-recovery' else mo.md('')
    return


@app.cell
def _(csv_missing_aggregate_button, csv_mode, mo, step_heading):
    step_heading(mo, 'missing-aggregate', csv_mode, csv_missing_aggregate_button)
    return


@app.cell
def _(csv_mode, get_missing_aggregate_result, lesson, mo, run_id, step_result):
    step_result(mo, 'missing-aggregate', csv_mode, get_missing_aggregate_result(), lesson, run_id)
    return


@app.cell
def _(csv_cancel_dependent_button, csv_mode, mo, step_heading):
    step_heading(mo, 'cancel-dependent', csv_mode, csv_cancel_dependent_button)
    return


@app.cell
def _(csv_mode, get_cancel_dependent_result, get_aggregate_result, lesson, mo, run_id, step_result):
    step_result(mo, 'cancel-dependent', csv_mode, get_cancel_dependent_result(), lesson, run_id, prerequisite=get_aggregate_result())
    return


@app.cell
def _(csv_repair_input_button, csv_mode, mo, step_heading):
    step_heading(mo, 'repair-input', csv_mode, csv_repair_input_button)
    return


@app.cell
def _(csv_mode, get_repair_input_result, lesson, mo, run_id, step_result):
    step_result(mo, 'repair-input', csv_mode, get_repair_input_result(), lesson, run_id)
    return


@app.cell
def _(csv_repair_shard_button, csv_mode, mo, step_heading):
    step_heading(mo, 'repair-shard', csv_mode, csv_repair_shard_button)
    return


@app.cell
def _(csv_mode, get_repair_shard_result, lesson, mo, run_id, step_result):
    step_result(mo, 'repair-shard', csv_mode, get_repair_shard_result(), lesson, run_id)
    return


@app.cell
def _(csv_aggregate_repaired_button, csv_mode, mo, step_heading):
    step_heading(mo, 'aggregate-repaired', csv_mode, csv_aggregate_repaired_button)
    return


@app.cell
def _(csv_mode, get_aggregate_repaired_result, get_repair_shard_result, lesson, mo, run_id, step_result):
    step_result(mo, 'aggregate-repaired', csv_mode, get_aggregate_repaired_result(), lesson, run_id, prerequisite=get_repair_shard_result())
    return


@app.cell
def _(csv_final_button, csv_mode, mo):
    mo.vstack([mo.md("""
    ## 觀察修復結果：新的彙總成功了嗎？

    按本段按鈕查詢新的修復工作與 aggregate。原 task 2 仍保留 FAILED 紀錄，原 aggregate 仍是 CANCELLED；
    新修復 task 2 與新 aggregate 最後應為 COMPLETED。
    四份 partial 應齊全，summary 應與成功路徑相同。第一階段的取樣會保留，不會被這次查詢改寫。
    """), csv_final_button]) if csv_mode == 'failure-recovery' else mo.md('')
    return


@app.cell
def _(csv_mode, get_final_snapshot, mo, observation_result):
    observation_result(mo, get_final_snapshot()) if csv_mode == 'failure-recovery' else mo.md('')
    return


@app.cell
def _(mo):
    mo.md("""
    ## 驗證並保存，再清理

    完成所選路徑後，按「驗證並保存」。成功路徑檢查四個 task、aggregate 與每份 partial 的筆數及總和。
    修復路徑還會檢查失敗證據、原 aggregate 已取消、只補跑 index 2，以及另外三份成功 partial 沒有被改寫。
    若工作還沒完成，等它結束再驗證；只看到 summary 的總和正確還不夠。

    「只清理本次實驗」取消本次仍未結束的工作，保留輸入、結果與紀錄。關閉頁面不會取消工作。
    重按已執行的步驟只讀回原紀錄；想重做請先清理，再建立新實驗。
    """)
    return


@app.cell
def _(lesson, mo, run_id, set_event, verification_controls):
    _buttons = {}
    _view = verification_controls(mo, lesson, run_id, set_event, buttons=_buttons)
    verify_run_button = _buttons.get('verify')
    cleanup_run_button = _buttons.get('cleanup')
    _view
    return cleanup_run_button, verify_run_button


@app.cell
def _(csv_report_button):
    csv_report_button
    return


@app.cell
def _(get_event, get_report_snapshot, mo, report_panel, run_id):
    get_report_snapshot()
    report_panel(mo, run_id, get_event())
    return


@app.cell
def _(mo, source_panel):
    mo.vstack([mo.md("## 對照公開腳本與程式"), source_panel(mo)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 獨立終端驗收

    下面是額外的自動測試，會另外建立工作、注入壞輸入、執行修復並保存 Evidence 報告。
    先清理 notebook 工作，確認 lab 沒有其他工作，再於 Ubuntu 專案根目錄執行：

    ```bash
    python3 scripts/smoke.py --case csv-pipeline-success --case csv-pipeline-failure-recovery
    ```

    它會自動跑兩條路徑，不會替代本頁手動操作的紀錄。
    """)
    return


if __name__ == "__main__":
    app.run()
