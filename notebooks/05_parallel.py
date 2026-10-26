import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="05｜平行與多節點：array、dependency、MPI")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    from lessons_cpu import get_lesson
    csv = get_lesson('05-csv')
    mpi = get_lesson('05-mpi')
    lessons = [csv, mpi]
    return course_diagrams, course_questions, course_ui, csv, lessons, mo, mpi


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
    course_ui.sidebar(mo, '05', get_token, set_token, get_t1, get_t2, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '05',
                     learn=['用 array 一次送出多個同樣的 task', '用 dependency 把工作串成流程', '多節點 MPI 工作要怎麼申請'],
                     before=['完成第 03 章（會寫 sbatch）', '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：array 與 dependency
    同一個腳本要處理很多份輸入時，不必手動送很多次；有前後順序的步驟，也不必自己盯著等。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg, mo, set_dg):
    course_ui.animated(mo, course_diagrams.ARRAY_DEPENDENCY, get_dg, set_dg)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 什麼時候用哪一種

    | 方式 | 適合 | 怎麼寫 |
    | :--- | :--- | :--- |
    | array | 同一個腳本、不同輸入（例如 4 份 CSV） | `--array=0-3`，腳本內用 `$SLURM_ARRAY_TASK_ID` 選輸入 |
    | dependency | 前後有順序（先處理、再彙總） | `--dependency=afterok:<JobID>` |
    | MPI | 一個程式跨節點、程序之間要互相溝通 | `--nodes=2 --ntasks=2`，腳本內用 `srun` 啟動 |

    ### `$SLURM_ARRAY_TASK_ID` 與 `%A_%a`
    - 每個 array task 拿到不同的 `$SLURM_ARRAY_TASK_ID`（0、1、2…），用它決定處理哪一份輸入。
    - `squeue`／`sacct` 裡 array task 的 ID 寫成 `<母 JobID>_<task>`，例如 `120_0`、`120_3`。
    - `--output=result-%A_%a.out`：`%A` 是 array 母 JobID、`%a` 是 task 編號，每個 task 各寫一個檔。
    - `--array=0-3%2`：`%2` 表示同時最多 2 個 task 在跑。
    """)
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
def _(controls, course_ui, csv, mo, runs, states):
    (course_ui.demo(mo, csv, runs.get(csv['chapter']), 'prepare', controls, states.get(csv['chapter']),
                    what='準備 4 份 CSV（shard 0–3）',
                    why='array 的每個 task 會各自處理一份輸入；先把輸入放到所有節點都看得到的 /shared。',
                    watch='「指令的 stdout」：這一步在主機上準備資料，不經過 Slurm。',
                    expect=['狀態：【已消耗】已完成 — 0.0x 秒',
                            '指令的 stdout `{"prepared": ".../pipeline", "row_count": 4000, "shards": 4}`：切成 4 片、共 4000 列'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, csv, mo, runs, states):
    (course_ui.demo(mo, csv, runs.get(csv['chapter']), 'array', controls, states.get(csv['chapter']),
                    what='用 `--array=0-3%2` 一次送出 4 個 worker task，同時最多 2 個',
                    why='同一個腳本、不同輸入：一次提交就好，Slurm 幫你排程每個 task。',
                    watch='「指令的 stdout」是 array 的母 JobID；四個 task 的輸出是 `array-<JobID>_0.out`…`_3.out`。',
                    expect=['指令的 stdout 只有一個數字（母 JobID，例如 `990`）；task 的 JobID 是 `990_0`…`990_3`',
                            '狀態最後是已結束 COMPLETED ExitCode=0:0（四個 task 都成功）',
                            '每片輸出一行，例如 `{"index": 0, "row_count": 1000, "value_sum": 1001000}`；index 1、2、3 的 value_sum 是 3001000、5001000、7001000',
                            '本 lab 每片不到 1 秒就跑完，「我的工作」表可能來不及看到；之後用 `sacct -j <JobID>` 看四個 task'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, csv, mo, runs, states):
    (course_ui.demo(mo, csv, runs.get(csv['chapter']), 'aggregate', controls, states.get(csv['chapter']),
                    what='提交 `--dependency=afterok:<array JobID>` 的彙總工作',
                    why='彙總要等所有 worker 成功才有意義；交給 Slurm 等，不必自己盯。',
                    watch='狀態徽章與「工作輸出 aggregate-<JobID>.out」。',
                    expect=['它在 worker 全部 COMPLETED 之前是 PENDING、Reason=Dependency（worker 很快，可能一閃而過）',
                            '狀態最後是已結束 COMPLETED ExitCode=0:0',
                            '工作輸出 `{"row_count": 4000, "shards": 4, "value_sum": 16004000}`：16004000 = 1001000 + 3001000 + 5001000 + 7001000，四片合計'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, mo, mpi, runs, states):
    (course_ui.demo(mo, mpi, runs.get(mpi['chapter']), 'mpi', controls, states.get(mpi['chapter']),
                    what='提交 `mpi.sbatch`：2 個 rank 分別在 cpu01、cpu02 做 Allreduce',
                    why='MPI 是一個程式跨節點溝通，要一次申請多個節點（`--nodes=2 --ntasks=2`）。',
                    watch='「工作輸出 mpi-<JobID>.out」的兩行 JSON。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            '兩行輸出（順序不一定）：`{"rank":0,"size":2,"hostname":"cpu01","sum":3,"valid":true}` 與 `{"rank":1,"size":2,"hostname":"cpu02","sum":3,"valid":true}`',
                            'size=2、兩個 rank 在不同節點；每個 rank 貢獻 rank＋1（1 和 2），Allreduce 加總後兩個 rank 都拿到 sum=3'])
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
    兩個任務都在下方迷你終端完成；輸入指令後按「執行」（或 Ctrl＋Enter）。先做 array，再拿 array 的 JobID 做 dependency。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '05', 't1-array', get_t1, set_t1, title='t1｜送出一個 array 工作',
                   steps_md='1. `sbatch --array=0-2 --job-name=course-array --wrap "hostname; echo task $SLURM_ARRAY_TASK_ID"`，記下 JobID\n'
                            '2. `squeue --me` 看 `<JobID>_0`…`_2`\n'
                            '3. `sacct -j <JobID> --format=JobID,JobName,State,NodeList` 看每個 task 在哪個節點跑\n'
                            '4. 至少 3 個 task COMPLETED 後按「檢查」')
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '05', 't2-dependency', get_t2, set_t2, title='t2｜用 dependency 接在 array 後面',
                   steps_md='1. 先送一個 array（可以再做一次 t1 的指令），記下它的 JobID\n'
                            '2. 立刻送 `sbatch --dependency=afterok:<ArrayJobID> --job-name=course-after --wrap "echo done"`\n'
                            '3. `squeue --me`：array 還在跑時，它是 PENDING、Reason=Dependency\n'
                            '4. 兩者都 COMPLETED 後按「檢查」')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch --array=0-2 --job-name=course-array --wrap "hostname; echo task $SLURM_ARRAY_TASK_ID"',
                                    'sbatch --dependency=afterok:<ArrayJobID> --job-name=course-after --wrap "echo done"',
                                    'squeue --me', 'sacct -j <id> --format=JobID,JobName,State,NodeList'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '05', course_questions.QUESTIONS['05'], get_quiz, set_quiz)
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
    course_ui.closing(mo, '05', recheck.value)
    return


if __name__ == "__main__":
    app.run()
