import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="05 跨節點 MPI：兩個程序共同計算")


@app.cell
def _():
    import marimo as mo
    from environment_view import TERMINAL_CSS
    from lesson_ui import setup_controls, verification_controls
    from lessons_cpu import get_lesson
    from mpi_view import mpi_controls, submit_result, snapshot_result, report_result, source_result
    lesson = get_lesson('05-mpi')
    return TERMINAL_CSS, lesson, mo, mpi_controls, report_result, setup_controls, snapshot_result, source_result, submit_result, verification_controls


@app.cell
def _(TERMINAL_CSS, mo):
    mo.vstack([mo.Html(TERMINAL_CSS), mo.md("""
    # 05 跨節點 MPI：兩個程序互相通訊，共同完成計算

    第四章的四個 worker 各算一份 CSV，最後再由另一個工作彙總。
    這一章則讓**同一個 Slurm 工作裡的兩個程序，在不同節點上執行，並在運算途中交換資料**。
    這種合作方式稱為 MPI（Message Passing Interface）。

    | 比較 | 第四章：job array | 第五章：MPI |
    | --- | --- | --- |
    | 工作關係 | 各個 array task 獨立處理輸入，可各自成功或失敗 | 一個工作裡的兩個程序共同參與一次計算 |
    | 如何分工 | SLURM_ARRAY_TASK_ID 選擇 CSV | MPI rank 區分程序，由程式安排工作 |
    | 怎麼合併 | 另外提交帶 afterok 的彙總工作 | 程式呼叫 MPI_Allreduce，兩個程序都收到加總結果 |
    | Slurm 的角色 | 排程各個 array task | 分配兩個節點的資源，由 srun 啟動 MPI 程序 |

    本次固定使用 cpu01、cpu02，各一個程序、1 CPU、256 MiB RAM，總共 2 CPU、512 MiB RAM，不用 GPU。
    cpu01／cpu02 是同一台電腦上的兩個容器；可以練習跨 Slurm 節點通訊，無法用來代表跨實體伺服器的效能。
    """)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 這次兩個程序要做什麼？

    rank 是程序在 MPI 群組中的編號，從 0 開始；size 是這個群組的程序總數。
    **rank 0 不是 CPU 0，rank 1 也不是 cpu01。** 程序與節點的實際對應要看工作配置與輸出。

    | 程序 | 提供的數字 | 共同參與的計算 | 各自收到的結果 |
    | --- | --- | --- | --- |
    | rank 0 | 1 | 同一次 Allreduce：1 + 2 | 3 |
    | rank 1 | 2 | 同一次 Allreduce：1 + 2 | 3 |

    MPI_Allreduce 讓群組裡的程序共同提供數值，並讓每個程序都取得合併結果。
    本實驗兩個程序執行同一支 C 程式，各自提供 rank + 1，所以最後兩邊都應得到 sum=3。
    Allreduce 不會建立下一個 Slurm 工作，也不需要 afterok。

    官方參考：[MPI_Allreduce](https://docs.open-mpi.org/en/main/man-openmpi/man3/MPI_Allreduce.3.html)、
    [Slurm MPI 啟動方式](https://slurm.schedmd.com/mpi_guide.html)。

    ## 1．建立本次實驗

    按「套用參數並建立實驗」只保存設定與目錄，不會提交工作。
    接著在步驟 2 先看指令，再按提交；想重做請建立新實驗。
    """)
    return


@app.cell
def _(lesson, mo, setup_controls):
    _setup = setup_controls(mo, lesson)
    get_run = _setup['get_run']
    get_event = _setup['get_event']
    set_event = _setup['set_event']
    parameter_form = _setup['form']
    restore_run_menu = _setup['restore_menu']
    _setup['view']
    return get_event, get_run, parameter_form, restore_run_menu, set_event


@app.cell
def _(get_run):
    run_id = get_run()
    return (run_id,)


@app.cell
def _(lesson, mo, mpi_controls, run_id):
    _controls = mpi_controls(mo, lesson, run_id)
    mpi_submit_button = _controls['submit']
    mpi_observe_button = _controls['observe']
    get_mpi_submit = _controls['get_submit']
    get_mpi_snapshot = _controls['get_snapshot']
    mpi_setup_error = _controls['setup_error']
    return get_mpi_snapshot, get_mpi_submit, mpi_observe_button, mpi_setup_error, mpi_submit_button


@app.cell
def _(mo, mpi_setup_error, run_id):
    mo.vstack([mo.md(f'目前實驗：`{run_id}`。下一步提交兩節點 MPI 工作。' if run_id else '尚未建立實驗。'),
               mo.plain_text('讀取實驗失敗：' + mpi_setup_error) if mpi_setup_error else mo.md('')])
    return


@app.cell
def _(mo, mpi_submit_button):
    mo.vstack([mo.md("""
    ## 2．提交一個工作，讓兩個節點共同運算

    這個按鈕提交公開的 mpi.sbatch，拿到一個 Job ID 就返回。
    腳本會先用 mpicc 編譯 mpi_sum.c，再以 srun 啟動兩個 MPI 程序。
    **兩個 rank 屬於同一個 Slurm 工作，不會像兩次 sbatch 那樣拿到兩張提交回條。**

    下方黑底區塊會先顯示 stdin 指令與空白 stdout；按下按鈕後才填入實際回應。
    程式很短，第一次查詢時就已 COMPLETED 也正常。
    """), mpi_submit_button])
    return


@app.cell
def _(get_mpi_submit, lesson, mo, run_id, submit_result):
    submit_result(mo, lesson, run_id, get_mpi_submit())
    return


@app.cell
def _(mo):
    mo.md("""
    ## 提交設定：這次為什麼能跨兩個節點？

    所有本章 sbatch 選項集中在這張表。「命令列」是上方黑底區塊；「腳本」是 mpi.sbatch 裡的 #SBATCH 行。
    同名選項以命令列為準；RUN_DIR 代稱本次 /shared/demos/實驗編號。
    Docker 前綴 `docker compose exec -T -u lab controller` 是在 controller 容器中，以 lab 身分執行後面的提交指令。

    | 用途分類 | sbatch 選項 | 設定位置 | 本實驗的意思 |
    | --- | --- | --- | --- |
    | 提交回條 | `--parsable` | 命令列 | stdout 回傳 Job ID，方便程式讀取；不代表 MPI 已完成 |
    | 工作辨識 | `--job-name=demo-…-mpi` | 命令列 | 唯一名稱，方便對照本次實驗 |
    | 工作目錄 | `--chdir=RUN_DIR` | 命令列覆蓋腳本 | 在本次實驗目錄啟動；編譯後的執行檔另外放在共享目錄 /shared |
    | 輸出紀錄 | `--output=RUN_DIR/mpi-%j.out` | 命令列覆蓋腳本 | %j 換成 Job ID；兩個 rank 的 stdout 都寫入這份檔案 |
    | 輸出紀錄 | `--error=RUN_DIR/mpi-%j.err` | 命令列 | 收集編譯、srun 與 MPI 執行時的 stderr |
    | 節點範圍 | `--partition=cpu` | 腳本 | 使用 CPU partition |
    | 節點範圍 | `--nodelist=cpu01,cpu02` | 命令列 | 指定這次要使用的兩個節點，方便核對跨節點配置 |
    | 節點數量 | `--nodes=2` | 腳本 | 同一份工作需要兩個節點的資源 |
    | 程序數量 | `--ntasks=2` | 腳本 | 為這份工作配置兩個 Slurm task；腳本中的 srun 會啟動兩個 MPI 程序 |
    | 程序分布 | `--ntasks-per-node=1` | 腳本 | 配合兩節點、兩 task，每個節點放一個程序 |
    | CPU | `--cpus-per-task=1` | 腳本 | 每個 task 申請 1 CPU，兩個 task 合計 2 CPU |
    | RAM | `--mem=256M` | 腳本 | 每個節點申請 256 MiB；兩節點合計 512 MiB |
    | 執行上限 | `--time=00:03:00` | 腳本 | 整份工作的執行上限三分鐘，不含排隊時間 |

    **資源數量不會自動讓程式平行化。** 本章的 C 程式有呼叫 MPI，才會讓兩個 rank 合作。
    第四章的 --array 是建立多份工作；這裡的 --ntasks=2 是在同一份工作裡配置兩個 task。

    ### 指令沒寫 rank 數量，怎麼知道要有 0 和 1？

    sbatch 會讀取最後那個腳本 `mpi.sbatch` 裡的設定；不是只讀命令列。
    其中這三行決定本次配置，接著 srun 使用這些資源設定啟動程序：

    ```bash
    #SBATCH --nodes=2
    #SBATCH --ntasks=2
    #SBATCH --ntasks-per-node=1
    ```

    `--ntasks=2` 配合 srun 啟動兩個 MPI 程序，MPI 初始化後，兩個程序在 MPI_COMM_WORLD 中的 rank 分別是 0、1。
    C 程式呼叫 `MPI_Comm_rank` 取得自己的編號，呼叫 `MPI_Comm_size` 得到群組大小 2；沒有用 Python 的 range 產生程序。
    `--nodelist=cpu01,cpu02` 指定在哪些節點執行，**節點清單的長度不是 rank 數量的設定**。
    本次只是剛好兩個節點、兩個程序、每節點一個；MPI 也可以在一個節點上執行多個 rank。

    **檔名裡的 `%j` 又是另一件事：它代表整份工作的 Job ID，不是 rank。**
    例如 sbatch 回傳 128，`mpi-%j.out` 就變成 `mpi-128.out`，兩個 rank 的輸出都寫進這一個檔案。
    第四章的 `%a` 才是 array task 的 index；本章沒有提交 array。

    ### 腳本如何啟動 MPI？

    ```bash
    srun --mpi=pmix --cpu-bind=threads "$binary"
    ```

    srun 使用這份工作已取得的 allocation，啟動兩個 task，不會另外提交第二個 sbatch 工作。
    --mpi=pmix 選用 PMIx 支援，協助 MPI 程序啟動與交換通訊資訊；
    --cpu-bind=threads 限制 task 在分配的邏輯 CPU 上執行，並不代表程式會建立多條執行緒。
    $binary 是 mpicc 編譯出的執行檔；放在 /shared，兩個節點都讀得到，腳本結束時會移除它。
    """)
    return


@app.cell
def _(mo, mpi_observe_button):
    mo.vstack([mo.md("""
    ## 3．看工作配置，再看兩個 rank 的結果

    按本段按鈕查詢本次 Job ID，並讀取它的 .out／.err；只更新下方取樣，不會重新提交。
    若仍在 PENDING 或 RUNNING，稍後再按。重按提交按鈕只會讀回舊回條，不會重跑。

    | 證據來源 | 要確認什麼？ |
    | --- | --- |
    | squeue | 是否仍排隊／執行，以及分配的節點；完成後會從這裡消失 |
    | scontrol／已核對身分的工作紀錄 | NodeList 包含 cpu01、cpu02，NumNodes=2、NumTasks=2；最後狀態應 COMPLETED、ExitCode=0:0 |
    | mpi-JobID.out | 恰好兩筆 rank JSON，分別是 rank 0 和 1，hostname 合起來是 cpu01、cpu02 |
    | 每筆 rank JSON | size=2、sum=3、valid=true；兩個程序都拿到完整加總 |
    | mpi-JobID.err | 失敗時先看這裡；空白 stderr 本身不足以證明成功 |

    hostname 是程式自己回報的資訊；工作配置是排程器的紀錄，兩者應互相對得上。
    valid 是這支程式的自我檢查：size=2、sum=3，且兩個 hostname 不同；
    本頁的正式驗證還會核對 hostname 必須正好是 cpu01／cpu02。
    這個短實驗沒有做第二章那種 process CPU 取樣，不能拿它當長時間 CPU 使用率的證據。
    兩行輸出可能 rank 1 在前，不代表程序啟動順序錯誤。

    squeue 的 NODELIST 顯示已分配節點、NODES 是節點數、CPUS 是 CPU 數、TIME 是已執行時間；
    最後的 REASON 說明為何等待。只有「查不到工作」不能判定成功。
    """), mpi_observe_button])
    return


@app.cell
def _(get_mpi_snapshot, get_mpi_submit, mo, snapshot_result):
    snapshot_result(mo, get_mpi_snapshot(), get_mpi_submit())
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4．驗證並保存，再清理

    看到兩個 rank 的結果後按「驗證並保存」。驗證會核對工作 COMPLETED、成功退出、使用者 UID=1000，
    以及恰好兩筆 rank、不同節點、size=2、sum=3、valid=true。
    若工作仍未結束，等幾秒再觀察與驗證；不是只看 stdout 有沒有印出 3。

    「只清理本次實驗」會取消本次尚未結束的工作，保留輸出與報告。
    關閉頁面不會取消工作；重新開啟後可在側欄恢復既有實驗，不會重送。
    想再做一次，先處理舊工作，再按上方「套用參數並建立實驗」。
    """)
    return


@app.cell
def _(lesson, mo, run_id, set_event, verification_controls):
    _buttons = {}
    _view = verification_controls(mo, lesson, run_id, set_event, buttons=_buttons)
    mpi_verify_button = _buttons.get('verify')
    mpi_cleanup_button = _buttons.get('cleanup')
    _view
    return mpi_cleanup_button, mpi_verify_button


@app.cell
def _(get_event, mo, report_result, run_id):
    report_result(mo, run_id, get_event())
    return


@app.cell
def _(mo, source_result):
    mo.vstack([mo.md('## 對照公開腳本與 C 程式\n\n展開查看本章實際使用的程式；顯示原始碼不會提交工作。'), source_result(mo)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 遇到問題要看哪裡？

    | 現象 | 下一步 |
    | --- | --- |
    | PENDING | 看等待原因；同時要兩個節點可用，先確認前幾章的工作已結束或清理 |
    | FAILED／非零退出 | 先看 .err：mpicc 是編譯階段，PMIx／srun 是啟動與通訊階段 |
    | 只有一筆 rank，或 sum／hostname 不符 | 不能當作通過；核對 .err、兩節點配置與公開程式，不要只用有輸出判定成功 |
    | 紀錄缺失／查詢失敗 | 保留錯誤，確認叢集狀態；不把缺失標成 COMPLETED |
    | 提交結果 unknown | 先核對原回條、唯一工作名稱、UID 與目錄，確認有沒有已提交的工作，再決定如何清理 |

    ## 獨立終端驗收

    先結束或清理 notebook 工作，再於 Ubuntu 專案根目錄執行：

    ```bash
    python3 scripts/smoke.py --case cross-node-mpi
    ```

    這會另外提交一份 MPI 測試工作、檢查兩個 rank 的跨節點加總並保存 Evidence 報告，不會取代本頁的實驗紀錄。
    """)
    return


if __name__ == "__main__":
    app.run()
