import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="06｜GPU 與容器")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_ui
    from lessons_gpu import get_lesson
    compute = get_lesson('06-container-gpu')
    isolation = get_lesson('06-gpu-isolation')
    lessons = [compute, isolation]
    return compute, course_diagrams, course_questions, course_ui, isolation, lessons, mo


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_actions, set_actions = course_ui.actions_state(mo)
    get_dg, set_dg = course_ui.diagram_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_actions,
        get_dg,
        get_quiz,
        get_t1,
        get_term,
        get_token,
        set_actions,
        set_dg,
        set_quiz,
        set_t1,
        set_term,
        set_token,
    )


@app.cell
def _(course_ui, get_quiz, get_t1, get_token, mo, set_token):
    course_ui.sidebar(mo, '06', get_token, set_token, get_t1, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '06',
                     learn=['GPU 怎麼申請（partition + GRES）', '沒申請 GRES 為什麼用不到 GPU', '容器 image 怎麼跟 Slurm 一起用'],
                     before=['完成第 02 章（會提交與查看工作）', '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念：GPU 是一種 GRES
    CPU 與記憶體每個節點都有；GPU 只有某些節點有，Slurm 把它當成「一般資源」（GRES, Generic RESource）另外管理。
    本 lab 只有 gpu01 有一張 GPU，放在 `gpu` partition。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg, mo, set_dg):
    course_ui.animated(mo, course_diagrams.GPU_GRES, get_dg, set_dg)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 容器
    本 lab 用 Pyxis 外掛讓 Slurm 直接在容器裡跑工作：

    ```bash
    srun --partition=gpu --gres=gpu:1 --container-image=/shared/images/gpu-job.sqsh <image 裡的程式>
    ```

    - `--container-image=/shared/images/gpu-job.sqsh`：image 放在 `/shared`，每個節點都讀得到同一份。
    - 程式與 CUDA 函式庫在 image 裡；**CUDA driver 來自主機（節點）**，所以容器版和直接執行算出同樣的結果。
    - 容器不會繞過 Slurm：沒申請 `--gres=gpu:1`，容器裡一樣開不了 GPU。
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
def _(compute, controls, course_ui, mo, runs, states):
    (course_ui.demo(mo, compute, runs.get(compute['chapter']), 'direct', controls, states.get(compute['chapter']),
                    what='申請 `--gres=gpu:1`，直接在 gpu01 跑 CUDA vector-add',
                    why='先看正常的樣子：申請了 GPU，程式就能在 GPU 上算。',
                    watch='「工作輸出 direct-<JobID>.out」：三段 JSON，依序是 gpu_environment、gpu_device、gpu_compute。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            'gpu_environment：`"hostname": "gpu01"`、`"image": null`（直接在節點上跑，沒有容器）、`"CUDA_VISIBLE_DEVICES": "0"`',
                            'gpu_device：`"name": "NVIDIA GeForce RTX 4070 SUPER"`、`"visible_devices": 1`（只看得到申請到的一張）',
                            'gpu_compute：`"kernel": "vector_add"`、`"elements": 65539`、`"status": "PASS"`：真的在 GPU 上算完並驗證'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(compute, controls, course_ui, mo, runs, states):
    (course_ui.demo(mo, compute, runs.get(compute['chapter']), 'container', controls, states.get(compute['chapter']),
                    what='同一個程式改在容器 image 內跑（`container-gpu.sbatch`）',
                    why='容器把程式與函式庫打包；driver 用主機的，結果應該一樣。',
                    watch='「工作輸出 container-<JobID>.out」，跟上一張卡片逐段比較。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            'gpu_environment 的 `"image"` 不再是 null，而是作業映像；`"executable": "/usr/local/bin/python3"`（映像裡的 Python）',
                            'gpu_compute 一樣是 `"status": "PASS"`，`"result_sha256"` 跟直接執行完全相同：同一個程式、同一個答案'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'deny-direct', controls, states.get(isolation['chapter']),
                    what='同樣排到 gpu01，但**不申請** `--gres`，跑同一個程式',
                    why='證明「看得到裝置名稱」不等於「能用」：cgroup 沒開放 /dev/nvidia0 給這個 job，開裝置會被拒絕。',
                    watch='工作輸出的 JSON：`device_denied` 與 `errno`。',
                    expect=['工作本身 COMPLETED（探測程式正常結束，它的任務就是回報被拒絕）',
                            '輸出 `{"device_denied": true, "errno": 1, ...}`：errno 1 是 EPERM，沒有權限開 /dev/nvidia0'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'absent-cpu01', controls, states.get(isolation['chapter']),
                    what='在 cpu01 找 GPU',
                    why='CPU 節點根本沒有 GPU；GPU 工作一定要送到對的 partition。',
                    watch='工作輸出的 JSON：`hostname` 與 `gpu_device_absent`。',
                    expect=['輸出 `{"hostname": "cpu01", "gpu_device_absent": true}`：cpu01 根本沒有 /dev/nvidia0',
                            'State COMPLETED（檢查本身成功）'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 進階（選做）：GPU 排隊
    下面五步示範：容器一樣受 GRES 限制、cpu02 也沒有 GPU，以及唯一的 GPU 被佔用時第二個 GPU 工作會排隊。
    收尾的「驗證並保存」需要這一組（隔離）示範的**全部**步驟都做完；只想清理的話直接按「只清理本次實驗」即可。
    """)
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'deny-container', controls, states.get(isolation['chapter']),
                    what='在容器裡、不申請 GRES 跑 GPU 程式',
                    why='容器不會繞過 Slurm 的裝置隔離。',
                    watch='「工作輸出 deny-container-<JobID>.out」。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0（探測程式正常結束）',
                            '輸出 `{"device_denied": true, "errno": 1, "uid": 1000}`：跟直接執行一樣被拒絕，換成容器也繞不過 cgroup'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'absent-cpu02', controls, states.get(isolation['chapter']),
                    what='在 cpu02 找 GPU',
                    why='確認另一個 CPU 節點也沒有 GPU 裝置。',
                    watch='「工作輸出 absent-cpu02-<JobID>.out」。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0（檢查本身成功）',
                            '輸出 `{"hostname": "cpu02", "gpu_device_absent": true}`：cpu02 上根本沒有 /dev/nvidia0'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'holder', controls, states.get(isolation['chapter']),
                    what='提交一個佔住 GPU 120 秒的容器工作（holder）',
                    why='lab 只有一張 GPU；先佔住它，才能看到下一個 GPU 工作排隊。',
                    watch='狀態徽章，與「工作輸出 holder-<JobID>.out」。',
                    expect=['狀態：等待輸出 marker → 執行中 — job <JobID> RUNNING（holder 只會佔 120 秒）',
                            '輸出出現 `GPU_HELD`：它已經拿到 gpu01 唯一的那張 GPU'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'waiter', controls, states.get(isolation['chapter']),
                    what='再提交一個也要 `--gres=gpu:1` 的工作（waiter）',
                    why='GPU 已被 holder 佔用，waiter 只能等。',
                    watch='狀態徽章，與下方「我的工作」表 waiter 的 NODELIST(REASON) 欄。',
                    expect=['狀態：等待 scheduler — job <JobID> PENDING，Reason=Resources（GPU 只有一張，被 holder 佔著）',
                            '還沒有工作輸出'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, isolation, mo, runs, states):
    (course_ui.demo(mo, isolation, runs.get(isolation['chapter']), 'cancel-holder', controls, states.get(isolation['chapter']),
                    what='用 `scancel` 取消 holder',
                    why='GPU 釋放後，排程器會讓 waiter 開始。',
                    watch='這張卡片沒有輸出（scancel 成功時不印東西）；看上面 holder 與 waiter 兩張卡片的狀態。',
                    expect=['這張卡片：已完成，指令沒有 stdout',
                            'holder 卡片：已結束 CANCELLED',
                            'waiter 卡片：幾秒內開始，最後已結束 COMPLETED，輸出同樣是 `"status": "PASS"`'])
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
    在下方迷你終端完成；輸入指令後按「執行」（或 Ctrl＋Enter）。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '06', 't1-gpu-job', get_t1, set_t1, title='t1｜自己申請一張 GPU',
                   steps_md='1. `sbatch --partition=gpu --gres=gpu:1 --job-name=course-gpu --wrap "nvidia-smi -L"`，記下 JobID\n'
                            '2. `squeue --me` 等它結束（幾秒）\n'
                            '3. `cat slurm-<JobID>.out`，應該看到 `GPU 0: ...`\n'
                            '4. 按「檢查」：會確認 Partition=gpu、申請了 `gres/gpu=1`、COMPLETED，且輸出含 `GPU 0`')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch --partition=gpu --gres=gpu:1 --job-name=course-gpu --wrap "nvidia-smi -L"',
                                    'squeue --me', 'cat slurm-<JobID>.out'])
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '06', course_questions.QUESTIONS['06'], get_quiz, set_quiz)
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
    course_ui.closing(mo, '06', recheck.value)
    return


if __name__ == "__main__":
    app.run()
