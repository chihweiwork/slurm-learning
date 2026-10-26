import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="00｜從這裡開始")


@app.cell
def _():
    import marimo as mo
    import course_progress
    import course_ui
    from notebook_queries import read_snapshot
    return course_progress, course_ui, mo, read_snapshot


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_t0, set_t0 = course_ui.view_state(mo)
    return get_t0, get_term, get_token, set_t0, set_term, set_token


@app.cell
def _(course_ui, get_t0, get_token, mo, set_token):
    course_ui.sidebar(mo, '00', get_token, set_token, get_t0)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '00', learn=['這套課怎麼用：每章都是同樣六段', '怎麼看叢集現在的狀態', '安全規則：什麼能動、什麼不能動'],
                     before=['在左側按「開始新的學習紀錄」：之後每一章的練習檔與進度都存在這個紀錄裡',
                             '叢集要是 idle（下方「現在的叢集」三個數字：執行中 0、等待中 0、健康節點 3）'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 這個實驗室是什麼
    一台電腦上用 Docker 跑出一個小型 Slurm 叢集：一台 controller（同時當作你登入的機器）、三個運算節點，加上記錄歷史的資料庫。
    你在頁面上按的每個按鈕、在迷你終端打的每個指令，都是在這個真實的 Slurm 上執行。

    | 容器 | 角色 | CPU | 記憶體 | GPU |
    | :--- | :--- | ---: | ---: | ---: |
    | controller | slurmctld：收工作、排程、決定誰在哪跑；也是你下指令的「登入節點」 | — | — | — |
    | cpu01 | slurmd：運算節點，partition `cpu` | 4 | 7168 MiB | — |
    | cpu02 | slurmd：運算節點，partition `cpu` | 4 | 7168 MiB | — |
    | gpu01 | slurmd：GPU 節點，partition `gpu` | 4 | 14336 MiB | 1 |
    | slurmdbd | 把每個工作的紀錄寫進資料庫（`sacct` 查的就是它） | — | — | — |
    | mariadb | slurmdbd 背後的資料庫 | — | — | — |

    兩個 partition：`cpu`（預設，cpu01＋cpu02，單一工作最長 30 分鐘）與 `gpu`（gpu01，最長 30 分鐘）。
    所有節點都掛載同一個 `/shared`（主機上的 `shared/` 目錄），所以你在 controller 寫的檔案，節點上看得到。
    """)
    return


@app.cell
def _(mo):
    cluster_refresh = mo.ui.refresh(options=['15s', '1m'], default_interval='15s', label='叢集狀態自動更新')
    return (cluster_refresh,)


@app.cell
def _(cluster_refresh, mo, read_snapshot):
    cluster_refresh.value
    _snapshot = read_snapshot()
    _counts = _snapshot['counts']
    _nodes = _snapshot['sources']['nodes']['data'] or []

    def _value(number):
        return '?' if number is None else number

    _rows = [{'節點': n['name'], '狀態': '+'.join(n['state']), 'partition': ','.join(n['partitions']),
              'CPU（已用／可用）': f"{n['alloc_cpus']}／{n['effective_cpus']}",
              '記憶體 MiB（已用／總量）': f"{n['alloc_memory']}／{n['real_memory']}",
              'GPU': n['gres'] or '—', 'Reason': n['reason'] or ''} for n in _nodes]
    mo.vstack([
        mo.md('## 現在的叢集'),
        cluster_refresh,
        mo.hstack([mo.stat(_value(_counts['running']), label='執行中', caption='RUNNING 的 task'),
                   mo.stat(_value(_counts['pending']), label='等待中', caption='PENDING 的 task'),
                   mo.stat(_value(_counts['healthy_nodes']), label='健康節點', caption='共 3 個')], justify='start', gap=2),
        mo.ui.table(_rows, selection=None) if _rows else mo.md('查不到節點：controller 可能沒有回應。').callout(kind='danger'),
        mo.md(f"快照時間 `{_snapshot['observed_at'][11:19]} UTC`。等一下你在終端打 `sinfo`，看到的是同一份資訊。"),
    ])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 每一章長這樣
    1. **章首卡**：這章學什麼、多久、開始前要先做什麼。
    2. **概念**：文字加動畫圖。圖會自動播放；關掉「自動播放」後可以用「上一步／下一步」一步一步看，下方說明當前這一步。
    3. **示範**：按鈕執行一個預先寫好的指令。每個按鈕上面寫著**你要做什麼、為什麼、看哪裡**，下面列出實際的指令（逐段註解）、狀態與輸出、「你應該看到」。
    4. **換你練習**：任務卡告訴你要做什麼，在迷你終端自己打指令，按「檢查」對答案。
    5. **小測驗**：幾題單選，對答案後逐題說明。
    6. **收尾**：清掉這章留下的工作與設定，再前往下一章。

    ### 示範按鈕的四種狀態
    - **尚未就緒**：前一步還沒完成（例如要先讓某個工作開始跑），卡片會寫原因。
    - **可執行**：條件都滿足，按下去就執行一次。
    - **執行中**：指令已送出，背景執行中；不用等，也不要重按。
    - **已消耗**：這一步已經做過了。每一步只能做一次，避免重複提交；想重來就在收尾區「重新開始示範」。

    ### 為什麼每章結尾要收尾
    共用叢集上，你沒取消的工作會一直佔著 CPU，你沒恢復的節點別人就用不到。收尾區會列出你留下的東西，全部 ✓ 才算離開乾淨。
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 安全規則
    - **只動自己的工作**：你在終端提交的工作名稱用 `course-` 開頭，示範用的工作名稱是 `demo-` 開頭。取消時只用明確的 JobID（`scancel 123`）。
    - **禁止 `scancel -u lab`**：它會取消 lab 的所有工作，包括你在別的章節、別的分頁正在用的。迷你終端會直接擋下。
    - **看到不對勁就停手回報**：節點的 Reason 不是你寫的、queue 裡有你不認識的工作、節點顯示 DOWN／NOT_RESPONDING——這些都不是你該修的，記下輸出找管理者。第 09 章會詳細練習這種判斷。
    """).callout(kind='warn')
    return


@app.cell
def _(course_progress, course_ui, get_token, mo):
    _token = get_token()
    _progress = course_progress.load(_token) if _token else None
    mo.vstack([mo.md('## 課程地圖'), course_ui.course_map(mo, _progress)])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 換你練習
    第一個指令：`sinfo`，看叢集有哪些 partition 與節點。
    """)
    return


@app.cell
def _(course_ui, get_t0, get_token, mo, set_t0):
    _token = get_token()
    course_ui.task(
        mo, _token, '00', 't0-sinfo', get_t0, set_t0,
        title='t0｜用 sinfo 看叢集',
        steps_md=r"""
在下方終端輸入 `sinfo` 後按「執行」（或 Ctrl＋Enter），然後按「檢查」。輸出每一欄的意思：

| 欄位 | 意思 |
| :--- | :--- |
| PARTITION | 節點群的名稱；後面有 `*` 的是預設 partition（不寫 `--partition` 就排到這裡） |
| AVAIL | partition 是否開放（up／down） |
| TIMELIMIT | 這個 partition 單一工作最長可以跑多久 |
| NODES | 這一列有幾個節點 |
| STATE | 節點狀態：idle 閒置、mix 部分使用、alloc 全滿、drain 維護中、down 故障 |
| NODELIST | 是哪些節點；`cpu[01-02]` 是 cpu01、cpu02 的縮寫 |

同一個 partition 若有節點狀態不同，會分成多列。
""")
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sinfo', 'sinfo -N -l', 'squeue', 'hostname'])
    return


@app.cell
def _(course_ui, mo):
    recheck = course_ui.recheck_button(mo)
    mo.vstack([mo.md('## 收尾\n本章沒有示範工作；確認叢集是乾淨的再往下走。'), recheck])
    return (recheck,)


@app.cell
def _(course_ui, mo, recheck):
    course_ui.closing(mo, '00', recheck.value)
    return


if __name__ == "__main__":
    app.run()
