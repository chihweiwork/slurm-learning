# Docker Compose Slurm GPU 實驗叢集

單機工作站上的真實 Slurm：`controller`、`cpu01`、`cpu02`、`gpu01`。計算節點是 Docker 容器；作業也可以使用獨立 Docker／OCI 映像，透過 Pyxis／Enroot 在 Slurm 資源配置內執行。

## 兩層容器

- Docker Compose 管理 Slurm 節點。
- Slurm 決定作業在哪個節點執行、配置哪些 CPU／RAM／GPU。
- Pyxis／Enroot 執行作業映像；不是在作業中呼叫主機 Docker daemon。
- `docker/job.Dockerfile` 是獨立 Debian/Python 映像，沒有 Slurm daemon；節點映像使用 Ubuntu。
- GPU 範例透過 CUDA Driver API 啟動 PTX vector-add kernel、同步、讀回並驗證全部 65,539 個元素；沒有 CPU fallback。顯式 GPU buffers 合計 786,468 bytes，另外會有 CUDA context／driver 開銷。

## 主機前提與安全

此設定針對已評估的 Ryzen 7 7700（8 核心／16 執行緒）、約 64 GB RAM、RTX 4070 SUPER 工作站。需 Docker Engine、Compose、NVIDIA Container Toolkit，以及能操作 Docker 的 UID 1000 使用者。

已經使用者核准：計算節點額外取得 `SYS_ADMIN`、`BPF`、`SYS_RESOURCE`、`SYS_NICE`、`SYS_PTRACE`，並在這些容器內放寬 seccomp／AppArmor。這是**高權限、可信工作專用的實驗環境**，不是多租戶安全沙箱。

`SYS_PTRACE` 於處理第 1 輪學員回饋時另行核准：slurmstepd 取樣 MaxRSS／AveCPU 需讀取作業程序的 `/proc/<pid>/io`；缺少此 capability 時讀取得到 EACCES，Slurm 捨棄全部 jobacct 取樣，`sacct` 的 MaxRSS 一律為空。只有加入後提交的工作才有 MaxRSS，先前的紀錄不會補回。

- 不使用 `privileged`、主機 Docker socket、host PID／network，或主機整棵可寫 cgroup 掛載。
- 每個計算節點使用 private cgroup namespace，只將自己的 cgroup 掛載重新設為可寫，由容器內 systemd 委派給 Slurm。
- 不改主機 Docker／NVIDIA 設定，不停止 Ollama 或其他既有服務。
- 只對 `gpu01` 提供 GPU；Slurm 不會阻止主機桌面／Ollama 同時使用同一張卡。執行測試前確認顯存餘裕。
- MUNGE 金鑰首次啟動由 `init` 寫入專用 Docker volume，僅 munge/root 可讀；不寫入 Git、共享工作目錄或作業映像。
- 節點不對主機發布連接埠。控制命令透過 `docker compose exec` 執行。

| 節點 | 主機 CPU IDs | 容器 RAM 上限 | 作業可排程 RAM | GPU |
| --- | --- | --- | --- | --- |
| controller | 6–7,14–15，最多 2 CPU 計算配額 | 2 GiB | 不執行作業 | 無 |
| cpu01 | 0–1,8–9 | 8 GiB | 7 GiB | 無 |
| cpu02 | 2–3,10–11 | 8 GiB | 7 GiB | 無 |
| gpu01 | 4–5,12–13 | 16 GiB | 14 GiB | 1 |

Slurm 保留真實主機的 16-thread 拓樸，透過 `CpuSpecList` 排除各節點不應排程的 CPU，所以應看 `CPUEfctv=4`，而不是將 `CPUTot=16` 誤認成超配。Slurm 抽象 CPU 編號為 core-major，與 Linux CPU IDs 不同；此處映射僅適用於目前工作站。主機既有程序仍可使用所有 CPU，並未被修改 affinity。

## 建置與啟動

```bash
bash scripts/up.sh
```

依序建立共享目錄、建置節點映像、初始化認證金鑰、啟動四個節點，再建置與轉換獨立 GPU 作業映像。

固定版本：Slurm 26.05.5、Pyxis 0.24.0、Enroot 4.2.1、節點內 libnvidia-container 1.19.1；選配 accounting 使用 MariaDB 11.4.13。基底映像使用 digest，原始碼／外部套件下載使用 SHA256 驗證。Ubuntu apt 相依套件使用當時的套件庫版本，完整安裝清單保存在映像的 `/usr/local/share/node-packages.txt`；這不等於所有套件已做 bit-for-bit snapshot pinning。

查看狀態與版本：

```bash
docker compose ps
docker compose exec -T controller sinfo -Nel
docker compose exec -T controller scontrol show nodes
docker compose exec -T controller srun --version
```

## marimo 學習介面（主機 Python）

使用 Python 3.12 與 uv，在專案根目錄建立獨立 `.venv`；不修改 Conda 或節點映像：

```bash
uv sync --locked
PYTHONPATH="$PWD/scripts" uv run --locked marimo run notebooks/ \
  --host 127.0.0.1 --port 2718 --headless --token --include-code --no-sandbox
```

開啟終端列出的帶 token loopback URL。Gallery 是 11 章課程（約 3–4 小時），依序：

| 章 | 標題 | 時間 |
| :--- | :--- | ---: |
| 00 | 從這裡開始（叢集現況、每章結構、安全規則、第一個 `sinfo`） | 10 分 |
| 01 | Slurm 架構與運作原理（動畫圖、排程模擬器；不碰叢集） | 30 分 |
| 02 | 基本用法：提交、查看、取消 | 30 分 |
| 03 | 寫好一個 sbatch：資源怎麼申請 | 30 分 |
| 04 | 排程與等待：為什麼我的工作在 PENDING | 25 分 |
| 05 | 平行與多節點：array、dependency、MPI | 30 分 |
| 06 | GPU 與容器 | 20 分 |
| 07 | 失敗排查：OOM、TIMEOUT、取消 | 25 分 |
| 08 | 用量與 accounting | 20 分 |
| 09 | 維運入門：DRAIN／RESUME 與何時停手 | 30 分 |
| 10 | 總結與綜合練習 | 30 分 |

側欄列出每章與狀態（✓ 完成＝必做任務全過且小測驗全對；第 00 章沒有測驗、第 01 章沒有任務；● 進行中、○ 未開始），
按「檢查」或「對答案」後立即更新，並在「本章：還差 …」列出還缺哪些任務或測驗。以原生連結保留 Gallery 的 `?file=...` 路由。
更新共用 Python helpers 後，需重啟 marimo server 才會載入修正；只刷新網頁不會重載已匯入的模組。

`marimo run --host 127.0.0.1` 印出的 URL 主機名是 `localhost`；以 `127.0.0.1` 與 `localhost` 文字比對的健康／就緒檢查可能誤判逾時。
確認 server 已啟動的方式：直接開啟終端印出的帶 token URL，或執行下列任一命令。

【只讀診斷】任何 HTTP 回應都代表 server 已啟動：

```bash
curl -sI http://127.0.0.1:2718/
```

【只讀診斷】確認 2718 埠正在監聽：

```bash
ss -ltn | grep 2718
```

run 模式可以閱讀程式，但不能編輯。需要編輯時，先停止上述 server，再執行：

```bash
PYTHONPATH="$PWD/scripts" uv run --locked marimo edit notebooks/ \
  --host 127.0.0.1 --port 2719 --headless --token --no-sandbox
```

埠被占用時不停止既有服務；以終端實際 URL 為準，或用 `--port` 換本機埠。
不分享 token；這是使用主機 Docker 權限的可信單一使用者介面，不要綁到公開網路介面。

從其他自己的裝置連線時，只綁 Tailscale 位址（tailnet 內才連得到），並保留 token；`--token-password` 可讓重啟後 token 不變：

```bash
PYTHONPATH="$PWD/scripts" uv run --locked marimo run notebooks/ \
  --host "$(tailscale ip -4)" --port 2720 --headless --token --token-password '<自訂 token>' --include-code --no-sandbox
```

頁面載入、篩選與刷新只查詢；提交與維運必須按明確操作按鈕。
關閉頁面不取消 Slurm 工作。執行 CLI 驗收前，先完成或清理 notebook 工作。
瀏覽器 WASM／靜態 HTML 不能替代此主機 backend；關閉 server 後不能操作叢集。

### 學習紀錄

側欄「開始新的學習紀錄」建立 `shared/course/<代碼>/`（代碼 `c` 開頭＋8 個十六進位字元）：`progress.json` 記錄各章任務、測驗與示範 run，
`terminal.jsonl` 是迷你終端每一行的完整紀錄，學員在頁面編輯器存的 `job.py`、`job.sbatch` 與工作輸出也在這裡（節點內路徑 `/shared/course/<代碼>/`）。
每一章用同一個紀錄；側欄下拉選單可切換，預設是最新建立的紀錄。`shared/` 被 Git 忽略，學習紀錄不會進版控；要重新開始，按「開始新的學習紀錄」或刪掉該目錄。
任務通過後不會被之後的「檢查」收回（例如第 09 章先 RESUME 再檢查 DRAIN 任務：改由 accounting 的 DRAIN 事件證明你做過）。

### 每章結構

每章固定六段：

1. **章首卡**：標題、時間、你會學到、開始前。
2. **概念**：文字＋SVG 動畫圖（`scripts/course_diagrams.py`）。預設自動播放；關掉後用「上一步／下一步」逐步看，下方顯示「第 i／n 步」與該步說明。第 01、04 章另有排程模擬器（`scripts/course_sim.py`）。
3. **示範**：按鈕執行固定指令（`scripts/lessons_*.py` 的步驟，經 `scripts/course_runner.py` 在背景執行）。每張卡片先寫「你要做什麼／為什麼／看哪裡」，再列出實際 argv 與逐段註解、
   四態徽章（尚未就緒／可執行／執行中／已消耗）、stdout 與工作輸出、「你應該看到」。狀態每 3 秒自動更新；按鈕建在不自動刷新的 cell，刷新不會吃掉點擊或確認字串。
4. **換你練習**：任務卡＋迷你終端＋「檢查」，結果是 ✓／✗ 唯讀表格與下一步提示（`scripts/course_tasks.py`）。
5. **小測驗**：單選，「對答案」後逐題對錯與解釋（`scripts/course_questions.py`）。
6. **收尾**：「驗證並保存」→「只清理本次實驗」→（想重做時）「重新開始示範」；卡片會寫出下一步。驗證要在工作結束後約 1 小時內（`MinJobAge`）按，過期查不到排程紀錄。
   唯讀收尾清單（`scripts/closing.py`）：自己的 active job、DRAIN／DOWN 與 Reason 所有權、`demo-*` account；有示範的章節（02、04–09）另查本章 run 是否清理、report 是否 passed。最後是下一章連結。
   示範卡片的 stdout 與工作輸出完整顯示在可捲動的框內（長行自動換行，JSON 自動排版），不會因自動刷新而收合。

### 迷你終端

`scripts/course_terminal.py`。一行一個指令，不經 shell：以 `docker compose exec -w /shared/course/<代碼>/` 在 controller 執行。
輸入後按「執行」（或 Ctrl＋Enter）。

- 拒絕引號外的 `|`、`;`、`&`、`<`、`>`、反引號與 `$(`。
- 以 `lab` 執行：`sinfo`、`squeue`、`sprio`、`sstat`、`sacct`、`hostname`、`scontrol show|ping`、`sbatch`（不得 `--uid`／`--chdir`；腳本路徑須在自己的目錄或 `/opt/lab/examples/`）、
  `srun`（不得 `--pty`，60 秒上限）、`scancel <JobID>`（不得 `-u`、`--me`、`-A`、`-p`、`-t`、`-n` 等篩選）、`sacctmgr show|list`、`cat`／`head`／`tail`／`ls`／`wc`／`pwd`（路徑同上）。
- 第 08 章（accounting 模式）另以 root 允許 `sacctmgr add|delete account name=course-<代碼>-<名稱>` 與對應的 `user name=lab account=…`。
- 第 09 章（ops 模式）另以 root 允許 `scontrol update NodeName=cpu02 State=DRAIN Reason=course-<代碼>…` 與 `State=RESUME`。

### 示範 run 與查詢邊界

每個學習紀錄、每個 lesson 一個 run：`shared/demos/<run-id>/`，參數在 `run.json` 凍結，run id 記在 `progress.json`。
每個固定步驟先取得 exclusive claim，再呼叫外部命令；重開頁面不重送。
claim 存在但沒有 receipt，或提交逾時，代表結果 **unknown**，不是可安全重試。
先以紀錄中的唯一 job name、UID、工作目錄與提交時間人工核對；不能自動收編或掃殺工作。
清理保留證據，只處理本次已登記且重新核對身分的 job IDs、仍屬本次 Reason 的 DRAIN 與本次 account。
第 09 章的維護按鈕要求先輸入 `DRAIN cpu02`、`RESUME cpu02`、`RESTART controller` 或 `RESTORE controller` 並按 Enter。
已結束工作在控制器只暫留 `MinJobAge`（3600 秒）；過期後，已啟用 accounting 時以 `sacct` 查詢（第 08 章）。

在專案根目錄執行單元回歸測試：

```bash
uv run --locked python -m unittest discover -s tests
```

## 提交 CPU 與 MPI 工作

以 `lab`（UID 1000）提交，不使用 root 執行計算工作：

```bash
docker compose exec -T -u lab controller sbatch /opt/lab/examples/cpu.sbatch
docker compose exec -T -u lab controller sbatch /opt/lab/examples/array.sbatch
docker compose exec -T -u lab controller bash /opt/lab/examples/dependency.sh
docker compose exec -T -u lab controller sbatch /opt/lab/examples/mpi.sbatch
docker compose exec -T -u lab controller squeue
```

輸出保存於主機 `shared/`。在所有節點，對應路徑皆為 `/shared`。

## CSV array 與失敗修復

Gallery 第 05 章直接提交 `examples/pipeline-worker.sbatch` 與
`examples/pipeline-aggregate.sbatch`，不以驗收程式替代操作。
`pipeline.py prepare --run-dir DIR` 只接受新目錄；四片 CSV 各 1000 筆，
`id=1..4000`、`value=2*id`。worker 僅讀自己的片，aggregate 拒絕缺片、
無效 JSON、錯誤索引／筆數／總和；成功 summary 為
`{"shards": 4, "row_count": 4000, "value_sum": 16004000}`。

成功與壞輸入模式使用不同 run。壞輸入章保留 afterok 等待者，
明確提交無 dependency 的缺片彙總並確認失敗，再取消等待者、修復輸入，
只重送 `--array=2`，最後提交新的 aggregate；不重跑已成功的三片。
所有輸入、partials、summary 與 stdout/stderr 保存於本次 `shared/demos/<run-id>/`。

## 提交真正的容器 GPU 工作

```bash
docker compose exec -T -u lab controller \
  sbatch --wait /opt/lab/examples/container-gpu.sbatch
```

觀察 `shared/container-gpu-<jobid>.out` 與 `.err`。成功紀錄應包含：

- `gpu_environment`：非 root UID、Slurm job 環境、作業 cgroup、受限 CPU affinity，以及獨立作業 image 的身份。
- `gpu_device`：實際 NVIDIA GPU 名稱與 PCI bus ID。
- `gpu_compute`：`status=PASS`、`kernel_launched=true`、`synchronized=true`、`verified_elements=65539`。

直接互動啟動相同映像：

```bash
docker compose exec -T -u lab controller bash -ec '
  export NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
  srun -p gpu --gres=gpu:1 -c 1 --mem=512M \
    --container-image=/shared/images/gpu-job.sqsh \
    --container-mounts=/shared:/shared --container-workdir=/shared \
    --no-container-mount-home --no-container-remap-root \
    /usr/local/bin/python3 /opt/gpu-job/gpu_compute.py
'
```

`--container-image` 由 Pyxis 提供。`NVIDIA_VISIBLE_DEVICES` 不是資源申請，也不能繞過 Slurm 的 GRES／cgroup 裝置限制。

### Docker image 如何進入 Slurm？

`python3 scripts/prepare-job-image.py` 會：

1. 建置 `slurm-playground/gpu-job:1`。
2. 在主機建立一個**不啟動**的暫時容器，以 `docker export` 匯出映像 rootfs。
3. 在控制節點轉成 Enroot 可讀取的 squashfs，保存於 `/shared/images/gpu-job.sqsh`。
4. 刪除暫時匯出容器與 tar；保存 image ID／轉換資訊於 `shared/images/gpu-job.json`。

這使用真實 Docker 映像，但執行 runtime 是 Enroot，不是 Docker Engine。`docker export` 不保留 Docker ENV／CMD／ENTRYPOINT metadata，因此本範例由 sbatch 明確提供命令與 NVIDIA 環境；不能假設任意映像的 ENTRYPOINT 會自動執行。映像內的程式及依賴保持在獨立 rootfs 中，不是把節點上的程式冒充成容器。

## 執行驗收

在沒有其他實驗作業占用節點時執行：

```bash
python3 scripts/smoke.py                # 完整 CPU、生命週期與容器 GPU 驗收
python3 scripts/smoke.py --section core # CPU／MPI／生命週期
python3 scripts/smoke.py --section gpu  # 直接 GPU、獨立映像 GPU、隔離與排隊
python3 scripts/smoke.py --list-cases
python3 scripts/smoke.py --case cpu-affinity
python3 scripts/smoke.py --case csv-pipeline-success --case csv-pipeline-failure-recovery
```

`--list-cases` 不呼叫 Docker、不建立結果目錄。`--case` 可重複，去重後依 catalog
順序執行，`nodes-partitions` 前置只做一次。`--case` 不可與 `--section` 或
`--skip-lifecycle` 混用；未知名稱在任何副作用前以 exit 2 拒絕。
報告標示選取範圍，只有包含全部 18 個 core＋gpu 案例且無 skip 的執行才標示完整套件。
選配的 `accounting-sacct-persistence` 不屬於完整套件，只能以 `--section accounting` 或 `--case` 明確執行。

完整驗收包含刻意超過 128 MiB job 限制的 OOM 工作，以及一分鐘時間限制測試；這些預期失敗是隔離驗收的一部分，不是要求主機耗盡記憶體。OOM 工作最多嘗試配置 256 MiB。

驗收會暫時 drain/resume `cpu02`、重啟本專案控制器、提交與取消自己的工作，不取消其他工作。`--skip-lifecycle` 可明確跳過 drain／控制器重啟，但這不是完整驗收。

每次產生 `shared/results/<run-id>/report.json`，包含命令、輸出、案例結果、失敗診斷與 cleanup 結果。core／gpu 驗收不依賴 accounting；已完成的 job 在控制器暫留至少一小時以利查驗，永久 `sacct` 歷史需啟用下方選配。

### 最終完整回歸（18 案例）

最新 `python3 scripts/smoke.py` **18/18 passed，cleanup_errors=[]**：
[完整套件報告](shared/results/20261018T071645Z-53bb15bc/report.json)。
獨立的 [CSV 選取報告](shared/results/20261018T072033Z-8955e709/report.json)
只包含一次 `nodes-partitions` 與兩個指定 CSV 案例，三者通過。
單案例、選取案例與完整套件的範圍分開標示，不用 CLI 結果代替下方 UI 操作證據。

回歸曾捕捉到多行 `SubmitLine` 導致文字解析漏掉 `WorkDir`；所有權核對改用 Slurm JSON，
保留嚴格的名稱／UID／工作目錄／SubmitTime 檢查，再完成上述全套回歸。
最後 `docker compose ps` 四個服務 healthy，三個計算節點 IDLE、每節點 CPUEfctv=4；
active queue 為空，沒有遺留 DRAIN/DOWN。驗證用 marimo server 與瀏覽器已關閉，
原有埠上服務、Ollama 與其他非本專案服務未停止或重啟。

### 原有叢集基線（16 案例）

已執行 `bash scripts/up.sh && python3 scripts/smoke.py`，**16 個案例全部通過，cleanup 無錯誤**。完整命令與證據：[驗收報告](shared/results/20261018T051635Z-8c19e082/report.json)。

- CPU affinity、128 MiB job OOM／相鄰工作存活、排隊、array／相依性、跨節點 MPI、取消／超時、drain／恢復與控制器狀態保存均通過。
- 獨立 Docker image 的 CUDA kernel 使用 RTX 4070 SUPER，全部 65,539 個元素驗證正確；程序 UID 為 1000。
- 容器化 GPU 程序從外層節點觀察仍位於對應 Slurm job cgroup，繼承 512 MiB 記憶體上限與單一 CPU affinity。
- 未申請 GPU 的直接／容器工作均被拒絕裝置存取；GPU 整卡排隊、取消程序清理與重新分配通過。
- 額外執行整個專案 `stop`／`up` 後，再提交公開範例 `container-gpu.sbatch` 成功（job 79）；[作業輸出](shared/container-gpu-79.out)。三個計算節點恢復 idle，佇列為空。

這些證據是本機執行產物，保存在被 Git 忽略的 `shared/`，不是跨機器的效能保證。既有 22 個容器（包含 Ollama）仍維持原本的執行時間，未被重啟。

### marimo 課程驗證

見「marimo 學習介面」；逐章瀏覽器驗收方式在 `PLAN.md` §7。

## 選配：slurmdbd＋MariaDB accounting

預設關閉。`config/slurm.conf` 以 `Include /etc/slurm/accounting.conf` 讀取切換檔：
預設掛載空的 `config/accounting-off.conf`；`compose.accounting.yaml` 改在四個 Slurm 節點掛載同一份
`config/accounting-slurmdbd.conf`（各節點 slurm.conf 雜湊一致），並加入 `mariadb`、`slurmdbd` 兩個服務。

```bash
printf 'COMPOSE_FILE=compose.yaml:compose.accounting.yaml\n' >> .env
bash scripts/up.sh
```

以被 Git 忽略的專案 `.env` 啟用，讓 scripts、notebook 與手動 `docker compose` 都使用同一組檔案。
不要只在某個 shell `export COMPOSE_FILE`：其他 shell 的 `docker compose up` 會用預設設定重建節點，
等於關閉 accounting。`up.sh` 偵測到 `slurmdbd` 服務時會：

1. 讓 `init` 在 `accounting-secret` volume 產生 DB 使用者與 root 密碼（各 64 hex，root 0400）；不寫入 Git、映像、`shared/` 或 log。
2. 依序啟動 `mariadb` → `slurmdbd` → 四個節點。`slurmdbd` 開機時把密碼附加到 `config/slurmdbd.conf` 範本，寫成容器內 0600 `slurm` 擁有的 `/etc/slurm/slurmdbd.conf`，再降權為 `slurm` 執行。
3. 執行 `scripts/accounting-init.sh`：等待 slurmctld 自動註冊 cluster `compose-lab`，冪等建立 account `lab` 與使用者 `lab` 的預設關聯；不刪改既有關聯。

| 服務 | cpuset（與 controller 共用） | CPU 配額 | RAM 上限 | 持久化 |
| --- | --- | --- | --- | --- |
| mariadb | 6–7,14–15 | 1 | 1.5 GiB | `accounting-db` volume |
| slurmdbd | 6–7,14–15 | 1 | 512 MiB | 無（狀態在 DB） |

兩者不發布主機連接埠。slurmdbd 只用僅限 `slurm_acct_db` 權限的 `slurm` DB 帳號；`AccountingStorageTRES` 另外記錄 `gres/gpu`。
`AccountingStorageEnforce=none`：關聯與用量只記錄、不限制提交；QOS／fair-share 需另行設定 enforcement 與 priority。
只有啟用後的工作會寫入資料庫，先前的歷史不會補回。MaxRSS／AveCPU 等 step 取樣另需計算節點具 `SYS_PTRACE`（見「主機前提與安全」）；加入前提交的工作在 `sacct` 中 MaxRSS 為空。
瀏覽器內的 `sacct` 查詢、`sacctmgr` 與本次專屬 account 實驗見 Gallery 第 08 章。
slurmdbd 啟動時對 `innodb_buffer_pool_size`（512M）的 not recommended 警告是 2 GiB 預算下的刻意取捨；MariaDB 的 io_uring EPERM 警告會自動退回一般 I/O。

```bash
docker compose exec -T -u lab controller sacct -X --starttime=now-1days \
  --format=JobID,JobName,Account,State,ExitCode,Elapsed,AllocTRES%40
docker compose exec -T controller sacctmgr show association format=cluster,account,user
python3 scripts/smoke.py --section accounting
```

驗收案例 `accounting-sacct-persistence` 建立本次專屬 account `smoke-<run 尾碼>` 與 `lab` 關聯，以該 account 提交工作，
核對 `sacct` 的 JobID、名稱、使用者、account、COMPLETED、`0:0`、WorkDir 與 cluster；重啟 `mariadb`、`slurmdbd`
（核對容器 StartedAt 改變）後紀錄與關聯仍在，再刪除並確認關聯消失。它屬於維護案例，`--skip-lifecycle` 會跳過；
失敗時 cleanup 只刪本次登記的 account。

實測（2026-10-24）：啟用 accounting 下完整 core＋gpu 回歸 **18/18 passed、cleanup_errors=[]**
（[報告](shared/results/20261024T041138Z-48f2ea3c/report.json)），其 39 個工作皆可由 `sacct` 查到；
[accounting 案例](shared/results/20261024T041054Z-4c12efa7/report.json) 通過。依下方步驟停用後
`AccountingStorageType` 為 `(null)`，[CPU／array 選取驗收](shared/results/20261024T041501Z-a5946444/report.json) 通過；
重新啟用後先前紀錄（job 285、333）仍在，[accounting 案例再次通過](shared/results/20261024T041556Z-af785846/report.json)。
另以備份檔 DROP 後還原 `slurm_acct_db`，重啟 slurmdbd 後 `sacct` 仍查得 job 285。

### 備份與還原

```bash
mkdir -p shared/accounting-backups
docker compose exec -T mariadb sh -ec 'MYSQL_PWD=$(cat /run/secrets/accounting/db-root-password) exec mariadb-dump --user=root --single-transaction --routines --databases slurm_acct_db' \
  > "shared/accounting-backups/slurm_acct_db-$(date -u +%Y%m%dT%H%M%SZ).sql"

# 還原：先停 slurmdbd，dump 內含 CREATE DATABASE 與各表 DROP/CREATE。
docker compose stop slurmdbd
docker compose exec -T mariadb sh -ec 'MYSQL_PWD=$(cat /run/secrets/accounting/db-root-password) exec mariadb --user=root' \
  < shared/accounting-backups/<file>.sql
docker compose start slurmdbd
```

密碼只經容器內環境變數傳遞，不出現在命令列參數。備份檔含作業與帳戶資料（不含密碼），存放在被 Git 忽略的 `shared/`。
slurmdbd 停止期間 slurmctld 會暫存紀錄，恢復後補送；不要在 slurmdbd 停止時刪除 `controller-state`。

### 升級與停用

升級步驟依 Slurm／MariaDB 官方順序整理，本專案尚未實際執行版本升級；停用流程已實測。

- 升級 Slurm：先備份；slurmdbd 必須先於 slurmctld／slurmd 升級。重建映像後依序執行
  `docker compose up -d --no-build --wait slurmdbd`，等 log 出現 `slurmdbd version ... started`（大版本會轉換資料表，不要中斷），
  再重建 controller 與計算節點。
- 升級 MariaDB：先備份，更新 `compose.accounting.yaml` 的 digest，重建 `mariadb` 後以 root 執行 `mariadb-upgrade`，再啟動 slurmdbd。
- 停用（保留 volume 與資料）：

```bash
docker compose rm -sf slurmdbd mariadb      # 仍在啟用狀態下執行
sed -i '/^COMPOSE_FILE=/d' .env
docker compose up -d --no-build --wait controller cpu01 cpu02 gpu01
```

## 停止與資料保存

```bash
docker compose stop
# 使用現有映像與狀態恢復：
docker compose up -d --no-build --wait controller cpu01 cpu02 gpu01
```

`stop` 保留容器與資料。`docker compose down` 移除本專案容器／網路，但保留命名 volume 與主機 `shared/`。控制器狀態保存在 `controller-state` volume；MUNGE 金鑰在 `munge-key` volume；啟用 accounting 時另有 `accounting-db`（資料庫）與 `accounting-secret`（DB 密碼）。計算中的程序不能跨計算容器停止／重建存活。

**只有要重設叢集狀態及認證金鑰時**才執行 `docker compose down --volumes`；此命令會刪除本專案上述 volume（啟用 accounting 時包含全部作業歷史與 DB 密碼），但不刪主機 `shared/`。不提供自動刪除作業輸出／其他 Docker 資源的操作，不使用全域 prune。重設後需再執行 `scripts/up.sh`。

## 故障排除

```bash
docker compose logs controller
docker compose exec -T cpu01 journalctl -u slurmd -u munge --no-pager -n 100
docker compose exec -T gpu01 slurmd -G
docker compose exec -T controller scontrol show job <jobid>
docker compose exec -T gpu01 systemctl status slurmd --no-pager
```

- cgroup 或 BPF 權限錯誤：檢查 Compose capabilities、安全設定及 private cgroup namespace；不要改成關閉 `task/cgroup`。
- `CPUEfctv`／affinity 不符：核對主機 CPU 拓樸與 `CpuSpecList`，不要用虛構拓樸壓過錯誤。
- GPU／顯存問題：先檢查主機 `nvidia-smi` 及其他 GPU 使用者；Slurm 的 GPU 配額不涵蓋主機 Ollama。
- Pyxis 啟動錯誤：檢查 job stderr、Enroot runtime 目錄及映像權限；Slurm 和 Pyxis 必須使用相符的編譯版本。
- Enroot 容器內 `/proc/self/cgroup` 顯示 `0::/` 是 namespace 視圖，不代表逃離 Slurm。驗收會從外層 `gpu01` 讀取仍在執行的 PID，核對其 Slurm job SLUID 與 512 MiB 記憶體上限，再驗證取消後該程序消失。
- 巢狀 NVIDIA `ldconfig`：本專案對固定版本 Enroot 套用 `docker/enroot-nested-ldconfig.patch`，改用映像內的 `/sbin/ldconfig`。原本的 host-relative loader 會嘗試額外掛載 `/proc`，被 Docker 預設遮蔽路徑保護拒絕；此修正保留該保護及 NVIDIA 的 privilege/seccomp 限制，不關閉錯誤檢查。GPU 作業映像必須提供可用的 `/sbin/ldconfig`，且只能執行可信映像。

accounting 問題：`docker compose logs slurmdbd mariadb`；`sacct` 回報無法連線時先確認兩者 healthy，slurmdbd 在資料庫未就緒時每 5 秒重試。
