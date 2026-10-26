import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="03｜寫好一個 sbatch：資源怎麼申請")


@app.cell
def _():
    import marimo as mo
    import course_jobs
    import course_progress
    import course_questions
    import course_ui
    import notebook_views
    return course_jobs, course_progress, course_questions, course_ui, mo, notebook_views


@app.cell
def _(course_ui, mo):
    get_token, set_token = course_ui.token_state(mo)
    get_ed_py, set_ed_py = course_ui.view_state(mo)
    get_ed_sh, set_ed_sh = course_ui.view_state(mo)
    get_t1, set_t1 = course_ui.view_state(mo)
    get_t2, set_t2 = course_ui.view_state(mo)
    get_t3, set_t3 = course_ui.view_state(mo)
    get_term, set_term = course_ui.view_state(mo)
    get_quiz, set_quiz = course_ui.view_state(mo)
    return (get_ed_py, get_ed_sh, get_quiz, get_t1, get_t2, get_t3, get_term, get_token,
            set_ed_py, set_ed_sh, set_quiz, set_t1, set_t2, set_t3, set_term, set_token)


@app.cell
def _(course_ui, get_quiz, get_t1, get_t2, get_t3, get_token, mo, set_token):
    course_ui.sidebar(mo, '03', get_token, set_token, get_t1, get_t2, get_t3, get_quiz)
    return


@app.cell
def _(course_ui, mo):
    course_ui.header(mo, '03',
                     learn=['`#SBATCH` 怎麼寫', '`--cpus-per-task`／`--mem`／`--time`／`--output` 的意思與怎麼估',
                            '用 sacct 看實際用量再調整'],
                     before=['完成第 02 章（會用 sbatch、squeue、sacct）', '左側已選好學習紀錄', '叢集 idle'])
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
            f'# TODO：輸出檔放在 {_dir} 底下，%j 代表 JobID，例如 {_dir}job-%j.out\n'
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
def _(course_paths, get_token, mo):
    get_token()
    _name, _dir = course_paths()
    mo.md(rf"""
    ## 概念

    ### 一個 sbatch 腳本的解剖
    平常用 Slurm 就是：自己寫 sbatch → 提交 → 只看自己的工作 → 依結果調整資源再重送。
    主機的 `shared/` 就是節點裡的 `/shared`，所有節點看到同一份；你的練習目錄是 `{_dir}`。

    ```bash
    #!/bin/bash
    #SBATCH --job-name={_name}
    #SBATCH --partition=cpu
    #SBATCH --cpus-per-task=1
    #SBATCH --mem=256M
    #SBATCH --time=00:05:00
    #SBATCH --chdir={_dir}
    #SBATCH --output={_dir}job-%j.out
    srun python3 {_dir}job.py
    ```

    | 行 | 意思 |
    | :--- | :--- |
    | `#!/bin/bash` | 第一行：用 bash 執行 |
    | `--job-name` | 工作名稱，squeue／sacct 都看得到；本課必須是 `{_name}` |
    | `--partition=cpu` | 排到哪個節點群（cpu 是預設，最多 30 分鐘） |
    | `--cpus-per-task=1` | 每個 task 幾個 CPU；單執行緒程式 1 個就夠 |
    | `--mem=256M` | 記憶體上限；超過會被 cgroup OOM-kill |
    | `--time=00:05:00` | 時間上限；超過會 TIMEOUT |
    | `--chdir` | 工作目錄（選填；本課終端已固定在練習目錄） |
    | `--output` | stdout 寫到哪；`%j` 會換成 JobID |
    | `srun python3 …` | 在 allocation 裡啟動一個 step |

    `#SBATCH` 開頭的行是給 Slurm 看的選項（對 bash 來說只是註解），必須寫在第一個指令之前。
    命令列選項會覆蓋腳本裡的 `#SBATCH`，例如 `sbatch --mem=512M job.sbatch`。
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 第一次怎麼估
    1. **先寬鬆但有上限**：第一次用 `--mem=1G`、`--time=00:10:00`、`--cpus-per-task=1`。
    2. **跑完看實際用量**：`sacct -j <JobID> --format=JobID,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS`。
       MaxRSS 記在 step 列（`<JobID>.0`、`.batch`），allocation 列永遠空白。
    3. **下一次收緊**：`--mem` 取 **1.3 × MaxRSS**、`--time` 取 **1.5 × Elapsed**，再**無條件進位成整數**——Slurm 的 `--mem` 不接受小數（`70.46M` 會得到 `Invalid --mem specification`，要寫 `71M`）。

    | 申請太小 | 申請太大 |
    | :--- | :--- |
    | `--mem` 太小 → OUT_OF_MEMORY（第 07 章）；`--time` 太短 → TIMEOUT | 排隊更久，也佔住別人能用的資源 |

    多給 CPU 只有在程式真的會平行時才有用；單執行緒 Python 給 4 個 CPU 也不會變快。
    """)
    return


@app.cell
def _(course_jobs, course_ui, get_token, mo, notebook_views):
    _token = get_token()
    if not _token:
        _out = mo.vstack([mo.md('### 常見錯誤長什麼樣'), course_ui.need_token(mo)])
    else:
        _parts = [mo.md('### 常見錯誤長什麼樣\n以下是真實的 Slurm 輸出，以及本頁的檢查器會怎麼說。')]
        for _i, _ex in enumerate(course_jobs.mistake_examples(_token), 1):
            _parts.append(mo.vstack([
                mo.md(f"#### {_i}. {_ex['title']}\n\n{_ex['what']}\n\n```text\n{_ex['slurm']}\n```"),
                notebook_views.result_table(mo, _ex['grader_items'], title='檢查器的判斷'),
            ]))
        _out = mo.vstack(_parts)
    _out
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 換你練習
    在下面兩個編輯器寫好程式與 sbatch，按儲存後檔案會出現在你的練習目錄；再用終端提交。
    """)
    return


@app.cell
def _(course_ui, editor_note, get_ed_py, get_token, mo, set_ed_py):
    _template = '''import os
import socket
import time

# TODO：配置約 50 MiB 的記憶體，並真的寫入（只配置不寫入，記憶體不一定會被算進來）
data = bytearray(50 * 1024 * 1024)
for offset in range(0, len(data), 4096):
    data[offset] = 1

# TODO：停 3 秒，讓你有時間用 squeue --me 看到它
time.sleep(3)

# TODO：印出在哪個節點跑、JobID 是多少
print('hostname', socket.gethostname())
print('SLURM_JOB_ID', os.environ.get('SLURM_JOB_ID'))
'''
    course_ui.file_editor(mo, get_token(), 'job.py', get_ed_py, set_ed_py, language='python', template=_template,
                          note=editor_note('job.py', 'job.sbatch'))
    return


@app.cell
def _(course_ui, editor_note, get_ed_sh, get_token, mo, sbatch_skeleton, set_ed_sh):
    course_ui.file_editor(mo, get_token(), 'job.sbatch', get_ed_sh, set_ed_sh, language='bash',
                          template=sbatch_skeleton('job.py'), note=editor_note('job.py', 'job.sbatch'))
    return


@app.cell
def _(course_paths, course_ui, get_t1, get_token, mo, set_t1):
    _name, _dir = course_paths()
    course_ui.task(mo, get_token(), '03', 't1-files', get_t1, set_t1, title='t1｜寫好 job.py 與 job.sbatch',
                   steps_md=f'1. 在上面兩個編輯器填好 TODO，各按一次儲存\n'
                            f'2. `job.sbatch` 必須有 `#!/bin/bash`、`--job-name={_name}`、`--mem`、`--time`、'
                            f'`--output`（放在 `{_dir}` 底下）、`--cpus-per-task`，並用 `srun` 執行 `job.py`\n'
                            '3. `--chdir` 可以不寫\n'
                            '4. 按「檢查」，✗ 的那列會告訴你缺什麼')
    return


@app.cell
def _(course_jobs, get_token, mo):
    _token = get_token()
    if _token:
        _py, _sh = course_jobs.reference_files(_token)
        _ref = mo.accordion({'看參考解答（先自己試過再開）': mo.md(
            f'**job.py**\n\n```python\n{_py}```\n\n**job.sbatch**\n\n```bash\n{_sh}```')})
    else:
        _ref = mo.md('')
    _ref
    return


@app.cell
def _(course_ui, get_term, get_token, mo, set_term):
    course_ui.terminal(mo, get_token(), get_term, set_term, mode='user',
                       suggestions=['sbatch job.sbatch', 'squeue --me',
                                    'sacct -j <JobID> --format=JobID,State,ExitCode,Elapsed,Timelimit,ReqMem,MaxRSS',
                                    'cat job-<JobID>.out'])
    return


@app.cell
def _(course_ui, get_t2, get_token, mo, set_t2):
    course_ui.task(mo, get_token(), '03', 't2-first', get_t2, set_t2, title='t2｜第一次提交',
                   steps_md='1. 在終端輸入 `sbatch job.sbatch`，輸入後按「執行」（或 Ctrl＋Enter），記下 JobID\n'
                            '2. 用 `squeue --me` 等它跑完，再 `cat job-<JobID>.out` 看輸出\n'
                            '3. 把 JobID 貼到下面再按「檢查」；通過時會給你下一次 `--mem`／`--time` 的建議',
                   ask='JobID')
    return


@app.cell
def _(course_ui, get_t3, get_token, mo, set_t3):
    course_ui.task(mo, get_token(), '03', 't3-second', get_t3, set_t3, title='t3｜照建議收緊資源再送一次',
                   steps_md='1. 依 t2 的建議修改 `job.sbatch` 的 `--mem`（約 1.3 × MaxRSS，進位成整數，例如 `71M`）與 `--time`（約 1.5 × Elapsed），儲存\n'
                            '2. 再 `sbatch job.sbatch`，等它 COMPLETED\n'
                            '3. 貼上第二個 JobID 按「檢查」；縮太緊會 OOM，縮太少會被提醒還能再省',
                   ask='JobID')
    return


@app.cell
def _(course_questions, course_ui, get_quiz, get_token, mo, set_quiz):
    course_ui.quiz(mo, get_token(), '03', course_questions.QUESTIONS['03'], get_quiz, set_quiz)
    return


@app.cell
def _(course_ui, mo):
    recheck = course_ui.recheck_button(mo)
    mo.vstack([mo.md('## 收尾\n本章沒有示範工作；確認你的練習工作都結束了、叢集是乾淨的再往下走。'), recheck])
    return (recheck,)


@app.cell
def _(course_ui, mo, recheck):
    course_ui.closing(mo, '03', recheck.value)
    return


if __name__ == "__main__":
    app.run()
