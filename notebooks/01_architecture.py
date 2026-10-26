import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="01｜Slurm 架構與運作原理")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    import notebook_views
    return course_diagrams, course_questions, course_ui, mo, notebook_views


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_dg_components, set_dg_components = course_ui.diagram_state(mo)
    get_dg_states, set_dg_states = course_ui.diagram_state(mo)
    get_dg_layers, set_dg_layers = course_ui.diagram_state(mo)
    get_dg_sched, set_dg_sched = course_ui.diagram_state(mo)
    get_sim, set_sim = course_ui.simulator_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_dg_components,
        get_dg_layers,
        get_dg_sched,
        get_dg_states,
        get_quiz,
        get_sim,
        get_token,
        set_dg_components,
        set_dg_layers,
        set_dg_sched,
        set_dg_states,
        set_quiz,
        set_sim,
        set_token,
    )


@app.cell
def _(course_ui, get_quiz, get_token, mo, set_token):
    course_ui.sidebar(mo, '01', get_token, set_token, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '01',
                     learn=['Slurm 有哪些元件、各在哪台機器',
                            '一個工作從提交到留下紀錄經過哪些狀態',
                            '排程器怎麼決定誰先跑'],
                     before=['完成第 00 章（知道怎麼開學習紀錄）', '本章是純概念，不會動到叢集'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 1：Slurm 的元件與一個工作的一生

    按「自動播放」看完整流程，或關掉自動播放用「上一步／下一步」慢慢看。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_components, mo, set_dg_components):
    course_ui.animated(mo, course_diagrams.COMPONENTS, get_dg_components, set_dg_components)
    return


@app.cell
def _(mo):
    mo.md(r"""
    **對照本 lab：**

    | 圖中的元件 | 在這個實驗室是 |
    | :--- | :--- |
    | 登入節點／終端 | 你在頁面裡的迷你終端（指令實際在 `controller` 容器以 `lab` 身分執行） |
    | slurmctld | `controller` 容器 |
    | slurmd | `cpu01`、`cpu02`、`gpu01` 三個容器各跑一個 |
    | slurmdbd + MariaDB | `slurmdbd` 與 `mariadb` 兩個容器；`sacct` 從這裡查 |
    | `/shared` | 所有容器都掛載的同一個共用目錄 |
    | munge | 每個容器都有同一把 munge key，元件之間互相認證 |
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 2：工作狀態機
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_states, mo, set_dg_states):
    course_ui.animated(mo, course_diagrams.JOB_STATES, get_dg_states, set_dg_states)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### Reason 怎麼讀

    工作在 PENDING 時，`squeue` 的 `NODELIST(REASON)` 欄會寫出原因：

    | Reason | 意思 | 你該做什麼 |
    | :--- | :--- | :--- |
    | `Resources` | 你是隊首，但現在沒有足夠的空閒 CPU／記憶體／GPU | 等；或申請少一點資源 |
    | `Priority` | 前面還有更優先的工作在等同樣的資源 | 等；排到隊首後會變 Resources |
    | `Dependency` | 你設了 `--dependency`，前面的工作還沒完成 | 等前面的工作結束 |
    | `ReqNodeNotAvail` | 你要的節點不能用（DRAIN／DOWN），或沒有任何節點符合要求 | 檢查申請的資源；節點問題找管理者 |
    | `BeginTime` | 你用 `--begin` 指定了開始時間，還沒到 | 等到指定時間 |
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 3：allocation、step、task 三層
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_layers, mo, set_dg_layers):
    course_ui.animated(mo, course_diagrams.ALLOCATION_STEP_TASK, get_dg_layers, set_dg_layers)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 4：排程與回填（backfill）
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_sched, mo, set_dg_sched):
    course_ui.animated(mo, course_diagrams.SCHEDULING, get_dg_sched, set_dg_sched)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 排程模擬器

    1. 先**關閉回填**，看 C（1 CPU、2 分鐘）什麼時候開始——它要等 B 開始後才輪得到。
    2. 再**開啟回填**比較：C 會在 0 分鐘就開始，而 B 的開始時間沒有變晚。
    3. 也可以自己加 job（例如要 5 個 CPU，或 gpu 分區要 GPU），看看哪些會 `ReqNodeNotAvail`。
    """)
    return


@app.cell
def _(course_ui, get_sim, mo, set_sim):
    course_ui.simulator(mo, get_sim, set_sim)
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    mo.vstack([mo.md('本章沒有終端練習：**小測驗按「對答案」並全部答對**，左側本章才會打勾 ✓（答錯可以改答案再按一次）。')
               .callout(kind='info'),
               course_ui.quiz(mo, get_token(), '01', course_questions.QUESTIONS['01'], get_quiz, set_quiz)])
    return


@app.cell
def _(mo, notebook_views):
    mo.vstack([mo.md('## 收尾\n本章沒有動叢集，不需要清理；直接進下一章。'),
               notebook_views.next_chapter_link(mo, '01')])
    return


if __name__ == "__main__":
    app.run()
