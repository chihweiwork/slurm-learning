import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="10｜總結與綜合練習")


@app.cell
def _():
    import marimo as mo
    import course_progress
    import course_questions
    import course_ui
    import notebook_views
    return course_progress, course_questions, course_ui, mo, notebook_views


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_ed_py, set_ed_py = course_ui.view_state(mo)
    get_ed_sh, set_ed_sh = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_t2, set_t2 = course_ui.view_state(mo)
    get_t3, set_t3 = course_ui.view_state(mo)
    get_t4, set_t4 = course_ui.view_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (get_ed_py, get_ed_sh, get_quiz, get_t1, get_t2, get_t3, get_t4, get_term, get_token,
            set_ed_py, set_ed_sh, set_quiz, set_t1, set_t2, set_t3, set_t4, set_term, set_token)


@app.cell
def _(course_ui, get_quiz, get_t1, get_t2, get_t3, get_t4, get_token, mo, set_token):
    course_ui.sidebar(mo, '10', get_token, set_token, get_t1, get_t2, get_t3, get_t4, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '10',
                     learn=['從零把一個分析跑起來並調好資源', '處理一次失敗：讀懂 OOM 的證據', '留下乾淨的叢集'],
                     before=['完成第 03 章（sbatch 與資源估算）', '完成第 07 章（失敗排查）', '完成第 08 章（sacct）',
                             '左側已選好學習紀錄', '叢集 idle'])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 總結

    | 章 | 你學到的一句話 | 對應指令 |
    | :--- | :--- | :--- |
    | 00 | 先看叢集狀態，只動自己的工作 | `sinfo`、`squeue` |
    | 01 | slurmctld 排程、slurmd 執行、slurmdbd 留紀錄 | （概念） |
    | 02 | sbatch 排隊立刻回 JobID，srun 立刻跑並等結果 | `sbatch`、`srun`、`squeue --me`、`scancel <id>` |
    | 03 | 先寬鬆申請，再用 MaxRSS／Elapsed 收緊 | `#SBATCH --mem/--time`、`sacct -j <id>` |
    | 04 | PENDING 看 Reason：Resources、Priority、Dependency… | `squeue --format="%i %T %R"`、`sprio` |
    | 05 | array 跑多份輸入、dependency 串流程、MPI 跨節點 | `--array`、`--dependency=afterok:<id>`、`--nodes` |
    | 06 | GPU 是 GRES，沒申請就用不到 | `--partition=gpu --gres=gpu:1` |
    | 07 | OOM、TIMEOUT、CANCELLED 各層寫法不同；先看 State／ExitCode | `sacct --format=State,ExitCode,MaxRSS` |
    | 08 | 歷史與用量查 accounting；association = user × account | `sacct -u lab`、`sacctmgr show assoc` |
    | 09 | DRAIN 不是關機；看到不是自己的狀態就停手回報 | `scontrol update`、`sinfo -R`、`scontrol ping` |
    | 10 | 從寫腳本、估資源、處理失敗到收尾，一次走完 | 以上全部 |
    """)
    return


@app.cell
def _(course_progress, get_token):
    def course_paths():
        """(job name, container directory) for the current learner, or placeholders."""
        _token = get_token()
        if not _token:
            return 'course-<token>', '/shared/course/<token>/'
        return f'course-{_token}', course_progress.container_dir(_token)

    def sbatch_skeleton(program):
        _name, _dir = course_paths()
        return (
            '#!/bin/bash\n'
            f'# TODO：工作名稱必須是 {_name}\n'
            '#SBATCH --job-name=\n'
            '# TODO：記憶體上限，整數加單位（不能有小數，70.46M 要寫 71M），第一次先寬鬆，例如 1G\n'
            '#SBATCH --mem=\n'
            '# TODO：時間上限 HH:MM:SS，第一次例如 00:10:00（cpu partition 最多 30 分）\n'
            '#SBATCH --time=\n'
            f'# TODO：輸出檔放在 {_dir} 底下，%j 代表 JobID，例如 {_dir}capstone-%j.out\n'
            '#SBATCH --output=\n'
            '# TODO：單執行緒程式 1 個 CPU 就夠\n'
            '#SBATCH --cpus-per-task=\n'
            '# （選填）--chdir 可以不寫：終端已把工作目錄固定在你的練習目錄\n'
            '\n'
            f'# TODO：用 srun 執行程式，例如 srun python3 {_dir}{program}\n'
        )

    def editor_note(program, script):
        _name, _dir = course_paths()
        return (f'`{script}` 的工作名稱必須是 `{_name}`；`--output` 要放在 `{_dir}` 底下；'
                f'`--chdir` 可寫可不寫（寫的話必須等於 `{_dir}`）；srun 那行要執行 `{program}`。')
    return course_paths, editor_note, sbatch_skeleton


@app.cell
def _(mo):
    mo.md(r"""
    ## 綜合練習
    這次沒有填好的範本：自己寫 `capstone.py` 與 `capstone.sbatch`，提交、依用量收緊資源，
    再故意讓它失敗一次，用 sacct 讀懂證據。終端輸入後按「執行」（或 Ctrl＋Enter）。
    """)
    return


@app.cell
def _(course_ui, editor_note, get_ed_py, get_token, mo, set_ed_py):
    _template = '''import os
import random
import socket
import time

# TODO：產生 100 萬個隨機數字並算平均（約用 40 MiB 記憶體）
numbers = [random.random() for _ in range(1_000_000)]
print('mean', sum(numbers) / len(numbers))

# TODO：停 5 秒，讓你有時間用 squeue --me 看到它
time.sleep(5)

# TODO：印出在哪個節點跑、JobID 是多少
print('hostname', socket.gethostname())
print('SLURM_JOB_ID', os.environ.get('SLURM_JOB_ID'))
'''
    course_ui.file_editor(mo, get_token(), 'capstone.py', get_ed_py, set_ed_py, language='python', template=_template,
                          note=editor_note('capstone.py', 'capstone.sbatch'))
    return


@app.cell
def _(course_ui, editor_note, get_ed_sh, get_token, mo, sbatch_skeleton, set_ed_sh):
    course_ui.file_editor(mo, get_token(), 'capstone.sbatch', get_ed_sh, set_ed_sh, language='bash',
                          template=sbatch_skeleton('capstone.py'), note=editor_note('capstone.py', 'capstone.sbatch'))
    return


@app.cell
def _(course_paths, course_ui, get_t1, get_token, mo, set_t1):
    _name, _dir = course_paths()
    course_ui.task(mo, get_token(), '10', 't1-files', get_t1, set_t1, title='t1｜寫好 capstone.py 與 capstone.sbatch',
                   steps_md=f'1. 在上面兩個編輯器填好 TODO，各按一次儲存\n'
                            f'2. `capstone.sbatch` 必須有 `#!/bin/bash`、`--job-name={_name}`、`--mem`、`--time`、'
                            f'`--output`（放在 `{_dir}` 底下）、`--cpus-per-task`，並用 `srun` 執行 `capstone.py`\n'
                            '3. `--chdir` 可以不寫\n'
                            '4. 按「檢查」')
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch capstone.sbatch', 'squeue --me',
                                    'sacct -j <JobID> --format=JobID,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS',
                                    'cat capstone-<JobID>.out', 'sbatch --mem=20M capstone.sbatch'])
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '10', 't2-first', get_t2, set_t2, title='t2｜第一次提交',
                   steps_md='1. `sbatch capstone.sbatch`，記下 JobID\n'
                            '2. 等它跑完，`cat` 輸出檔確認有 mean、hostname、SLURM_JOB_ID\n'
                            '3. 貼上 JobID 按「檢查」，記下建議的 `--mem`／`--time`',
                   ask='JobID')
    return


@app.cell
def _(course_ui, get_t3, get_token, mo, set_t3):
    course_ui.task(mo, get_token(), '10', 't3-second', get_t3, set_t3, title='t3｜收緊資源再送一次',
                   steps_md='1. 依建議修改 `capstone.sbatch` 的 `--mem` 與 `--time`，儲存\n'
                            '2. 再 `sbatch capstone.sbatch`，等它 COMPLETED\n'
                            '3. 貼上第二個 JobID 按「檢查」',
                   ask='JobID')
    return


@app.cell
def _(course_ui, get_t4, get_token, mo, set_t4):
    course_ui.task(mo, get_token(), '10', 't4-failure', get_t4, set_t4, title='t4｜故意讓它 OOM，再用 sacct 說明',
                   steps_md='1. 用命令列覆蓋記憶體上限重送：`sbatch --mem=20M capstone.sbatch`（命令列選項會蓋過腳本裡的 `#SBATCH`）。'
                            '如果它還是 COMPLETED，表示程式用量低於 20M，把 `capstone.py` 的數字量加大（例如 300 萬個）再送一次\n'
                            '2. 等它結束，輸入 `sacct -j <JobID> --format=JobID,State,ExitCode,MaxRSS,ReqMem`\n'
                            '3. 自己說明：allocation 列（沒有點號）通常是 `FAILED`、step 列（`.0`／`.batch`）是 `OUT_OF_MEMORY 0:125`——'
                            '同一次 OOM 在兩層的寫法不同，不是兩個錯誤\n'
                            '4. 按「檢查」：需要有一個 OUT_OF_MEMORY 的工作，而且你用 sacct 查過它的 JobID')
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '10', course_questions.capstone(), get_quiz, set_quiz, title='綜合測驗')
    return


@app.cell
def _(course_ui, mo):
    recheck = course_ui.recheck_button(mo)
    mo.vstack([mo.md('## 收尾\n最後一次確認：你的工作都結束了、叢集是乾淨的。'), recheck])
    return (recheck,)


@app.cell
def _(course_ui, mo, recheck):
    course_ui.closing(mo, '10', recheck.value)
    return


@app.cell
def _(course_progress, get_quiz, get_t1, get_t2, get_t3, get_t4, get_token, mo, notebook_views):
    # Reading the view getters makes this cell re-run after every task check or quiz grading.
    get_t1(), get_t2(), get_t3(), get_t4(), get_quiz()
    _token = get_token()
    if not _token:
        _done = mo.md('')
    else:
        _progress = course_progress.load(_token)
        _required = notebook_views.chapter_entry('10')[3]
        if course_progress.chapter_status(_progress, '10', _required) == '完成':
            _done = mo.callout(mo.md(f'## 🎉 課程完成\n\n你的學習紀錄保存在 '
                                     f'`shared/course/{_token}/progress.json`。'), kind='success')
        else:
            _chapter = _progress['chapters'].get('10') or {}
            _tasks = _chapter.get('tasks') or {}
            _missing = [f'- 任務 `{t}` 還沒通過' for t in _required if not (_tasks.get(t) or {}).get('passed')]
            _quiz = _chapter.get('quiz')
            if not _quiz or _quiz.get('correct') != _quiz.get('total'):
                _missing.append('- 綜合測驗還沒全對')
            _done = mo.md('### 還差一點\n' + '\n'.join(_missing))
    _done
    return


if __name__ == "__main__":
    app.run()
