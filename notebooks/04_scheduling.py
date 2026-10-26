import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="04｜排程與等待：為什麼我的工作在 PENDING")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    from lessons_cpu import get_lesson
    lesson = get_lesson('04-queue')
    lessons = [lesson]
    return course_diagrams, course_questions, course_ui, lesson, lessons, mo


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_actions, set_actions = course_ui.actions_state(mo)
    get_dg_sched, set_dg_sched = course_ui.diagram_state(mo)
    get_dg_states, set_dg_states = mo.state(0, allow_self_loops=True)
    get_sim, set_sim = course_ui.simulator_state(mo, preset='先來先服務／回填', backfill=False)
    get_observe, set_observe = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_actions,
        get_dg_sched,
        get_dg_states,
        get_observe,
        get_quiz,
        get_sim,
        get_t1,
        get_term,
        get_token,
        set_actions,
        set_dg_sched,
        set_dg_states,
        set_observe,
        set_quiz,
        set_sim,
        set_t1,
        set_term,
        set_token,
    )


@app.cell
def _(course_ui, get_quiz, get_t1, get_token, mo, set_token):
    course_ui.sidebar(mo, '04', get_token, set_token, get_t1, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '04',
                     learn=['PENDING 的 Reason 怎麼讀', '排程器為什麼讓某些工作等',
                            '`squeue`／`sprio`／`scontrol show job` 哪些欄位告訴你要等多久'],
                     before=['完成第 02 章', '左側已選好學習紀錄', '叢集 idle（沒有別人的工作在跑）'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：排程器怎麼決定誰先跑
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_sched, mo, set_dg_sched):
    course_ui.animated(mo, course_diagrams.SCHEDULING, get_dg_sched, set_dg_sched)
    return


@app.cell
def _(mo):
    mo.md(r"""
    複習第 01 章的狀態機第 1 步：PENDING 時，Reason 告訴你為什麼還在等。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_states, mo, set_dg_states):
    course_ui.animated(mo, course_diagrams.JOB_STATES, get_dg_states, set_dg_states)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### Reason 速查表

    | Reason | 意思 | 你該做什麼 |
    | :--- | :--- | :--- |
    | `Resources` | 你是隊首，但現在沒有足夠的空閒 CPU／記憶體／GPU | 等；或申請少一點資源 |
    | `Priority` | 前面還有更優先的工作在等同樣的資源 | 等；排到隊首後會變 Resources |
    | `Dependency` | 你設了 `--dependency`，前面的工作還沒完成 | 等前面的工作結束 |
    | `ReqNodeNotAvail` | 你要的節點不能用（DRAIN／DOWN），或沒有任何節點符合要求 | 檢查申請的資源；節點問題找管理者 |
    | `BeginTime` | 你用 `--begin` 指定了開始時間，還沒到 | 等到指定時間 |

    ### 模擬器：等一下真實叢集會重現這張圖

    預設是「先來先服務」、回填關閉：A 佔 3 CPU，B 要 4 CPU 只能等（Resources），C 排在 B 後面（Priority）。
    打開回填看 C 怎麼插隊。下面的示範會在真實的 cpu01 上製造同樣的「資源不夠」。
    """)
    return


@app.cell
def _(course_ui, get_sim, mo, set_sim):
    course_ui.simulator(mo, get_sim, set_sim)
    return


@app.cell
def _(course_ui, mo):
    refresh = course_ui.demo_refresh(mo)
    mo.vstack([mo.md('## 示範\n按鈕會執行卡片上列出的真實指令；狀態每 3 秒自動更新。順序：holder → waiter → 觀察問答 → release。'),
               refresh])
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
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'holder', controls, states.get(lesson['chapter']),
                    what='在 cpu01 獨佔 4 個 CPU 180 秒',
                    why='製造「資源不夠」的狀況：cpu01 只有 4 個 CPU，全被 holder 佔走。',
                    watch='狀態徽章，與下方「我的工作」表的 STATE／NODELIST(REASON) 欄。',
                    expect=['狀態：等待輸出 marker → 執行中 — job <JobID> RUNNING，並顯示「holder 操作窗口約剩 N 秒」',
                            '工作輸出 holder-<JobID>.out 第一行 `{"affinity": [0, 1, 8, 9], "hostname": "cpu01", ..., "started": true, ...}`：4 個 CPU 都被它佔住',
                            '「我的工作」表：holder RUNNING、NODELIST cpu01；180 秒後會自己結束，接下來的步驟要在這段時間內做'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'waiter', controls, states.get(lesson['chapter']),
                    what='提交一個也要 cpu01 的工作',
                    why='看排程器為什麼讓它等。',
                    watch='狀態徽章，與下方「我的工作」表 waiter 的 NODELIST(REASON) 欄。',
                    expect=['狀態：【已消耗】等待 scheduler — job <JobID> PENDING，Reason=Resources；scheduler 預估 HH:MM:SS 開始（只是估計）',
                            '「我的工作」表：waiter PENDING，`(Resources)`；還沒有工作輸出（它沒跑過）'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(course_ui, get_observe, get_token, mo, set_observe):
    course_ui.quiz(mo, get_token(), '04', [{
        'id': '04-observe', 'prompt': 'waiter 的 Reason 是？',
        'options': ['Priority', 'Resources', 'Dependency', 'ReqNodeNotAvail'], 'answer': 1,
        'explain': 'waiter 已經是隊首，只是 cpu01 的 4 個 CPU 都被 holder 佔走，所以是 Resources。',
    }], get_observe, set_observe, key='observe', title='觀察問答')
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'release', controls, states.get(lesson['chapter']),
                    what='寫 marker 讓 holder 提前結束',
                    why='資源一釋放，排程器會立刻讓 waiter 開始。',
                    watch='這張卡片的「指令的 stdout」，以及上面 holder／waiter 兩張卡片的狀態。',
                    expect=['指令的 stdout `{"operation": "release", "paths": [".../queue.release"]}`：寫了一個標記檔，holder 看到就結束',
                            'holder 卡片變成已結束 COMPLETED，輸出多一行 `"released": true`',
                            'waiter 卡片幾秒內變成已結束 COMPLETED，輸出 `{"affinity": [0], "hostname": "cpu01", ..., "sum": 50005000, ...}`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(course_ui, mo, refresh):
    refresh.value
    course_ui.queue_table(mo, title='我的工作（隨狀態自動更新）')
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 換你練習

    `squeue` 預設的欄位不一定有 Reason；用 `--format` 自己挑欄位：`%i` JobID、`%j` 名稱、`%T` 狀態、`%R` Reason（或節點）。
    `scontrol show job <JobID>` 看 `JobState`、`Reason`、`StartTime`（PENDING 時是排程器的預估，會變）；
    `sprio -j <JobID>` 看優先權由哪些因子組成。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '04', 't1-reason', get_t1, set_t1, title='t1｜自己印出 Reason 欄',
                   steps_md='1. 在上面示範按 holder，再按 waiter\n'
                            '2. waiter 還在等的時候，在終端輸入 `squeue --me --format="%i %j %T %R"`，看 waiter 的 Reason\n'
                            '3. 也可以試 `scontrol show job <waiter 的 JobID>` 與 `sprio -j <JobID>`\n'
                            '4. 按「檢查」\n\n'
                            '注意：holder 只會跑 180 秒，要在這段時間內做完。來不及的話，到下方收尾區按「只清理本次實驗」，'
                            '再按「重新開始示範」建立新的 run，從 holder 重來。')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['squeue --me --format="%i %j %T %R"', 'scontrol show job <JobID>', 'sprio -j <JobID>'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '04', course_questions.QUESTIONS['04'], get_quiz, set_quiz)
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
    course_ui.closing(mo, '04', recheck.value)
    return


if __name__ == "__main__":
    app.run()
