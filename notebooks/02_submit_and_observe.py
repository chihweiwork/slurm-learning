import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="02 提交與觀察")


@app.cell
def _():
    import marimo as mo
    from lesson_ui import setup_controls, action_controls, verification_controls
    from submit_view import run_summary, status_panel
    from submit_observer import observer_panel
    from submit_serial import serial_panel
    from lessons_cpu import get_lesson
    lesson = get_lesson('02-submit')
    return action_controls, lesson, mo, observer_panel, run_summary, serial_panel, setup_controls, status_panel, verification_controls


@app.cell
def _(mo):
    mo.md("""
    # 02 提交與觀察：工作在哪裡跑？申請多核就會更快嗎？

    本章先建立實驗、練習 srun／sbatch，再從外部觀察計算工作，最後比較單執行緒用 1 核與 4 核的差別。
    每個工作只申請 **128 MiB RAM**，不使用 GPU。

    ### srun 與 sbatch 比較

    | 比較項目 | `srun ... python3 ...`（直接執行） | `sbatch ... cpu.sbatch`（提交腳本） |
    | --- | --- | --- |
    | 交給 Slurm 的東西 | 要啟動的程式與參數 | 一份批次腳本 |
    | 資源與執行 | 在既有 allocation 外呼叫時，先申請資源，再啟動 task | 依需求排隊，取得資源後執行腳本 |
    | 何時返回？ | 通常等程式結束，終端才回到提示符號 | 提交成功取得 Job ID 就返回，不等計算結束 |
    | 程式輸出在哪？ | 通常直接回到目前終端的 stdout／stderr | 通常寫到 `.out`／`.err`；本章會指定路徑 |
    | 適合什麼情況？ | 前景測試、除錯，或在已分配資源內啟動 task | 不想守著終端的批次計算 |
    | 沒有資源時？ | 一般可等待；本章短測試用 `--immediate=5`，等不到就失敗 | 通常留在 PENDING 等排程 |
    | 會有幾個 Job ID？ | 本章直接按 srun，建立一個 job | 再按 sbatch，另建一個 job；腳本內的 srun 是該 job 的 step |

    **兩個都按，就有兩個工作；它們不是同一個工作的兩種顯示方式。**
    後面的 90 秒觀察與 1／4 核比較也是透過 sbatch 提交，讓你能繼續操作觀察按鈕。

    頁內導覽：[選參數](#submit-setup) · [目前實驗](#submit-current-run) ·
    [srun](#submit-interactive) · [sbatch](#submit-batch) · [觀察實際運算](#submit-external) ·
    [單執行緒 1／4 核比較](#submit-serial) ·
    [輸出與結果](#submit-results) · [指令解說](#submit-reference) · [驗證／清理](#submit-verify)
    """)
    return


@app.cell
def _(mo):
    mo.vstack([mo.Html('<span id="submit-setup"></span>'), mo.md("""## 選擇執行節點與 CPU 數

    **你可以指定核數：** `cpus = 1` 或 `4`，代表每個 task 申請幾個 Slurm CPU（Linux 邏輯 CPU）。
    本章只有 1 個 task；選 4 CPU 不會自動啟動 4 份 Python。

    選好後按一次「套用參數並建立實驗」即可保存設定，下方會立即顯示「目前實驗已就緒」，接著就是 srun／sbatch 按鈕。
    建立實驗只準備紀錄目錄，**啟動／測量按鈕才會提交工作**。
    90 秒工作與後面的 srun／sbatch 都使用這份設定；比較實驗會明確對照固定的 1 與 4 CPU。
    想換設定就重新選擇並建立新實驗；下方會顯示目前實驗實際保存的節點與核數。
    """)])
    return


@app.cell
def _(lesson, mo, setup_controls):
    setup = setup_controls(mo, lesson)
    get_run = setup['get_run']
    get_event = setup['get_event']
    set_event = setup['set_event']
    refresh = setup['refresh']
    parameter_form = setup['form']
    restore_run_menu = setup['restore_menu']
    setup['view']
    return get_event, get_run, parameter_form, refresh, restore_run_menu, set_event


@app.cell
def _(get_event, get_run, mo, run_summary):
    run_id = get_run()
    run_summary(mo, run_id, get_event())
    return (run_id,)


@app.cell
def _(action_controls, get_event, lesson, mo, refresh, run_id, set_event):
    get_event()
    refresh.value
    _buttons = {}
    _view = action_controls(mo, lesson, run_id, set_event, include_verification=False, buttons=_buttons)
    short_srun_button = _buttons.get('interactive')
    short_sbatch_button = _buttons.get('batch')
    _view
    return short_sbatch_button, short_srun_button


@app.cell
def _(mo):
    get_observation, set_observation = mo.state(None, allow_self_loops=True)
    return get_observation, set_observation


@app.cell
def _(get_event, get_observation, mo, observer_panel, refresh, run_id, set_event, set_observation):
    get_event()
    refresh.value
    _buttons = {}
    _view = observer_panel(mo, run_id, get_observation(), set_observation, set_event, buttons=_buttons)
    observer_start_button = _buttons.get('start')
    observer_sample_button = _buttons.get('observe')
    observer_stop_button = _buttons.get('stop')
    _view
    return observer_sample_button, observer_start_button, observer_stop_button


@app.cell
def _(get_event, mo, refresh, run_id, serial_panel, set_event):
    refresh.value
    _buttons = {}
    _view = serial_panel(mo, run_id, get_event(), set_event, buttons=_buttons)
    serial_one_button = _buttons.get('serial-1')
    serial_four_button = _buttons.get('serial-4')
    serial_refresh_button = _buttons.get('refresh')
    _view
    return serial_four_button, serial_one_button, serial_refresh_button


@app.cell
def _(lesson, mo, run_id, set_event, verification_controls):
    _buttons = {}
    _view = verification_controls(mo, lesson, run_id, set_event, buttons=_buttons)
    verify_run_button = _buttons.get('verify')
    cleanup_run_button = _buttons.get('cleanup')
    _view
    return cleanup_run_button, verify_run_button


@app.cell
def _(get_event, lesson, mo, refresh, run_id, status_panel):
    refresh.value
    status_panel(mo, lesson, run_id, get_event())
    return


@app.cell
def _(mo):
    mo.vstack([
        mo.Html('<span id="submit-reference"></span>'),
        mo.accordion({'指令解說：Docker 前綴、Slurm 名詞與資源參數': mo.md("""
        ### 為什麼指令前面有 docker？

        `docker compose exec -T -u lab controller` 表示進入本實驗的 controller 容器，以 lab 身分執行後面的指令。
        `-T` 不配置虛擬終端，讓 notebook 收集輸出；`-u lab` 指定使用者；`controller` 是服務名稱。
        後面的 srun／sbatch 才把工作交給 Slurm，安排到 cpu01／cpu02 計算。

        | 名詞 | 本章怎麼理解？ |
        | --- | --- |
        | Job | 一次交給 Slurm 管理的工作，有自己的 Job ID |
        | Allocation | 分配給工作的節點、CPU、RAM 等資源 |
        | Task | 啟動的一份程式，本章是 1 份 Python |
        | Step | 工作內的一次執行步驟，例如腳本裡的 srun |

        | 選項 | 意思 |
        | --- | --- |
        | `--partition=cpu` | 選 cpu 分區 |
        | `--nodelist=cpu01`／`cpu02` | 指定計算節點 |
        | `--nodes=1`、`--ntasks=1` | 使用 1 台節點，啟動 1 個 task |
        | `--cpus-per-task=1`／`4` | 每個 task 申請的 CPU 數，沒有自動平行化功能 |
        | `--exclusive` | 要求工作獨佔所分配的節點，避免其他工作共用；本章按鈕未使用此選項 |
        | `--mem=128M` | 每台節點申請 128 MiB RAM |
        | `--cpu-bind=threads` | 以邏輯 CPU 為單位設定 task 的 CPU 綁定 |
        | `--time=...` | 工作最長允許執行多久，不是一定要跑滿 |
        | `--immediate=5` | 短 srun 測試五秒內等不到資源就失敗 |
        | `--parsable` | sbatch 使用方便程式解析的格式回傳 Job ID |
        | `--job-name=...`、`--chdir=...` | 工作名稱與執行目錄 |
        | `--output=...`、`--error=...` | stdout／stderr 檔案；`%j` 會替換成 Job ID |

        ### 申請幾個 CPU，與獨佔節點有什麼差別？

        `--cpus-per-task=1` 是替每個 task 申請 1 個 CPU；`--exclusive` 則要求獨佔工作被分配的節點，
        例如 cpu01 這台計算節點。這裡的 cpu01 是模擬節點的容器，獨佔它不代表獨佔整台 Windows 主機。
        在一般配置下，`sbatch --exclusive` 會分配該節點全部 CPU，但 RAM 仍只按要求分配；實際行為也受 partition 的共享設定影響。

        假設一台節點有 4 個可分配 CPU，其他資源足夠、分區允許共享，後來的 B 需要 1 CPU：

        | A 的申請 | B 能否共用這台節點？ |
        | --- | --- |
        | 1 CPU | 可以，還剩 3 CPU |
        | 4 CPU | 需要排隊，全部 CPU 已分配給 A |
        | 1 CPU 加上 `--exclusive` | 需要排隊，A 要求獨佔節點 |

        本章只介紹這個選項，不替按鈕加上它。下一章以 A 申請全部 4 CPU 示範資源不足造成排隊。
        官方說明：[sbatch --exclusive](https://slurm.schedmd.com/sbatch.html#OPT_exclusive)。

        本章短 srun 指令最多等待 15 秒；若指令逾時又無法確認結果，會標為 unknown，先核對紀錄再處理。
        官方說明：[srun](https://slurm.schedmd.com/srun.html)、[sbatch](https://slurm.schedmd.com/sbatch.html)。
        """)}),
    ])
    return


if __name__ == "__main__":
    app.run()
