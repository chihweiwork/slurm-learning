import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="01 環境與資源")


@app.cell
def _():
    import marimo as mo
    from notebook_queries import read_snapshot
    from notebook_views import navigation
    from environment_view import environment_panel, read_environment_checks

    return (
        environment_panel,
        mo,
        navigation,
        read_environment_checks,
        read_snapshot,
    )


@app.cell
def _(mo, navigation):
    refresh = mo.ui.refresh(options=['5s','15s','1m'], default_interval=None, label='只讀刷新（查詢狀態）')
    mo.sidebar(mo.vstack([navigation(mo, "01"), refresh]), width=290)
    return (refresh,)


@app.cell
def _(mo):
    mo.md("""
    # 01 環境、身分與可排程資源

    **目標**：認識你用 Docker 建立的小型 Slurm 叢集：誰安排工作、誰執行工作，以及結果存在哪裡。
    本頁只有查詢，不建立 run、不提交工作、不恢復節點。即使叢集有別人的工作也可以觀察。

    **怎麼讀這一頁：** 先看說明，再對照黑底 terminal 的 `stdin:` 指令與 `stdout:` 輸出。
    警告或錯誤會另列 `stderr:`；完整 JSON 保留在頁面下方，可依需要展開。
    需要更新狀態時，用左側「只讀刷新」；選 5s 就會每五秒查一次，不必按瀏覽器重新整理。

    **預期**：controller 可回應、cpu01／cpu02／gpu01 各有效 CPU 4、cpu／gpu partition，gpu01 有一張 GPU GRES。
    查詢失敗時保留錯誤與最後成功時間，不能顯示假綠燈；請先看 Compose、scontrol ping、daemon logs。
    """)
    return


@app.cell
def _(mo):
    mo.vstack([
        mo.md("""
        ## 先建立全貌：Slurm 幫你安排程式在哪裡、什麼時候執行

        假設你有一支 Python 程式，需要 1 個 CPU、128 MiB RAM。
        你把程式與資源需求交給 Slurm；Slurm 根據資源、優先順序與排程規則安排執行。
        **程式負責計算，Slurm 負責分配資源與管理工作。** 要使用多個 CPU，程式本身也要支援平行運算。

        這個實驗中，你透過網頁按鈕或 Ubuntu 終端機，以容器內的 `lab` 身分提交工作。
        controller 是派工主管，cpu01／cpu02 是實際做事的計算節點。
        """),
        mo.mermaid('''flowchart TD
            user["你：網頁按鈕／Ubuntu 終端機"] -->|"Docker：進入 controller 執行 Slurm 指令"| controller["controller：接收提交、安排工作"]
            controller -->|"分配資源、啟動工作"| cpu01["cpu01：執行你的程式"]
            controller -->|"分配資源、啟動工作"| cpu02["cpu02：執行你的程式"]
            cpu01 -->|"讀取輸入、寫入結果"| shared["/shared：共享檔案目錄"]
            cpu02 -->|"讀取輸入、寫入結果"| shared
        '''),
        mo.md("""
        這些容器都在你的一台電腦裡；一般 HPC 叢集則通常有多台實體計算節點。
        實際使用 HPC 時，通常先登入登入節點，再提交 Slurm 工作。
        本實驗把提交入口放在 controller，所以會看到 `docker compose exec -T -u lab controller ...`；
        這段是進入容器執行指令的方式，後面的 `srun`／`sbatch` 才是 Slurm 指令。

        ## 下方五種查詢，各自回答什麼問題？

        **它們是五種資訊來源，不是五台機器。**

        點第一欄的指令，可以跳到本頁對應的說明或查詢結果。
        `--json` 表示用 JSON 格式輸出；下方節點區另外用一般文字格式呈現相同類型的資訊。

        | 指令／跳到說明 | 查詢來源 | 像什麼 | 回答的問題 |
        | --- | --- | --- | --- |
        | [`scontrol --json ping`](#env-source-controller) | 排程控制器 | 派工主管 | 負責安排工作的控制器有回應嗎？ |
        | [`scontrol --json show nodes`](#env-nodes) | 計算節點 | 做事的工人 | 有哪些節點？CPU、RAM 分配多少？節點可用嗎？ |
        | [`scontrol --json show jobs`](#env-snapshot) | 工作紀錄 | 工作登記簿 | 某個 Job ID 的需求、狀態、結束結果是什麼？ |
        | [`squeue`](#env-snapshot) | 正在執行／排隊的工作 | 現場待辦看板 | 哪些工作還在跑或等待？為什麼等待？ |
        | [`nvidia-smi`](#env-gpu) | GPU 觀測 | GPU 儀表板 | GPU 整卡目前用了多少運算資源與顯示記憶體？ |

        工作紀錄與排隊資料收在[完整 snapshot](#env-snapshot)；展開後看 `sources.jobs` 與 `sources.queue`。
        其他查詢：[Docker 服務](#env-compose) · [Slurm 設定檔](#env-conf) ·
        [節點狀態 sinfo](#env-sinfo) · [分區規則](#env-partitions) ·
        [身分與共享目錄](#env-identity) · [診斷與獨立驗收](#env-diagnostics)。

        工作結束後會離開待辦看板，但可能暫時仍在工作登記簿中。
        **這裡的工作紀錄不是永久歷史資料庫。** 程式印出的文字要看 `.out`／`.err`；
        本實驗保存的報告與輸出檔則在專案的 `shared/` 裡。

        ## 一個工作，從提交到結束會經過什麼？

        以需要 1 個 CPU 的工作為例：

        1. **提交：** Slurm 接受需求，給你一個 Job ID。收到 ID 代表提交成功，還不代表計算成功。
        2. **等待：** 如果資源不足或尚未輪到它，就顯示 `PENDING`。這是排隊，不是程式失敗；看 Reason 判斷原因。
        3. **執行：** Slurm 分配資源，在計算節點啟動程式，工作進入 `RUNNING`。
        4. **結束：** 工作釋放資源，Slurm 才能把資源分給其他工作。程式輸出與結束狀態供你檢查結果。

        資源與排程條件允許時，工作可能很快開始；短工作也可能快到你看不到中間狀態。

        | 結束狀態 | 代表什麼 |
        | --- | --- |
        | `COMPLETED` | Slurm 判定工作成功結束；結果內容是否正確，仍要自行驗證 |
        | `FAILED` | 工作執行失敗，需要查看退出碼與錯誤輸出 |
        | `CANCELLED` | 被使用者或有權限的管理員取消 |
        | `TIMEOUT` | 達到工作的時間上限而終止 |
        | `OUT_OF_MEMORY` | 超出記憶體限制而終止 |

        ## 看資源表之前，先分清楚這幾個詞

        | 名詞 | 在這個實驗裡的意思 |
        | --- | --- |
        | Node（節點） | 執行程式的地方，例如 cpu01 |
        | Partition（分區） | 一組節點加上排程規則；提交時可用 `-p cpu` 選擇 |
        | Job（工作） | 一次提交給 Slurm 管理的工作，有自己的 Job ID |
        | Allocation（資源分配） | Slurm 留給工作的 CPU、RAM 等配額；不等於即時使用率 |
        | Step（工作內的執行步驟） | 在既有工作分配的資源裡啟動程式；例如 batch 腳本內的 `srun` |

        要到 4 個 CPU，不代表 Python 程式會自動變成四倍快；
        看到節點有空閒 CPU，也不保證自己的工作能立即執行，還要符合記憶體、分區與排程條件。

        **你在這裡是提交工作的使用者。** 取消自己的工作通常不需要管理權限；
        取消別人的工作、調整節點狀態等操作，則需要額外權限。
        後面的維運章節會明確示範管理操作；一般提交與查詢以 `lab` 身分執行。

        接下來再看實際查詢：先確認查詢成功，再看節點和資源，最後確認身分與共享目錄。
        """),
    ])
    return


@app.cell
def _(
    environment_panel,
    mo,
    read_environment_checks,
    read_snapshot,
    refresh,
):
    refresh.value
    snapshot = read_snapshot()
    checks = read_environment_checks()
    mo.vstack([
        environment_panel(mo, snapshot, checks),
        mo.Html('<span id="env-diagnostics"></span>'),
        mo.md('''## 診斷與獨立驗收
        **前面的頁面查詢只負責顯示資訊；下面是你需要時可以手動執行的工具。**
        在 Ubuntu 終端先切到專案目錄：
        ```bash
        cd ~/slurm-learning
        ```

        ### 1. 驗收：目前的節點與分區設定是否符合本實驗？
        ```bash
        python3 scripts/smoke.py --case nodes-partitions
        ```
        這支程式會自動檢查：控制器是否有回應、節點是否齊全且健康、
        每節點是否有 4 個有效 CPU、RAM 是否符合設定，以及 cpu 分區是否為預設且包含正確節點。
        GPU 模式也會檢查 GPU 分區與 GRES；它不是效能測試，也不會測完整套工作流程。

        **這個驗收要求叢集空閒。** 若仍有執行中、排隊或暫停等待的工作，就會驗收失敗，
        不代表叢集壞掉，也不會替你取消那些工作。這個 case 不提交計算工作，
        但會把查詢與檢查結果寫到 `shared/results/`，最後印出 `Evidence:` 報告路徑。
        成功時會看到 `PASS nodes-partitions`；失敗時先讀錯誤訊息，再看下面的 log。

        ### 2. 看 controller 容器最近印出了什麼
        ```bash
        docker compose logs --no-color --tail=100 controller
        ```
        讀 controller 容器的 stdout／stderr，查看啟動訊息與錯誤線索。
        `--no-color` 去除顏色控制碼、方便複製；`--tail=100` 只取最近 100 行。
        這不是你的計算結果，也不保證收錄所有 Slurm daemon 記錄。

        ### 3. 看 cpu01 的計算服務與身分驗證服務記錄
        ```bash
        docker compose exec -T -u root cpu01 journalctl -u slurmd -u munge --no-pager -n 100
        ```
        `docker compose exec -T -u root cpu01` 表示以 root 身分進入 cpu01 執行後面的查詢。
        `journalctl` 讀取 systemd 日誌；`-u slurmd -u munge` 只看計算節點服務與 MUNGE 身分驗證服務，
        `--no-pager` 直接印出、避免進入翻頁畫面，`-n 100` 取最近 100 筆。
        cpu01 無法註冊或驗證失敗時，可以從這裡找原因；要查 cpu02，就把指令中的 cpu01 換成 cpu02。

        **平常不需要每次都執行這三行。** 想確認設定符合實驗預期，用第 1 行；
        遇到容器或節點異常，再用第 2、3 行找線索。讀 log 不要求叢集空閒，也不會停止服務。
        本頁不會自動清理工作、修改 Compose、掛載 Docker socket、變更檔案擁有者（chown）或重建叢集。
        ''')
    ])
    return


if __name__ == "__main__":
    app.run()
