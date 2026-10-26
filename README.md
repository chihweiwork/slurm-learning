# Slurm 實驗叢集（Docker Compose＋GPU）

本專案在單一工作站上以 Docker Compose 啟動多節點 Slurm 叢集，包含 `controller` 與計算節點 `cpu01`、`cpu02`、`gpu01`，並將一張 NVIDIA GPU 配給 `gpu01`。
工作可透過 Pyxis 與 Enroot 在獨立的 Docker 或 OCI 映像中執行；專案內建 11 章繁體中文 marimo 互動課程（00–10）與自動化驗收測試。

> **安全提醒：這是受信任的單人特權實驗環境，並非多租戶安全沙箱。**
> 計算節點具備額外 Linux capabilities 並放寬 seccomp 與 AppArmor 限制；所有服務皆不對宿主機發布網路連接埠。

## 主機需求

請先確認宿主機符合以下條件：
- Linux amd64 架構，且已啟用 cgroup v2。
- Docker Engine 與 Compose v2 外掛，且目前使用者可直接執行 `docker`。
- NVIDIA 驅動程式與 NVIDIA Container Toolkit，且 GPU 為裝置 0（`gres.conf` 固定使用 `/dev/nvidia0`）。
- **宿主機 UID 必須為 1000**，否則 `scripts/init.py` 會中止執行。
- CPU 拓撲固定為 8 核 16 緒（SMT 配對 0/8、1/9 …）；其他硬體需修改 `compose.yaml` 與 `config/slurm.conf`。
- 開發機：Ryzen 7 7700、64 GB RAM、RTX 4070 SUPER。
- 容器記憶體上限合計 34 GiB（2＋8＋8＋16 GiB），啟用 accounting 另需約 2 GiB。
- 宿主機具備 `python3`；互動課程另需 Python 3.12 與 `uv`。
- 建置映像時具備網際網路連線（存取 apt、GitHub 與 NVIDIA 套件庫）。
- 測過版本：Docker 29.8.2、Compose v5.6.0、NVIDIA Container Toolkit 1.12.1、Driver 580.173.02。

## 快速開始

在專案根目錄執行單一命令即可建置並啟動叢集：
```bash
bash scripts/up.sh
```

`scripts/up.sh` 會依序執行以下 5 個步驟，結束時印出 `sinfo -Nel` 節點表（`cpu01`、`cpu02`、`gpu01` 應為 `idle`）：
1. 建立 `shared/` 子目錄並檢查宿主機 UID。
2. 建置節點映像 `slurm-playground/node:26.05.5`。
3. 執行一次性 `init` 服務產生 MUNGE 金鑰（啟用 accounting 時一併產生資料庫密碼）。
4. 啟動 `controller`、`cpu01`、`cpu02`、`gpu01`（啟用 accounting 時先啟動 `mariadb` 與 `slurmdbd`，最後執行 `scripts/accounting-init.sh`）。
5. 建置 GPU 工作映像並由 `scripts/prepare-job-image.py` 轉換為 `shared/images/gpu-job.sqsh`。

檢查狀態：
```bash
bash scripts/ps.sh
docker compose exec -T controller sinfo -Nel
```

`scripts/up.sh` 可重複執行；切換 accounting 開關後請重跑。

## 開始上課（marimo 課程）

同步相依套件後，在專案根目錄啟動互動課程伺服器：
```bash
uv sync --locked
PYTHONPATH="$PWD/scripts" uv run --locked marimo run notebooks/ \
  --host 127.0.0.1 --port 2718 --headless --token --include-code --no-sandbox
```

開啟終端機印出的含 token 網址。網頁可操作宿主機的 Docker，請勿綁定公開網路介面或分享 token。

| 章 | 主題 | 分鐘 |
| --- | --- | --- |
| 00 | 從這裡開始 | 10 |
| 01 | Slurm 架構與運作原理 | 30 |
| 02 | 基本用法：提交、查看、取消 | 30 |
| 03 | 寫好一個 sbatch：資源怎麼申請 | 30 |
| 04 | 排程與等待：為什麼我的工作在 PENDING | 25 |
| 05 | 平行與多節點：array、dependency、MPI | 30 |
| 06 | GPU 與容器 | 20 |
| 07 | 失敗排查：OOM、TIMEOUT、取消 | 25 |
| 08 | 用量與 accounting（需啟用 accounting） | 20 |
| 09 | 維運入門：DRAIN／RESUME 與何時停手 | 30 |
| 10 | 總結與綜合練習 | 30 |

合計約 280 分鐘。
- 點擊側欄「開始新的學習紀錄」會建立 `shared/course/<代碼>/`，保存進度、終端機紀錄與學員檔案。
- 當章節必做任務全過且測驗全對時才會顯示「完成 ✓」（第 00 章無測驗，第 01 章無任務）。
- 頁內小型終端機不是 shell，每行僅允許一個白名單內的 Slurm 或唯讀命令。
- 練習時請以 `course-` 或 `demo-` 作為工作名稱前綴，且不要執行 `scancel -u lab`。

編輯教材：先停止 `marimo run`，再執行：
```bash
PYTHONPATH="$PWD/scripts" uv run --locked marimo edit notebooks/ \
  --host 127.0.0.1 --port 2719 --headless --token --no-sandbox
```
- 修改 `scripts/*.py` 輔助模組後須重啟 marimo 伺服器；只重新整理頁面無效。

## 叢集架構

叢集由 4 個常駐 Slurm 節點服務與一次性 `init` 服務組成：

| 節點 | 角色 | 主機 CPU | 記憶體上限 | GPU |
| --- | --- | --- | --- | --- |
| `controller` | slurmctld＋登入節點（不跑工作） | 6–7,14–15 | 2 GiB | — |
| `cpu01` | 計算 | 0–1,8–9 | 8 GiB | — |
| `cpu02` | 計算 | 2–3,10–11 | 8 GiB | — |
| `gpu01` | 計算 | 4–5,12–13 | 16 GiB | 1 |

叢集提供預設的 `cpu` partition（`cpu01`、`cpu02`）與 `gpu` partition（`gpu01`），兩者 MaxTime 皆為 30 分鐘、DefaultTime 皆為 5 分鐘。
- Docker Compose 負責管理外層的 Slurm 節點容器。
- Slurm 負責決定工作落在哪個節點，並分配 CPU 數量、記憶體與 GPU。
- GPU 工作透過 Pyxis 與 Enroot 載入獨立映像（`docker/job.Dockerfile` 轉為 `shared/images/gpu-job.sqsh`），不呼叫宿主機 Docker daemon。
- 啟用 accounting 時會額外啟動 `mariadb` 與 `slurmdbd`，與 `controller` 共用同一組主機 CPU（見下方 accounting 小節）。
- 版本：節點映像基於 Ubuntu 24.04，內建由固定原始碼編譯的 Slurm 26.05.5、Pyxis 0.24.0、Enroot 4.2.1；課程使用 marimo 0.25.1。

## 專案結構

```text
compose.yaml               # 4 個 Slurm 節點＋一次性 init
compose.accounting.yaml    # 選配：mariadb＋slurmdbd
config/                    # slurm.conf、cgroup.conf、gres.conf 等（唯讀掛載）
docker/                    # 節點映像 Dockerfile、boot.sh、GPU 工作映像 job.Dockerfile
examples/                  # 範例工作（節點內 /opt/lab/examples）
notebooks/                 # 00–10 章 marimo 課程
scripts/
  up.sh                    # 建置＋啟動
  ps.sh                    # 服務狀態
  smoke.py                 # 叢集驗收（gpu_smoke.py、pipeline_smoke.py 由它匯入）
  prepare-job-image.py     # 建置並轉換 GPU 工作映像
  accounting-init.sh       # accounting 初始帳號
  course_*.py lessons_*.py notebook_*.py …  # 課程 helper
tests/                     # helper 單元測試（不需叢集）
shared/                    # 執行期資料，Git 忽略；節點內 /shared
  images/  results/  course/  demos/
PLAN.md                    # 設計與驗收計畫
```

宿主機的 `./shared` 會掛載為每個節點內的 `/shared`，因此工作的輸出檔案會直接出現在宿主機的 `shared/` 目錄下。

## 手動提交工作

範例工作皆以 `lab` 使用者在 `controller` 上提交，格式為：
```bash
docker compose exec -T -u lab controller <命令>
```

| 範例 | 內容 | 命令 |
| --- | --- | --- |
| `cpu.sbatch` | 1 CPU、印出 affinity | `sbatch /opt/lab/examples/cpu.sbatch` |
| `array.sbatch` | 4 個 array task | `sbatch /opt/lab/examples/array.sbatch` |
| `dependency.sh` | 第二個工作 afterok 等第一個 | `bash /opt/lab/examples/dependency.sh` |
| `mpi.sbatch` | 跨 2 節點 MPI（PMIx） | `sbatch /opt/lab/examples/mpi.sbatch` |
| `memory-oom.sbatch` | **刻意**觸發 cgroup OOM | `sbatch /opt/lab/examples/memory-oom.sbatch` |
| `container-gpu.sbatch` | 在獨立映像內跑 GPU vector-add | `sbatch --wait /opt/lab/examples/container-gpu.sbatch` |

工作輸出會寫入 `shared/`，檔名格式為 `cpu-<jobid>.out`、`mpi-<jobid>.out` 等；CSV array pipeline 範例則於課程第 05 章介紹。

## 驗收與測試

**叢集驗收（需要叢集在跑）**
```bash
python3 scripts/smoke.py                   # core 12 案例＋GPU 6 案例
python3 scripts/smoke.py --list-cases      # 只列案例，不動叢集
python3 scripts/smoke.py --section core    # 或 gpu、accounting
python3 scripts/smoke.py --skip-lifecycle  # 跳過 drain/resume 與重啟 controller
```

- 請在叢集閒置時執行：測試會對 `cpu02` 執行 drain 與 resume 並重啟 `controller`（加 `--skip-lifecycle` 則報告狀態為 `partial`）。
- 結果寫入 `shared/results/<時間戳>-<8hex>/report.json` 並印出 `Evidence: <路徑>`；傳回 0 為通過、1 為失敗。
- accounting 案例僅在 `--section accounting` 時執行。

**單元測試（不需要叢集）**
```bash
uv run --locked python -m unittest discover -s tests
```

單元測試會驗證課程輔助模組（評分器、終端機、學習紀錄與排程模擬器），不需啟動 Docker 或瀏覽器。

## 選配：accounting（slurmdbd＋MariaDB）

基礎 `compose.yaml` 不會啟用 accounting；由 Git 忽略的 `.env` 檔案決定要載入哪些 Compose 設定檔：
```bash
# .env
COMPOSE_FILE=compose.yaml:compose.accounting.yaml
```

寫入後執行 `bash scripts/up.sh` 套用；用 `cat .env` 可確認是否已啟用。
- 請將 `COMPOSE_FILE` 寫入 `.env` 而非單次 `export`，否則其他 shell 的 `docker compose` 會在未帶 accounting 的狀態下重建節點。
- `scripts/up.sh` 偵測到 overlay 後會在 Docker volume 產生資料庫密碼，依序啟動 `mariadb`、`slurmdbd` 與各節點，並建立 `lab` account 與 `lab` 使用者。
- 若要停用 accounting，請從 `.env` 刪除該行設定，再重新執行 `bash scripts/up.sh`。

## 停止與重設

暫停（保留狀態）：
```bash
docker compose stop                                                  # 停止
docker compose up -d --no-build --wait controller cpu01 cpu02 gpu01  # 用現有映像恢復
```

徹底重設（刪除 volumes）：
```bash
docker compose down --volumes
```

這會刪除 `controller-state`、MUNGE 金鑰與 accounting 資料庫及密碼，但不動宿主機 `shared/`；之後須重跑 `bash scripts/up.sh`。

## 疑難排解

| 現象 | 原因／處理 |
| --- | --- |
| `init.py` 報錯提示 UID 不符 | 宿主機使用者 UID 必須為 1000。 |
| 節點結束並顯示 `Private cgroup namespace required` | 計算節點需 `cgroup: private`（Compose 已設）；請檢查 Docker 與 cgroup v2。 |
| 啟動時顯示 `Run the init service first` | 請執行 `bash scripts/up.sh`，不要直接執行裸 `docker compose up`。 |
| `slurmdbd` 顯示 `Run init with compose.accounting.yaml first` | 請先在 `.env` 啟用 accounting overlay，再執行 `bash scripts/up.sh`。 |
| `scontrol` 顯示 `CPUTot=16` 但 `CPUEfctv=4` | 正常現象；每個計算節點僅能排程分給它的 4 個 CPU。 |
| `sacct` 的 `MaxRSS` 欄位為空 | 在加入 `SYS_PTRACE` 之前提交的舊工作不會回填記憶體統計。 |
| 已完成的工作從 `squeue` 或 `scontrol` 消失 | `MinJobAge=3600`；約 1 小時後請改用 `sacct` 查詢（需啟用 accounting）。 |
| GPU 工作失敗或 VRAM 不足 | GPU 與宿主機桌面及其他程式共用，Slurm 無法阻擋；請在宿主機檢查 `nvidia-smi`。 |

`memory-oom.sbatch` 範例與驗收測試中的 OOM 案例皆為刻意觸發的失敗，並非系統異常。

## 延伸閱讀

- [`PLAN.md`](PLAN.md)：記錄設計決策、分階段建置計畫與驗收矩陣，第 10 節整理了官方參考連結。
- [`notebooks/`](notebooks/)：從第 00 章開始提供 Slurm 觀念與循序實作練習。
- [`compose.yaml`](compose.yaml) 與 [`config/slurm.conf`](config/slurm.conf)：包含詳細的資源與安全設定註解。
