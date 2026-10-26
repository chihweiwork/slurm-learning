import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="07｜失敗排查：OOM、TIMEOUT、取消")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    from lessons_lifecycle import get_lesson
    memory = get_lesson('07-memory')
    lifecycle = get_lesson('07-lifecycle')
    lessons = [memory, lifecycle]
    return course_diagrams, course_questions, course_ui, lessons, lifecycle, memory, mo


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
    course_ui.sidebar(mo, '07', get_token, set_token, get_t1, get_t2, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '07',
                     learn=['OOM、TIMEOUT、取消各留下什麼證據', 'ExitCode `A:B` 怎麼讀', '工作失敗時先看哪裡'],
                     before=['完成第 03 章（會寫 sbatch、會用 sacct）', '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：一次失敗會在好幾個地方留下紀錄
    同一個事件，程式、cgroup、step 列、allocation 列各有自己的寫法；看起來不一樣，並不矛盾。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg, mo, set_dg):
    course_ui.animated(mo, course_diagrams.FAILURE_LAYERS, get_dg, set_dg)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### ExitCode 怎麼讀
    `sacct` 的 ExitCode 寫成 `A:B`：**A** 是程式自己的結束碼，**B** 是讓它結束的訊號編號。

    | ExitCode | 意思 |
    | :--- | :--- |
    | `0:0` | 成功 |
    | `1:0` | 程式自己回傳 1（通常是程式錯誤，看 `.out`／`.err`） |
    | `0:9` | 被 SIGKILL（訊號 9）殺掉 |
    | `0:15` | 被 SIGTERM（訊號 15）終止，常見於 TIMEOUT 或 scancel |
    | `0:125` | step 因超過記憶體上限被 OOM-kill |

    ### 排查順序
    1. `sacct -j <id> --format=JobID,State,ExitCode,MaxRSS,Elapsed,Timelimit`：先看 State 與 ExitCode，allocation 列與 step 列都要看。
    2. 輸出檔最後 30 行：`tail -n 30 slurm-<id>.out`（有 `.err` 也看）。
    3. `scontrol show job <id>`：工作結束 1 小時內（MinJobAge）還查得到申請細節。
    4. 都看不出原因，帶著上面的證據問管理者。

    | State | 改什麼 |
    | :--- | :--- |
    | OUT_OF_MEMORY | 加大 `--mem`（參考 MaxRSS） |
    | TIMEOUT | 加大 `--time`（參考 Elapsed） |
    | CANCELLED by &lt;UID&gt; | 有人（常是你自己）scancel 了它 |
    | FAILED | 程式錯誤，看輸出檔 |
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
def _(controls, course_ui, memory, mo, runs, states):
    (course_ui.demo(mo, memory, runs.get(memory['chapter']), 'neighbor', controls, states.get(memory['chapter']),
                    what='先在 cpu01 啟動一個鄰居工作（180 秒）',
                    why='等一下要證明：別人的 OOM 只會殺掉超量的那個工作，同節點的鄰居不受影響。',
                    watch='狀態徽章，與「工作輸出 neighbor-<JobID>.out」。',
                    expect=['狀態：執行中 — job <JobID> RUNNING，並顯示「holder 操作窗口約剩 N 秒」',
                            '輸出 `{"affinity": [0], "hostname": "cpu01", ..., "started": true, ...}`：鄰居在 cpu01 佔 1 個 CPU'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, memory, mo, runs, states):
    (course_ui.demo(mo, memory, runs.get(memory['chapter']), 'offender', controls, states.get(memory['chapter']),
                    what='在同一節點跑一個 128 MiB 上限、卻要吃 200 MiB 的工作',
                    why='超過 `--mem` 時 cgroup 會把它 OOM-kill，這是最常見的失敗之一。',
                    watch='狀態徽章，以及「工作輸出 offender-<JobID>.err」的錯誤訊息。',
                    expect=['狀態：已結束 FAILED ExitCode=1:0——這是 allocation（整個工作）的結果：batch 腳本看到 srun 失敗',
                            'offender-<JobID>.err：`Detected 2 oom_kill events in StepId=<JobID>.0` 與 `srun: error: cpu01: task 0: Out Of Memory`',
                            '真正的原因在 step `.0`：之後用 `sacct -j <JobID>` 會看到 `OUT_OF_MEMORY 0:125`',
                            'offender-<JobID>.out 第二段 `"event": "oom_observation"`：`memory.max` 是 134217728（128 MiB）那層 job cgroup，`oom_kill` 從 0 變成 2',
                            'neighbor 卡片仍是執行中：隔壁的工作不受影響'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, memory, mo, runs, states):
    (course_ui.demo(mo, memory, runs.get(memory['chapter']), 'release-neighbor', controls, states.get(memory['chapter']),
                    what='保存證據後讓鄰居結束',
                    why='確認 OOM 與鄰居存活的證據都留下了，再釋放資源。',
                    watch='這張卡片的「指令的 stdout」，以及上面 neighbor 卡片。',
                    expect=['指令的 stdout `{"operation": "release", "paths": [".../neighbor.release"]}`',
                            'neighbor 卡片幾秒內變成已結束 COMPLETED，輸出多一行 `"released": true`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lifecycle, mo, runs, states):
    (course_ui.demo(mo, lifecycle, runs.get(lifecycle['chapter']), 'descendants', controls, states.get(lifecycle['chapter']),
                    what='提交 `--time=00:01:00`、會產生三代程序的工作',
                    why='看時間到時 Slurm 怎麼收尾：送 SIGTERM、等 KillWait，再清掉所有子孫程序。',
                    watch='卡片上的「狀態時間軸」，以及「工作輸出 descendants-<JobID>.out／.err」。',
                    expect=['時間軸：PENDING → RUNNING（約 77 秒，超過 1 分鐘的 TimeLimit 後才被處理）→ COMPLETING（幾秒）→ TIMEOUT',
                            '狀態：已結束 TIMEOUT ExitCode=0:15（被 signal 15 SIGTERM 結束）',
                            '.out 三行：`"role": "parent"`、`"child"`、`"grandchild"`，各有 pid：三代程序都在',
                            '.err：`*** JOB <JobID> ON cpu01 CANCELLED AT … DUE TO TIME LIMIT ***`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 進階（選做）
    確認失敗的工作被清乾淨後，同樣的 CPU 可以馬上重新使用（收尾的「驗證並保存」需要這兩步）。
    """)
    return


@app.cell
def _(controls, course_ui, memory, mo, runs, states):
    (course_ui.demo(mo, memory, runs.get(memory['chapter']), 'reuse', controls, states.get(memory['chapter']),
                    what='OOM 之後在 cpu01 申請獨佔整個節點',
                    why='證明 OOM 後資源已完全釋放。',
                    watch='狀態徽章與「工作輸出 reuse-<JobID>.out」。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            '輸出 `{"affinity": [0, 1, 8, 9], "hostname": "cpu01", ...}`：OOM 之後 cpu01 的 4 個 CPU 可以整台獨佔'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, lifecycle, mo, runs, states):
    (course_ui.demo(mo, lifecycle, runs.get(lifecycle['chapter']), 'reuse', controls, states.get(lifecycle['chapter']),
                    what='TIMEOUT 之後確認三代程序都消失，再重用四個 CPU',
                    why='證明時間限制到時，Slurm 連子孫程序也清乾淨了。',
                    watch='狀態徽章與「工作輸出 reuse-<JobID>.out」。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0（按下前，頁面已確認那三個 pid／starttime 都不在了）',
                            '輸出 `{"affinity": [0, 1, 8, 9], "hostname": "cpu01", ...}`：TIMEOUT 之後沒有殘留程序佔著 CPU'])
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
    在下方迷你終端自己製造兩種失敗；輸入指令後按「執行」（或 Ctrl＋Enter）。TIMEOUT 要等一分多鐘，可以先送出再去做 OOM。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '07', 't1-oom', get_t1, set_t1, title='t1｜製造一次 OOM',
                   steps_md='1. `sbatch --mem=50M --job-name=course-oom --wrap "python3 -c \'x=bytearray(200*1024*1024); import time; time.sleep(5)\'"`\n'
                            '2. 幾秒後 `sacct -j <id> --format=JobID,State,ExitCode,MaxRSS,Elapsed,Timelimit`\n'
                            '3. **寫下來**：allocation 列（`<id>`）的 State／ExitCode 是什麼？step 列（`<id>.batch`）呢？'
                            '兩列寫法不同，是同一次 OOM 在不同層的紀錄。\n'
                            '4. 按「檢查」：任一列 State 是 OUT_OF_MEMORY 就通過')
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '07', 't2-timeout', get_t2, set_t2, title='t2｜製造一次 TIMEOUT',
                   steps_md='1. `sbatch --time=00:01:00 --job-name=course-timeout --wrap "sleep 120"`\n'
                            '2. **要等大約 1 分鐘，再加上 KillWait 的收尾時間**；期間可以用 `squeue --me` 看它從 R 變 CG\n'
                            '3. `sacct -j <id> --format=JobID,State,ExitCode,MaxRSS,Elapsed,Timelimit`：Elapsed 會略超過 Timelimit\n'
                            '4. 按「檢查」：State 是 TIMEOUT 就通過')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch --mem=50M --job-name=course-oom --wrap "python3 -c \'x=bytearray(200*1024*1024); import time; time.sleep(5)\'"',
                                    'sbatch --time=00:01:00 --job-name=course-timeout --wrap "sleep 120"',
                                    'sacct -j <id> --format=JobID,State,ExitCode,MaxRSS,Elapsed,Timelimit',
                                    'tail -n 20 slurm-<id>.out'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '07', course_questions.QUESTIONS['07'], get_quiz, set_quiz)
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
    course_ui.closing(mo, '07', recheck.value)
    return


if __name__ == "__main__":
    app.run()
