import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="08｜用量與 accounting")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    import notebook_views
    from lessons_accounting import DEFAULT_FIELDS, SACCT_FIELDS, STATES, WINDOWS, get_lesson, sacct_query
    lesson = get_lesson('08-accounting')
    lessons = [lesson]
    return (
        DEFAULT_FIELDS,
        SACCT_FIELDS,
        STATES,
        WINDOWS,
        course_diagrams,
        course_questions,
        course_ui,
        lesson,
        lessons,
        mo,
        notebook_views,
        sacct_query,
    )


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_actions, set_actions = course_ui.actions_state(mo)
    get_dg, set_dg = course_ui.diagram_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_t2, set_t2 = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_actions,
        get_dg,
        get_quiz,
        get_t1,
        get_t2,
        get_term,
        get_token,
        set_actions,
        set_dg,
        set_quiz,
        set_t1,
        set_t2,
        set_term,
        set_token,
    )


@app.cell
def _(course_ui, get_quiz, get_t1, get_t2, get_token, mo, set_token):
    course_ui.sidebar(mo, '08', get_token, set_token, get_t1, get_t2, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '08',
                     learn=['用 `sacct` 查歷史與用量', '帳戶（account）與關聯（association）是什麼', '紀錄保存在哪裡、保存多久'],
                     before=['完成第 03 章（要有自己的工作可查）', '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：紀錄保存在哪裡、多久
    `squeue`／`scontrol show job` 讀的是 slurmctld 記憶體裡的資料，工作結束約 1 小時（`MinJobAge=3600`）後就查不到；
    `sacct` 讀的是 slurmdbd 存在 MariaDB 的歷史，本 lab 沒有設定 purge，會一直保存。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg, mo, set_dg):
    course_ui.animated(mo, course_diagrams.ACCOUNTING_FLOW, get_dg, set_dg)
    return


@app.cell
def _(mo, notebook_views):
    mo.vstack([mo.md('### 各種紀錄的保存期限'), notebook_views.retention_table(mo)])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### sacct 常用欄位

    一個工作在 sacct 裡會有好幾列，建議分三層看：

    | 層級 | 看哪幾列 | 看哪些欄位 | 用途 |
    | :--- | :--- | :--- | :--- |
    | ① 只看 allocation（加 `-X`） | `123` | `State`、`ExitCode`、`Elapsed`、`Timelimit`、`ReqMem`、`AllocCPUS` | 整體結局：成功、失敗、超時、取消 |
    | ② 加上 `.0` step | `123.0` | `State`、`ExitCode`、`MaxRSS`、`TotalCPU` | srun 啟動的程式本身；OOM 的真正原因（`OUT_OF_MEMORY 0:125`）與記憶體峰值在這列 |
    | ③ 全部 step | `123.batch`、`123.extern` | 同上 | `.batch` 是腳本的 shell，`.extern` 是 Slurm 管理用，通常不用判讀 |

    - **MaxRSS 只在 step 列**，allocation 列一律空白；所以要看用量時不要加 `-X`。
    - **ExitCode `a:b`**：`a` 是程式退出碼，`b` 是終止它的訊號。
    - **ReqTRES vs AllocTRES**：申請了什麼 vs 實際配到什麼。
    - `Account` 欄：這個工作記在哪個帳戶名下。
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 帳戶、使用者、關聯

    - **account（帳戶）**：計費與配額的單位，通常對應一個研究計畫或實驗室。
    - **user（使用者）**：Linux 帳號，例如本 lab 的 `lab`。
    - **association（關聯）**：`user × account × cluster`（可再加 partition）的組合；使用者必須透過某個 association 才能把工作記到某個 account。
      限制（例如最多幾個 CPU、多少 GPU 小時）掛在 association 上。
    - 本 lab 設定 `AccountingStorageEnforce=none`：**只記錄、不強制**，沒有 association 也能提交；正式叢集通常會強制，沒有 association 的提交會被拒絕。
    - 建立與刪除 account 需要管理者權限（`sacctmgr`）；本章示範用的 account 都以 `demo-` 開頭，收尾時必須刪掉。
    """)
    return


@app.cell
def _(course_ui, mo):
    refresh = course_ui.demo_refresh(mo)
    mo.vstack([mo.md('## 示範\n五個步驟依序建立 account → 關聯 → 用它提交工作 → 刪除關聯 → 刪除 account；狀態每 3 秒自動更新。'), refresh])
    return (refresh,)


@app.cell
def _(course_ui, get_actions, get_token, lessons):
    get_actions()
    runs = course_ui.ensure_runs(lessons, get_token())
    return (runs,)


@app.cell
def _(course_ui, get_actions, get_token, lessons, mo, runs, set_actions):
    controls = course_ui.demo_controls(mo, lessons, runs, get_token(), get_actions(), set_actions)
    return (controls,)


@app.cell
def _(controls, course_ui, lessons, refresh, runs, set_actions):
    refresh.value
    controls
    states = course_ui.lesson_states(lessons, runs, controls, set_actions)
    return (states,)


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'add-account', controls, states.get(lesson['chapter']),
                    what='用 `sacctmgr add account` 建立本次專屬的 account',
                    why='account 是記帳單位；先有 account 才能把使用者掛上去。',
                    watch='「指令的 stdout」（sacctmgr 的回應）。',
                    expect=['狀態：已完成 — 約 0.1 秒',
                            '指令的 stdout：`Adding Account(s)` 下一行是新 account，例如 `demo-305c5afdc601`；`Description = demo-<run id>` 是這次示範的所有權標記；`Organization = lab`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'add-user', controls, states.get(lesson['chapter']),
                    what='用 `sacctmgr add user` 建立 lab ↔ 這個 account 的 association',
                    why='association 讓 lab 可以把工作記到這個 account 名下。',
                    watch='「指令的 stdout」。',
                    expect=['狀態：已完成',
                            '指令的 stdout：`Associations =` 下一行 `C = compose-lab A = demo-… U = lab`：cluster＋account＋user 這一組就是一個 association',
                            '在下方終端打 `sacctmgr show association user=lab` 會多出這一列'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'job', controls, states.get(lesson['chapter']),
                    what='用這個 account 提交一個短工作（`--account=demo-…`）',
                    why='看 sacct 怎麼把用量記到指定的 account。',
                    watch='狀態徽章與「工作輸出 job-<JobID>.out」；Account 欄要用 sacct 查。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            '工作輸出 `{"affinity": [0], "hostname": "cpu01", ..., "sum": 50005000, "uid": 1000}`',
                            '在下方終端打 `sacct -j <JobID> --format=JobID,Account,State`：Account 欄是 `demo-…`，不是預設的 `lab`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'delete-user', controls, states.get(lesson['chapter']),
                    what='sacct 查到紀錄後，刪除 lab 與這個 account 的 association',
                    why='用完的關聯要拿掉；刪除關聯不會刪掉已記錄的工作歷史。',
                    watch='「指令的 stdout」。',
                    expect=['狀態：已完成',
                            '指令的 stdout：`Deleting user associations...` 與 `C = compose-lab A = demo-… U = lab`',
                            '刪掉 association 不會刪歷史：`sacct -j <上一步的 JobID> --format=JobID,Account` 仍查得到 Account=demo-…'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'delete-account', controls, states.get(lesson['chapter']),
                    what='刪除本次的 demo account',
                    why='留下測試 account 會讓之後的人搞不清楚它屬於誰；收尾清單也會檢查。',
                    watch='「指令的 stdout」。',
                    expect=['狀態：已完成',
                            '指令的 stdout：`Deleting accounts...` 與 `demo-…`',
                            '下方終端打 `sacctmgr show account`：只剩 `lab`、`root`，沒有 `demo-` 開頭的 account'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(DEFAULT_FIELDS, SACCT_FIELDS, STATES, WINDOWS, mo):
    query_form = mo.md(r"""
    ## 互動查詢：我的歷史（只讀）
    {job_ids}

    {window} {state}

    {allocations}

    {fields}
    """).batch(
        job_ids=mo.ui.text(label='Job ID（逗號分隔，可留空）', placeholder='例如 402,409'),
        window=mo.ui.dropdown(['不限（搭配 Job ID）', *WINDOWS], value='最近 1 天', label='--starttime'),
        state=mo.ui.dropdown([s or '全部' for s in STATES], value='全部', label='--state'),
        allocations=mo.ui.checkbox(value=True, label='-X／--allocations（只看 allocation 列；看 MaxRSS 時請取消）'),
        fields=mo.ui.multiselect(list(SACCT_FIELDS), value=list(DEFAULT_FIELDS), label='--format 欄位'),
    ).form(submit_button_label='執行 sacct（只讀）')
    query_form
    return (query_form,)


@app.cell
def _(WINDOWS, mo, notebook_views, query_form, sacct_query):
    if query_form.value is None:
        _out = mo.md('填好條件後按「執行 sacct」。不填 Job ID 時，sacct 只列 `--starttime` 之後、你（lab）自己的 job。')
    else:
        _v = query_form.value
        _result = sacct_query(job_ids=_v['job_ids'].split(','), window=WINDOWS.get(_v['window']),
                              state='' if _v['state'] == '全部' else _v['state'],
                              allocations=_v['allocations'], fields=_v['fields'])
        if _result['status'] == 'invalid':
            _out = mo.md(_result['error']).callout(kind='warn')
        else:
            _out = mo.vstack([
                notebook_views.command_block(mo, 'diagnostic', _result['command'], '可以複製到迷你終端（去掉前面的 docker compose 部分）'),
                mo.md(_result['error']).callout(kind='danger') if _result['status'] != 'ok' else mo.md(f"共 {len(_result['rows'])} 列"),
                mo.ui.table(_result['rows'], selection=None, pagination=True, page_size=20) if _result['rows'] else mo.md('沒有符合的紀錄。'),
            ])
    _out
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 換你練習
    兩個任務都在下方迷你終端完成。輸入後按「執行」（或 Ctrl＋Enter）。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '08', 't1-sacct-usage', get_t1, set_t1, title='t1｜用 sacct 查今天的用量（含 MaxRSS）',
                   steps_md='輸入 `sacct -u lab --starttime today --format=JobID,JobName,State,Elapsed,MaxRSS,Account`。'
                            '找出一個工作的 `.batch` 或 `.0` 列，讀它的 MaxRSS（記憶體峰值）與 Elapsed；'
                            '注意 allocation 列的 MaxRSS 是空白。指令裡要有 `MaxRSS` 欄位才算通過。')
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '08', 't2-assoc', get_t2, set_t2, title='t2｜看 lab 的 association',
                   steps_md='輸入 `sacctmgr show association user=lab`（`assoc` 縮寫也可以）。'
                            '每一列是一個 `Cluster × Account × User` 組合；`Account` 欄就是 lab 可以記帳的帳戶。'
                            '再試 `sacctmgr show account` 看所有帳戶。')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='accounting',
                       suggestions=['sacct -u lab --starttime today --format=JobID,JobName,State,Elapsed,MaxRSS,Account',
                                    'sacctmgr show association user=lab', 'sacctmgr show account'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '08', course_questions.QUESTIONS['08'], get_quiz, set_quiz)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 收尾
    按「驗證並保存」把本次示範的證據存下來，再「只清理本次實驗」。清理會刪掉殘留的 `demo-` association 與 account，
    但 sacct 的工作歷史不會被刪。下方清單第 3 項會檢查**沒有任何 `demo-` 開頭的 account 留在資料庫**；沒通過就回來清理。
    """)
    return


@app.cell
def _(controls, course_ui, lessons, mo, refresh, runs):
    refresh.value
    course_ui.closing_actions(mo, lessons, runs, controls) if runs else course_ui.need_token(mo)
    return


@app.cell
def _(course_ui, mo):
    recheck = course_ui.recheck_button(mo)
    recheck
    return (recheck,)


@app.cell
def _(course_ui, get_actions, mo, recheck):
    get_actions()
    course_ui.closing(mo, '08', recheck.value)
    return


if __name__ == "__main__":
    app.run()
