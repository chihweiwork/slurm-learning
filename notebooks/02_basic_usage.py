import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="02｜基本用法：提交、查看、取消")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    from lessons_cpu import get_lesson
    lesson = get_lesson('02-submit')
    lessons = [lesson]
    return course_diagrams, course_questions, course_ui, lesson, lessons, mo


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_actions, set_actions = course_ui.actions_state(mo)
    get_dg, set_dg = course_ui.diagram_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_t2, set_t2 = course_ui.view_state(mo)
    get_t3, set_t3 = course_ui.view_state(mo)
    get_t4, set_t4 = course_ui.view_state(mo)
    get_t5, set_t5 = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_actions,
        get_dg,
        get_quiz,
        get_t1,
        get_t2,
        get_t3,
        get_t4,
        get_t5,
        get_term,
        get_token,
        set_actions,
        set_dg,
        set_quiz,
        set_t1,
        set_t2,
        set_t3,
        set_t4,
        set_t5,
        set_term,
        set_token,
    )


@app.cell
def _(course_ui, get_quiz, get_t1, get_t2, get_t3, get_t4, get_t5, get_token, mo, set_token):
    course_ui.sidebar(mo, '02', get_token, set_token, get_t1, get_t2, get_t3, get_t4, get_t5, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '02',
                     learn=['`sinfo`／`squeue`／`sbatch`／`srun`／`scancel`／`scontrol show job`／`sacct` 各做什麼',
                            '怎麼讀 squeue 與 sacct 的欄位', '怎麼只處理自己的工作'],
                     before=['完成第 01 章（知道 allocation、step、task 是什麼）', '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：七個每天都會用的指令

    | 指令 | 用途 | 什麼時候用 | 安全提醒 |
    | :--- | :--- | :--- | :--- |
    | `sinfo` | 看 partition 與節點狀態 | 提交前確認有沒有可用的節點 | 唯讀 |
    | `squeue` | 看排隊中與執行中的工作 | 提交後追蹤；`--me` 只看自己 | 唯讀；結束的工作不會出現 |
    | `sbatch` | 提交批次腳本，立刻回傳 JobID | 大部分的工作 | 一定要寫 `--time`、`--mem` |
    | `srun` | 立刻要資源並執行，等它跑完 | 很短的測試、或在 sbatch 腳本裡啟動 step | 資源不夠時會卡住等 |
    | `scancel` | 取消工作 | 送錯了、不需要了 | 只用明確的 JobID；不要用 `-u` |
    | `scontrol show job` | 看單一工作的完整設定與狀態 | 想知道申請了什麼、為什麼還在等 | 結束約 1 小時後就查不到 |
    | `sacct` | 查歷史：狀態、結束碼、用了多少 | 工作結束後 | 唯讀 |

    `srun` 直接在終端執行時，Slurm 同時建立 allocation 與 step；`sbatch` 只建立 allocation，腳本裡的每個 `srun` 才是 step。
    複習一下這三層：
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg, mo, set_dg):
    course_ui.animated(mo, course_diagrams.ALLOCATION_STEP_TASK, get_dg, set_dg)
    return


@app.cell
def _(course_ui, mo):
    refresh = course_ui.demo_refresh(mo)
    mo.vstack([mo.md('## 示範\n按鈕會執行卡片上列出的真實指令；狀態每 3 秒自動更新。'), refresh])
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
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'interactive', controls, states.get(lesson['chapter']),
                    what='用 `srun` 立刻在 cpu01 跑一個小程式',
                    why='看 allocation 與 step 一起產生，而且程式是在運算節點上跑，不是在 controller。',
                    watch='卡片下方「指令的 stdout」：srun 直接把程式的輸出印回來（一行 JSON）。',
                    expect=['狀態：【已消耗】已結束 — job <JobID> COMPLETED ExitCode=0:0',
                            '指令的 stdout 是 `{"affinity": [0], "hostname": "cpu01", "job_id": "<JobID>", "sum": 50005000, "uid": 1000}`',
                            'hostname=cpu01：程式跑在運算節點，不是 controller；uid=1000 是 lab；affinity 只有 1 個 CPU（申請了 1 個）'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lesson, mo, runs, states):
    (course_ui.demo(mo, lesson, runs.get(lesson['chapter']), 'batch', controls, states.get(lesson['chapter']),
                    what='用 `sbatch` 提交 `cpu.sbatch`，馬上拿回 JobID',
                    why='批次工作不等結果：sbatch 把腳本交給排程器就回來，之後用 squeue／sacct 追。',
                    watch='「指令的 stdout」只有 sbatch 回傳的 JobID；程式的輸出在「工作輸出 batch-<JobID>.out」。',
                    expect=['指令的 stdout 只有一個數字，例如 `982`：這就是 JobID，sbatch 不等工作跑完',
                            '幾秒後狀態：【已消耗】已結束 — job <JobID> COMPLETED ExitCode=0:0',
                            '工作輸出 batch-<JobID>.out 是 `{"affinity": [0], "hostname": "cpu01", "job_id": "<JobID>", "sum": 50005000, "uid": 1000}`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(course_ui, mo, refresh):
    refresh.value
    course_ui.queue_table(mo)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 換你練習
    下面五個任務都在同一個迷你終端完成（終端在任務卡下方）。`<JobID>` 換成你自己拿到的數字。
    建議順序：先提交 → 用 squeue 看 → 用 scontrol 看細節 → 結束後用 sacct 看 → 最後練習取消。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '02', 't1-submit', get_t1, set_t1, title='t1｜自己提交 cpu.sbatch',
                   steps_md='在終端輸入 `sbatch /opt/lab/examples/cpu.sbatch`。看到 `Submitted batch job 123` 就成功了；'
                            '等它跑完（幾秒）再按「檢查」。')
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '02', 't2-squeue', get_t2, set_t2, title='t2｜用 squeue --me 看自己的工作',
                   steps_md='輸入 `squeue --me`。欄位：`JOBID`、`PARTITION`、`NAME`、`USER`、`ST`（R 執行中、PD 等待中、CG 收尾中）、'
                            '`TIME`（已跑多久）、`NODES`、`NODELIST(REASON)`（在哪跑；等待中時是原因）。'
                            '空的也沒關係，代表你沒有工作在跑。')
    return


@app.cell
def _(course_ui, get_t3, get_token, mo, set_t3):
    course_ui.task(mo, get_token(), '02', 't3-show-job', get_t3, set_t3, title='t3｜用 scontrol show job 看細節',
                   steps_md='輸入 `scontrol show job <你的 JobID>`。找這幾個欄位：`NumCPUs`（拿到幾個 CPU）、'
                            '`MinMemoryNode`／`MinMemoryCPU`（記憶體上限）、`TimeLimit`（時間上限）、`WorkDir`（工作目錄）。'
                            '工作結束約 1 小時後就查不到了。')
    return


@app.cell
def _(course_ui, get_t4, get_token, mo, set_t4):
    course_ui.task(mo, get_token(), '02', 't4-sacct', get_t4, set_t4, title='t4｜用 sacct 看結果',
                   steps_md='輸入 `sacct -j <JobID> --format=JobID,JobName,State,ExitCode,Elapsed`。'
                            '會看到好幾列：`123`（allocation）、`123.batch`（腳本本身）、`123.extern`、`123.0`（srun 的 step）。'
                            '`State` COMPLETED、`ExitCode` 0:0 才是成功。')
    return


@app.cell
def _(course_ui, get_t5, get_token, mo, set_t5):
    course_ui.task(mo, get_token(), '02', 't5-cancel', get_t5, set_t5, title='t5｜提交一個會跑 2 分鐘的工作，再取消它',
                   steps_md='1. `sbatch --wrap "sleep 120" --job-name=course-wait`，記下 JobID\n'
                            '2. `squeue --me` 確認它在跑\n'
                            '3. `scancel <JobID>`\n'
                            '4. 幾秒後按「檢查」：sacct 會記成 `CANCELLED by 1000`（1000 是 lab 的 UID）')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch /opt/lab/examples/cpu.sbatch', 'squeue --me', 'scontrol show job <JobID>',
                                    'sacct -j <JobID> --format=JobID,JobName,State,ExitCode,Elapsed',
                                    'sbatch --wrap "sleep 120" --job-name=course-wait', 'scancel <JobID>'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '02', course_questions.QUESTIONS['02'], get_quiz, set_quiz)
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
    course_ui.closing(mo, '02', recheck.value)
    return


if __name__ == "__main__":
    app.run()
