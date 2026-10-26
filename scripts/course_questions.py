"""Quiz bank per chapter; `answer` is the 0-based index of the correct option."""


def _q(id, prompt, options, answer, explain):
    return {'id': id, 'prompt': prompt, 'options': options, 'answer': answer, 'explain': explain}


QUESTIONS = {
    '01': [
        _q('01-1', '你輸入 `sbatch` 之後，誰決定工作在哪個節點跑？', ['slurmd', 'slurmctld', 'MariaDB', 'munge'], 1,
           '排程決策都在 slurmctld（controller）。slurmd 只負責在自己的節點上啟動與監看工作；MariaDB 存歷史；munge 只做認證。'),
        _q('01-2', '工作顯示 PENDING，Reason=Resources 的意思是？',
           ['現在沒有足夠的空閒 CPU／記憶體', '你沒有權限', '腳本有錯', '節點壞了'], 0,
           'Resources 表示符合條件的節點目前沒有足夠的空閒資源；等前面的工作結束就會開始。節點壞了會是 ReqNodeNotAvail 或 NodeDown。'),
        _q('01-3', '`sacct` 的 MaxRSS 記在哪一列？', ['allocation 列', 'step 列（例如 101.0）', '兩列都有', '都沒有'], 1,
           '記憶體是在 step 裡量的：MaxRSS 記在 101.batch、101.0 這種 step 列；沒有點號的 allocation 列永遠空白。'),
        _q('01-4', '小工作能在大工作前面先跑，是因為？',
           ['先來先服務', '回填：它會在大工作預計開始前結束', '它比較重要', '隨機'], 1,
           'backfill 排程器只讓「不會延後隊首工作預計開始時間」的小工作先跑，所以 --time 寫得準，小工作更容易被回填。'),
        _q('01-5', '`scontrol show job` 查不到一小時前結束的工作，為什麼？',
           ['紀錄被刪了', 'controller 只暫留 MinJobAge 秒，要用 sacct 查', '工作沒跑過', '需要 root'], 1,
           '本 lab 的 MinJobAge=3600：結束一小時後 controller 就從記憶體移除；歷史仍在 slurmdbd，用 sacct 查。'),
    ],
    '02': [
        _q('02-1', '`sbatch` 回傳的數字是？', ['PID', 'JobID', 'CPU 數', '結束碼'], 1,
           '`Submitted batch job 123` 的 123 是 JobID；之後 squeue、scontrol show job、sacct、scancel 都用它。'),
        _q('02-2', '`squeue` 看不到剛才的工作，最可能是？',
           ['被刪了', '已經結束，要用 sacct 查', '還沒提交成功', '需要重開頁'], 1,
           'squeue 只列還在排隊或執行中的工作；結束的工作用 sacct（或一小時內的 scontrol show job）查。'),
        _q('02-3', '`scancel -u lab` 會？',
           ['只取消最新的工作', '取消 lab 的所有工作，包括別的章節的', '什麼都不做', '需要 root'], 1,
           '-u 是篩選條件：符合的工作全部取消，包括你在別的分頁、別的章節正在用的工作。只用明確的 JobID 取消。'),
        _q('02-4', '`srun` 與 `sbatch` 的差別？',
           ['srun 立刻跑並等結果；sbatch 排隊、立刻回 JobID', '一樣', 'srun 只能 root', 'sbatch 只能跑 Python'], 0,
           'srun 會等到程式結束並把輸出直接印回來；sbatch 只把腳本交給排程器，立刻回傳 JobID，輸出寫到檔案。'),
    ],
    '03': [
        _q('03-1', '`--mem=128M` 的工作用了 300 MiB 會？',
           ['變慢', '被 cgroup OOM-kill，State 變 OUT_OF_MEMORY／FAILED', '自動加記憶體', '排隊'], 1,
           '--mem 是 cgroup 的硬上限；超過時 kernel 直接殺掉程序，step 列是 OUT_OF_MEMORY，allocation 列通常是 FAILED。'),
        _q('03-2', '`--cpus-per-task=4` 會讓單執行緒 Python 變快嗎？',
           ['會', '不會，程式要自己平行才有用', '只有在 GPU 節點會', '看 partition'], 1,
           'Slurm 只是保留 4 個 CPU 給你；單執行緒程式仍然只用 1 個，其餘 3 個閒置還讓別人等。'),
        _q('03-3', '`--output=/shared/course/cXXXX/job-%j.out` 裡的 `%j`？', ['使用者名稱', 'JobID', '節點名', '日期'], 1,
           '%j 會換成 JobID，所以每次提交的輸出檔不會互相覆蓋；array 工作常用 %A_%a。'),
        _q('03-4', '下一次 `--time` 怎麼估？', ['永遠 30 分', '上次 Elapsed 乘 1.2–1.5', '越短越好', '不用寫'], 1,
           '用實測 Elapsed 加 20–50% 餘裕：太短會 TIMEOUT，太長排隊比較久、也比較難被回填。'),
    ],
    '04': [
        _q('04-1', 'Reason=Priority 表示？',
           ['前面還有更優先的工作在等同樣資源', '資源不夠', '沒權限', '節點壞了'], 0,
           'Priority 表示排在你前面的工作會先拿到資源；隊首那個工作的 Reason 才是 Resources。'),
        _q('04-2', 'PENDING 工作顯示的 StartTime 是？', ['實際開始時間', '排程器的預估，會變', '提交時間', '結束時間'], 1,
           '那是 backfill 排程器依目前工作的 TimeLimit 算出的預估；前面工作提早結束或有新工作進來都會改變。'),
        _q('04-3', '要求 `--exclusive` 的工作會？',
           ['比較快', '獨佔整個節點，別的工作都得等', '不用排隊', '只能在 GPU 節點'], 1,
           '--exclusive 不跟別人共用節點：就算只用 1 CPU，整個節點都被保留，其他工作只能等或去別的節點。'),
    ],
    '05': [
        _q('05-1', '`--array=0-3%2`', ['4 個 task 同時跑', '4 個 task，最多同時 2 個', '2 個 task', '跑 2 次'], 1,
           '0-3 是 4 個 task（SLURM_ARRAY_TASK_ID 0～3），%2 限制同時最多 2 個在跑。'),
        _q('05-2', '`afterok` 的工作前面有一個 task FAILED，彙總會？',
           ['照跑', '永遠不會開始（本 lab 會被取消）', '跑一半', '變 RUNNING'], 1,
           'afterok 要求全部成功；有一個失敗就永遠不會滿足（DependencyNeverSatisfied），本 lab 設了 kill_invalid_depend 會直接取消它。'),
        _q('05-3', 'MPI 工作 `--nodes=2 --ntasks=2`',
           ['2 個節點各 2 task', '2 個節點各 1 task', '1 個節點 2 task', '只用 GPU 節點'], 1,
           '--ntasks 是總數：2 個 task 分到 2 個節點，各 1 個 rank。'),
    ],
    '06': [
        _q('06-1', '要用 GPU 一定要寫？',
           ['`--cpus-per-task=4`', '`--gres=gpu:1`（加對的 partition）', '`--mem=16G`', '`--exclusive`'], 1,
           'GPU 是 GRES（generic resource），要明確申請；本 lab 的 GPU 只在 gpu partition 的 gpu01。'),
        _q('06-2', '沒申請 GRES 的工作 `nvidia-smi -L` 看得到 GPU 名稱，CUDA 卻開不了，因為？',
           ['驅動壞了', 'cgroup 沒開放裝置權限', 'GPU 被別人用', 'image 錯'], 1,
           'slurmd 只在有申請 GRES 的 job cgroup 開放 /dev/nvidia0；看得到名稱不等於有權限打開裝置。'),
        _q('06-3', '容器裡的 CUDA driver 來自？', ['image', '主機（節點）', 'slurmctld', 'MariaDB'], 1,
           'image 只帶 CUDA runtime 與程式；driver 是節點核心模組與使用者層函式庫，由容器執行環境掛進來。'),
    ],
    '07': [
        _q('07-1', 'sacct 顯示 allocation `FAILED 1:0`、step `OUT_OF_MEMORY 0:125`，發生了？',
           ['兩個不同錯誤', '同一次 OOM 在兩層的寫法', '程式回傳 125', '記錄壞了'], 1,
           'kernel 殺掉的是 srun 啟動的 step（OUT_OF_MEMORY）；batch 腳本只看到 srun 回傳非零，所以 allocation 是一般的 FAILED 1:0。'),
        _q('07-2', 'State=TIMEOUT 要改？', ['`--mem`', '`--time`', '`--cpus-per-task`', 'partition'], 1,
           'TIMEOUT 是撞到 --time；先看 Elapsed，下次加 20–50%，或讓程式能分段續跑。'),
        _q('07-3', '`CANCELLED by 1000`', ['系統取消', 'UID 1000（lab）自己 scancel', 'OOM', '超時'], 1,
           'by 後面是執行 scancel 的 UID；1000 是 lab，也就是你自己。'),
        _q('07-4', '排查第一步看？', ['重送一次', 'sacct 的 State 與 ExitCode', '重啟 controller', '刪輸出檔'], 1,
           '先用 sacct 確認是哪一種失敗（OOM、TIMEOUT、程式錯誤），再去看輸出檔最後幾行找原因。'),
    ],
    '08': [
        _q('08-1', '一小時前結束的工作要查用量，用？', ['`squeue`', '`scontrol show job`', '`sacct`', '`sinfo`'], 2,
           'squeue 只有進行中的工作，scontrol 只暫留 MinJobAge 秒；sacct 從 slurmdbd 查歷史與 MaxRSS、Elapsed。'),
        _q('08-2', 'MaxRSS 空白最常見原因？',
           ['程式沒用記憶體', '工作還沒結束，或你看的是 allocation 列', 'accounting 壞了', '要 root'], 1,
           'MaxRSS 在 step 結束時寫入，而且只在 .batch／.0 等 step 列；加 -X（只看 allocation）就看不到。'),
        _q('08-3', '本 lab 的 sacct 歷史保存？', ['1 小時', '1 天', '直到管理者刪除資料庫', '重開頁就沒了'], 2,
           '本 lab 沒有設定 Purge*：資料留在 MariaDB 直到管理者清除，或 docker compose down --volumes。'),
    ],
    '09': [
        _q('09-1', 'DRAIN 一個節點，上面執行中的工作會？', ['立刻被殺', '繼續跑完', '暫停', '搬去別的節點'], 1,
           'DRAIN 只是「不再接新工作」；執行中的工作照常跑完，跑完後節點變成 DRAINED。'),
        _q('09-2', 'cpu02 的 Reason 是別人寫的，你應該？',
           ['RESUME 它', '不要動，回報', 'DRAIN 其他節點', '重啟 controller'], 1,
           'Reason 是維護的所有權標記；不是你的就是別人的維護或故障，RESUME 可能把工作送到正在修的機器。'),
        _q('09-3', 'controller 重啟後，PENDING 的工作？', ['消失', '還在佇列', '變 RUNNING', '變 FAILED'], 1,
           'slurmctld 把狀態存在 StateSaveLocation（本 lab 的 controller-state volume），重啟後讀回來，佇列與執行中的工作都在。'),
    ],
}


def capstone():
    """Chapter 10 review: the first question of chapters 02–09."""
    return [QUESTIONS[chapter][0] for chapter in ('02', '03', '04', '05', '06', '07', '08', '09')]
