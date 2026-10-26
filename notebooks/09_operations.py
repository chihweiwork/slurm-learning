import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="09｜維運入門：DRAIN／RESUME 與何時停手")


@app.cell
def _():
    import marimo as mo
    import course_diagrams
    import course_questions
    import course_triage
    import course_ui
    from lessons_lifecycle import get_lesson
    drain = get_lesson('09-drain')
    recovery = get_lesson('09-recovery')
    lessons = [drain, recovery]
    return (
        course_diagrams,
        course_questions,
        course_triage,
        course_ui,
        drain,
        lessons,
        mo,
        recovery,
    )


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_actions, set_actions = course_ui.actions_state(mo)
    get_dg_drain, set_dg_drain = course_ui.diagram_state(mo)
    get_dg_comp, set_dg_comp = mo.state(1, allow_self_loops=True)
    get_term, set_term = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_t2, set_t2 = course_ui.view_state(mo)
    get_triage, set_triage = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (
        get_actions,
        get_dg_comp,
        get_dg_drain,
        get_quiz,
        get_t1,
        get_t2,
        get_term,
        get_token,
        get_triage,
        set_actions,
        set_dg_comp,
        set_dg_drain,
        set_quiz,
        set_t1,
        set_t2,
        set_term,
        set_token,
        set_triage,
    )


@app.cell
def _(course_ui, get_quiz, get_t1, get_t2, get_token, mo, set_token):
    course_ui.sidebar(mo, '09', get_token, set_token, get_t1, get_t2, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '09',
                     learn=['DRAIN／RESUME 做什麼、不做什麼', 'controller 重啟會不會弄丟工作', '什麼情況要停手找管理者'],
                     before=['完成第 04 章（會讀 Reason）', '左側已選好學習紀錄',
                             '叢集 idle（`sinfo` 全部 idle、沒有別人的工作）', '本章會改節點狀態並重啟 controller，請確定沒有別人在用這個 lab'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 1：DRAIN 不是關機
    維護節點前，管理者先把它設成 DRAIN：已經在跑的工作繼續跑完，新工作不再排上去。等維護完再 RESUME。
    `Reason` 欄寫下是誰、為什麼 DRAIN —— 這是唯一能判斷「這是不是我的」的線索。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_drain, mo, set_dg_drain):
    course_ui.animated(mo, course_diagrams.DRAIN_FLOW, get_dg_drain, set_dg_drain)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 概念 2：controller 重啟不會丟工作
    複習第 01 章的元件圖（下面停在第 2 步，可以按「下一步」走到第 7 步）：slurmctld 收到工作後，把佇列與工作狀態寫進狀態目錄；
    本 lab 這個目錄放在 `controller-state` volume，容器重啟後 slurmctld 從這裡讀回來。
    執行中的工作由各節點的 slurmd 繼續跑，結束時再向重新上線的 slurmctld 回報。
    """)
    return


@app.cell
def _(course_diagrams, course_ui, get_dg_comp, mo, set_dg_comp):
    course_ui.animated(mo, course_diagrams.COMPONENTS, get_dg_comp, set_dg_comp)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 停手規則
    遇到下列任一情況，**不要自己修**，把看到的輸出交給管理者：

    | 情境 | 判斷 |
    | :--- | :--- |
    | a. unknown receipt（按鈕送出但沒拿到 JobID） | 不可以重按；用唯一的 job name 查候選 JobID，交給管理者判斷，避免重複提交或編造編號。 |
    | b. Reason 所有權不符 | 節點的 Reason 不是你的 `demo-<run>`／`course-<代碼>`，就不能 RESUME 它——那是別人的維護。 |
    | c. 出現外部 job | `squeue` 有不認識的工作（別的 user 或名稱），不能取消、不能 DRAIN 它所在的節點。 |
    | d. controller 無法確認 | `scontrol ping` 不是 UP 或服務異常，代表核心管理器故障，只有本章自己觸發的重啟才可用「故障復原」。 |
    | e. account 標記不符 | `sacctmgr show account` 的 Description 不是你建立的，就不能刪。 |
    | f. 節點 DOWN／FAIL、slurmd 連不上 | 涉及容器、網路、munge 或 slurmd 本身，需要管理者看節點日誌。 |
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 到新站台先查什麼

    | 項目 | 本 lab | 正式叢集常見做法 | 要查什麼 |
    |------|--------|----------------|---------|
    | **指令入口** | `docker compose exec`（在 host 上執行容器內命令） | SSH 到登入節點，直接執行 `sbatch`、`squeue` 等 | 站台文件、登入節點名稱 |
    | **account enforcement** | 關閉（`AccountingStorageEnforce=none`）；自己建立即可使用 | 啟用 associations, limits, QoS；無 association 會被拒 | sacctmgr show associations；是否有 user=lab 的 default account |
    | **partition / QoS / 時間上限** | `cpu`／`gpu` 兩個 partition，MaxTime 30 分鐘、預設 5 分鐘 | 依站台有多種 partition 與 QoS，時限從數小時到數天不等 | `sinfo`、`scontrol show partition`、`sacctmgr show qos`、站台文件 |
    | **檔案系統** | `/shared` 是同一台主機的目錄，沒有配額、沒有自動清除 | 常分 home／scratch／project，各有配額與清除政策；大量 I/O 會影響全叢集 | 站台文件、`quota`／`df -h`；暫存放 scratch，不要在 home 跑大量 I/O |
    | **GPU** | 單張 NVIDIA RTX 4070 SUPER；無 MIG (Multi-Instance GPU)、無 MPS（Multi-Process Service）；`--gres=gpu:1` 取得獨佔 | 可能多卡、支援 MIG 或 MPS 分割、型號不一致；GPU 排程更複雜 | `nvidia-smi`；slurm.conf `Gres` 定義；MIG/MPS 政策文件 |
    | **權限** | 你能用 `docker compose exec -u root` 取得 root，所以可以 DRAIN、跑 sacctmgr（lab 本身沒有 sudo） | 只有管理員能 DRAIN、改 slurm.conf、改 sacctmgr；一般使用者沒有這些權限 | 站台文件；不要嘗試用 sudo 繞過權限 |
    | **軟體環境** | 無 module、無 conda 虛擬環境；直接跑 /usr/bin 與 venv | 通常提供 modules（`module load cuda/11.8`）或 conda 管理；apptainer 沙箱化 | `module avail`；`which python`；`conda env list` |
    | **登入節點規範** | 無登入節點（直接 docker exec）；lab 可以做小計算 | 登入節點只能用於編譯、遞交、輕量級工作；重計算必須上 compute nodes；違者遭 kill | 行為準則文件；`sinfo -R`（reserved nodes） |
    | **accounting 歷史保存期間** | controller 紀錄約 1 小時（MinJobAge=3600）；slurmdbd 歷史沒有設定 purge，保存到管理者清除 | 通常 30 天～1 年；長期追蹤成本與資源使用 | slurm.conf `MinJobAge`；`sacct` 與 `sacctmgr` 有無資料；計費政策 |
    | **維護窗口與通知** | 無定期維護；隨時可重啟 | 通常每週固定時間、提前 24h 通知；停機期間所有工作被殺 | 叢集公告、Slack/郵件、`motd`（message of the day） |
    | **最後一行** | **一律以本 lab 文件與教學為準** | **一律以站台文件與管理者為準** | 不懂就問、不盲目移植 |
    """)
    return


@app.cell
def _(course_ui, mo):
    refresh = course_ui.demo_refresh(mo)
    mo.vstack([mo.md('## 示範\n兩組示範都會用到 cpu01／cpu02，**請先把 DRAIN 示範做完（含 RESUME），再開始 controller 重啟示範**。'
                     '紅色按鈕要先輸入確認字串才會解鎖。'), refresh])
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
def _(mo):
    mo.md(r"""
    ### 示範 A：DRAIN／RESUME cpu02
    """)
    return


@app.cell
def _(controls, course_ui, drain, mo, runs, states):
    (course_ui.demo(mo, drain, runs.get(drain['chapter']), 'holder', controls, states.get(drain['chapter']),
                    what='在 cpu02 啟動一個會跑 180 秒的 holder',
                    why='DRAIN 時節點上要有執行中的工作，才看得出 DRAIN 不會打斷它。',
                    watch='狀態徽章與「工作輸出 holder-<JobID>.out」。',
                    expect=['狀態：等待輸出 marker → 執行中 — job <JobID> RUNNING，並顯示「holder 操作窗口約剩 N 秒」',
                            '輸出 `{"affinity": [2, 3, 10, 11], "hostname": "cpu02", ..., "started": true, ...}`：holder 佔滿 cpu02 的 4 個 CPU'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, drain, mo, runs, states):
    (course_ui.demo(mo, drain, runs.get(drain['chapter']), 'drain', controls, states.get(drain['chapter']),
                    what='把 cpu02 設成 DRAIN（需輸入 `DRAIN cpu02`）',
                    why='維護前讓節點不再接新工作，但不打斷執行中的。',
                    watch='這張卡片沒有 stdout（scontrol update 成功時不印東西）；節點狀態用下方終端的 `sinfo -R` 或 `sinfo -N -o "%N %t %E"` 看。',
                    expect=['這張卡片：已完成，沒有輸出',
                            '`sinfo -N -o "%N %t %E"`：`cpu02 drng demo-<run id>`——drng 是 draining：還有工作在跑、但不再收新工作',
                            'holder 卡片仍是執行中：DRAIN 不會殺掉正在跑的工作'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, drain, mo, runs, states):
    (course_ui.demo(mo, drain, runs.get(drain['chapter']), 'waiter', controls, states.get(drain['chapter']),
                    what='提交一個指定要 cpu02 的 waiter',
                    why='確認 DRAIN 的節點不會再接新工作。',
                    watch='狀態徽章，與下方「我的工作」表 waiter 的 NODELIST(REASON) 欄。',
                    expect=['狀態：等待 scheduler — job <JobID> PENDING，Reason=ReqNodeNotAvail…',
                            '「我的工作」表：`(ReqNodeNotAvail, May be reserved for other job)`：它指定要 cpu02，但 cpu02 在維護'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, drain, mo, runs, states):
    (course_ui.demo(mo, drain, runs.get(drain['chapter']), 'release-holder', controls, states.get(drain['chapter']),
                    what='保存 waiter 等待的證據，然後讓 holder 提前結束',
                    why='holder 跑完後 cpu02 仍是 DRAIN（DRAINED），waiter 依然不會開始。',
                    watch='這張卡片的「指令的 stdout」，以及上面 holder／waiter 卡片；節點狀態用 `sinfo -N -o "%N %t %E"`。',
                    expect=['指令的 stdout `{"operation": "release", "paths": [".../holder.release"]}`',
                            'holder 卡片：已結束 COMPLETED，輸出多一行 `"released": true`',
                            '`sinfo`：cpu02 從 `drng` 變成 `drain`（空了，但仍在維護）；waiter 卡片仍是 PENDING'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, drain, mo, runs, states):
    (course_ui.demo(mo, drain, runs.get(drain['chapter']), 'resume', controls, states.get(drain['chapter']),
                    what='RESUME cpu02（需輸入 `RESUME cpu02`）',
                    why='維護結束，讓節點重新接工作。',
                    watch='這張卡片沒有 stdout；看 waiter 卡片與 `sinfo -N -o "%N %t %E"`。',
                    expect=['這張卡片：已完成，沒有輸出',
                            '`sinfo`：`cpu02 idle none`（DRAIN 與 Reason 都清掉了）',
                            'waiter 卡片幾秒內變成已結束 COMPLETED，輸出 `{"affinity": [2], "hostname": "cpu02", ...}`'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 示範 B：重啟 controller
    DRAIN 示範完成後再開始。
    """)
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'completed', controls, states.get(recovery['chapter']),
                    what='提交一個基準工作並等它完成',
                    why='重啟後確認已完成的工作紀錄還查得到。',
                    watch='狀態徽章與「工作輸出 completed-<JobID>.out」。',
                    expect=['狀態：已結束 COMPLETED ExitCode=0:0',
                            '輸出 `{"affinity": [2], "hostname": "cpu02", ..., "sum": 50005000, "uid": 1000}`：重啟後要確認這筆紀錄與輸出都還在'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'holder', controls, states.get(recovery['chapter']),
                    what='啟動一個會跑 240 秒的 holder',
                    why='重啟時要有執行中的工作，才能看它是否被保留。',
                    watch='狀態徽章；StartTime 用下方終端 `squeue --me --format="%i %j %T %S"` 記下來。',
                    expect=['狀態：執行中 — job <JobID> RUNNING，並顯示「holder 操作窗口約剩 N 秒」（240 秒）',
                            '輸出第一行 `{"affinity": [0, 1, 8, 9], "hostname": "cpu01", ..., "started": true, ...}`',
                            '`squeue --me --format="%i %j %T %S"` 的 START_TIME 欄就是它的 StartTime'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'waiter', controls, states.get(recovery['chapter']),
                    what='排入一個等 holder 資源的 waiter',
                    why='重啟時也要有等待中的工作。',
                    watch='狀態徽章與「我的工作」表。',
                    expect=['狀態：等待 scheduler — job <JobID> PENDING，Reason=Resources；scheduler 預估 HH:MM:SS 開始（只是估計）',
                            '還沒有工作輸出'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'restart', controls, states.get(recovery['chapter']),
                    what='保存證據後重啟 controller 容器（需輸入 `RESTART controller`）',
                    why='看執行中與等待中的工作在 slurmctld 重啟後都還在。',
                    watch='「指令的 stderr」（docker compose 的進度訊息），以及重啟後的 `squeue --me --format="%i %j %T %S"` 與 `scontrol ping`。',
                    expect=['狀態：已完成；指令的 stderr：`Container slurm-playground-controller-1 Restarting` → `Started`（docker compose 把進度寫在 stderr，不是錯誤）',
                            '`scontrol ping`：`Slurmctld(primary) at controller is UP`',
                            '`squeue --me --format="%i %j %T %S"`：holder 仍 RUNNING，START_TIME 跟重啟前一模一樣；waiter 仍 PENDING'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'release-holder', controls, states.get(recovery['chapter']),
                    what='查核狀態有保存下來，然後釋放 holder',
                    why='資源釋放後 waiter 會開始，證明重啟後排程照常運作。',
                    watch='這張卡片的「指令的 stdout」，以及上面 holder／waiter 卡片。',
                    expect=['指令的 stdout `{"operation": "release", "paths": [".../holder.release"]}`',
                            'holder 卡片：已結束 COMPLETED，輸出多一行 `"released": true`',
                            'waiter 卡片：接著開始，最後已結束 COMPLETED'])
     if runs else course_ui.need_token(mo))
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 故障復原（只在 controller 起不來時）
    只有本次 run 自己觸發的重啟之後 controller 沒有回到 UP，才按這個按鈕（需輸入 `RESTORE controller`）；其他情況請停手找管理者。
    """)
    return


@app.cell
def _(controls, course_ui, mo, recovery, runs, states):
    (course_ui.demo(mo, recovery, runs.get(recovery['chapter']), 'restore', controls, states.get(recovery['chapter']),
                    what='啟動 controller 容器',
                    why='重啟示範失敗、controller 停著時的復原步驟。',
                    watch='`scontrol ping`。',
                    expect=['只有 controller 起不來時才需要；成功後 `scontrol ping` 是 `Slurmctld(primary) at controller is UP`'])
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
    在下方迷你終端（維運模式）親手 DRAIN 再 RESUME cpu02。輸入後按「執行」（或 Ctrl＋Enter）。
    這個終端只允許對 **cpu02** 做 DRAIN／RESUME，而且 DRAIN 的 Reason 必須以 `course-<你的代碼>` 開頭——這樣任何人都看得出是誰做的。
    做完一定要 RESUME，不要讓 cpu02 停在 DRAIN。
    """)
    return


@app.cell
def _(course_ui, get_t1, get_token, mo, set_t1):
    course_ui.task(mo, get_token(), '09', 't1-drain', get_t1, set_t1, title='t1｜DRAIN cpu02',
                   steps_md=f"1. `scontrol update NodeName=cpu02 State=DRAIN Reason=course-{get_token() or '<代碼>'}-practice`\n"
                            '2. `sinfo -R` 看 Reason 欄是你寫的字\n'
                            '3. `scontrol show node cpu02` 看 `State=IDLE+DRAIN`\n'
                            '4. **在 RESUME 之前**按「檢查」：cpu02 必須是 DRAIN，且 Reason 以你的 `course-<代碼>` 開頭')
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '09', 't2-resume', get_t2, set_t2, title='t2｜RESUME cpu02',
                   steps_md='1. **在終端執行** `scontrol update NodeName=cpu02 State=RESUME`——這一步才會真的解除維護\n'
                            '2. `sinfo -N -o "%N %t %E"` 確認 cpu02 是 `idle none`（不再是 `drain`）\n'
                            '3. `scontrol ping` 確認 controller UP（這只是健康檢查，不會改變節點）\n'
                            '4. 按「檢查」：cpu02 不再 DRAIN，而且 accounting 記得到你那段 DRAIN 的開始與結束時間')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    _code = get_token() or '<代碼>'
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='ops',
                       suggestions=[f'scontrol update NodeName=cpu02 State=DRAIN Reason=course-{_code}-practice',
                                    'sinfo -R', 'scontrol show node cpu02',
                                    'scontrol update NodeName=cpu02 State=RESUME', 'scontrol ping'])
    return


@app.cell
def _(course_triage):
    _keys = list(course_triage.DECISIONS)
    triage_questions = [
        {'id': f"triage-{_s['id']}",
         'prompt': f"**{_s['title']}**\n\n{_s['context']}\n\n```\n{_s['output']}\n```\n\n你的判斷？",
         'options': list(course_triage.DECISIONS.values()),
         'answer': _keys.index(_s['decision']),
         'explain': _s['explanation']}
        for _s in course_triage.SCENARIOS
    ]
    return (triage_questions,)


@app.cell
def _(mo):
    mo.md(r"""
    ## 事故判讀
    以下是靜態的輸出片段，不會碰叢集。每題判斷：可以繼續，還是該停手找管理者？（不計入完成條件，但成績會保存。）
    """)
    return


@app.cell
def _(course_ui, get_token, get_triage, mo, set_triage, triage_questions):
    course_ui.quiz(mo, get_token(), '09', triage_questions, get_triage, set_triage, key='triage', title='事故判讀')
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '09', course_questions.QUESTIONS['09'], get_quiz, set_quiz)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 收尾
    本章動過節點與 controller，離開前務必確認：**cpu02 不能停在 DRAIN**（`sinfo` 全部 idle）、**controller 必須是 UP**（`scontrol ping`）、
    沒有留下 holder／waiter。兩組示範各按「驗證並保存」再「只清理本次實驗」；清理會 RESUME 本次 run 自己 DRAIN 的節點。
    練習時你自己 DRAIN 的 cpu02，請在終端用 `State=RESUME` 還原。
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
    course_ui.closing(mo, '09', recheck.value)
    return


if __name__ == "__main__":
    app.run()
