# 單機 Slurm 實驗叢集建置計畫

## 1. 目標與範圍

在目前工作站上，以 Docker Compose 建立真正執行 Slurm 的多節點實驗環境，支援 CPU 作業、單 GPU 作業、跨節點啟動與基本管理操作。

本文件是建置與驗收依據；操作入口與執行方式見 `README.md`，實測證據由 `scripts/smoke.py` 保存。核心交付不包含資料庫；`slurmdbd`＋MariaDB 為獨立選配，不阻擋基本叢集完成。

### 核心交付

- 1 個控制／登入節點：執行 `slurmctld`，提供提交與管理命令。
- 2 個 CPU 計算節點：`cpu01`、`cpu02`，執行 `slurmd`。
- 1 個 GPU 計算節點：`gpu01`，執行 `slurmd`，獨占登記唯一的實體 NVIDIA GPU。
- MUNGE 認證、相同的作業使用者 UID/GID、共用工作目錄。
- `cpu` 與 `gpu` partition；真實 CPU、記憶體與 GPU 作業隔離。
- 可重現的建置與啟停流程、作業範例、操作說明及驗收紀錄。
- 使用獨立 Docker／OCI 作業映像，透過 Pyxis／Enroot 在 Slurm GPU 配額內執行真實 CUDA 計算；驗證數值、CPU／GPU 隔離、排隊及取消清理。

### 不在核心範圍

- 正式環境高可用、多主機部署、InfiniBand、分散式檔案系統。
- 多 GPU 訓練、GPU 虛擬切割、MPS／sharding、效能基準推估。
- Web 管理介面、Kubernetes、監控平台與排程器客製開發。
- 將單機容器當成不可信使用者的強安全隔離環境。

## 2. 初始環境評估與實作驗證

以下為 2026-10-18 評估快照；正式部署前重新檢查動態資源與版本。

| 項目 | 已觀察到的狀態 |
| --- | --- |
| CPU | Ryzen 7 7700，8 實體核心／16 執行緒；SMT 配對為 0/8、1/9，依此類推 |
| RAM | 系統顯示約 61 GiB，當下可用約 45 GiB |
| GPU | RTX 4070 SUPER，12,282 MiB 顯存；驅動 580.173.02；MIG 顯示 N/A |
| 儲存 | Kingston KC3000 NVMe；專案所在檔案系統當下可用約 367 GiB |
| 主機 | Pop!_OS 22.04 LTS；cgroup v2 |
| 容器 | Docker 29.8.2、Compose v5.6.0、NVIDIA Container Toolkit 1.12.1 |
| 既有負載 | 22 個執行中容器；Ollama 可存取全部 NVIDIA GPU；桌面也使用 GPU |
| Slurm | 主機 PATH 未找到 Slurm／MUNGE 命令；專案原為空目錄 |

已執行並通過：

- 既有 CUDA 容器使用 `--gpus device=0`，能由 `nvidia-smi` 辨識實體 GPU。
- 測試容器的 CPU affinity 確實限制為指定的 `[0, 8]`。
- 測試容器的 cgroup 記憶體上限確實為 512 MiB。
- 測試容器執行後自動刪除，未停止既有服務。

初始環境評估尚未涵蓋的 Slurm 啟動、作業層 cgroup 隔離、systemd／D-Bus 整合、CUDA 計算與跨節點工作，已在本次實作中完成驗收；另外加入獨立容器 GPU 作業驗收。完整結果見 `README.md`。`nvidia-smi` 顯示的 CUDA 版本仍不是主機已安裝 Toolkit 的證據。

## 3. 架構與資源配置

### 基本架構

使用專案獨立的 Compose 網路，固定節點 hostname。使用者透過 `docker compose exec` 進入控制節點，無須先建立 SSH 服務或對外開放 Slurm 連接埠。

控制節點負責排程，三個計算節點執行工作。共享目錄在所有節點使用相同絕對路徑；控制狀態、各計算節點 spool 與 MUNGE 金鑰分別保存，不共用同一份節點 spool。

### 起始預算

以下為規劃值，非效能測試結果。cpuset 依目前拓樸指定，部署時必須再次核對。

| 角色 | 主機 CPU 配置 | 容器 RAM 上限 | Slurm 可排程 RAM | GPU |
| --- | --- | --- | --- | --- |
| 控制／登入 | `6-7,14-15`，最多 2 邏輯 CPU 計算配額 | 2 GiB | 不執行計算作業 | 無 |
| `cpu01` | `0-1,8-9`，2 核心／4 執行緒 | 8 GiB | 起始 7 GiB | 無 |
| `cpu02` | `2-3,10-11`，2 核心／4 執行緒 | 8 GiB | 起始 7 GiB | 無 |
| `gpu01` | `4-5,12-13`，2 核心／4 執行緒 | 16 GiB | 起始 14 GiB | 1 張 |

- 核心服務 RAM 上限合計 34 GiB；預留節點 daemon 開銷，不把整個容器 RAM 上限全部登記為作業記憶體。
- 控制節點所在的 2 個實體核心不分配給計算節點；主機與既有服務仍可使用所有 CPU。這不是主機層 CPU 獨占保留，不修改既有服務 affinity。
- 16 個硬體執行緒不等於 16 個實體核心效能。使用 `select/cons_tres`，明確選擇以邏輯 CPU 與記憶體計量的配置，例如 `CR_CPU_Memory`，並驗證實際分配語意。
- 容器仍可能看見主機完整硬體拓樸。不得假設 cpuset 會自動讓 `slurmd -C` 只回報 4 個 CPU；階段 1 必須核對 Slurm 拓樸、CPU 編號映射與實際 job affinity。
- GPU 只映射到 `gpu01`，設定 `GresTypes=gpu` 與節點 `Gres=gpu:1`；不可在其他節點重複登記同一張卡。
- `cpu` partition 包含 `cpu01,cpu02`，作為預設；`gpu` partition 只包含 `gpu01`。設定明確的預設記憶體與時間上限，避免未指定資源的作業耗盡節點。

## 4. 安全邊界與主要風險

### 主機與既有服務

- 不自動停止 Ollama、其他容器或桌面程序，不更動主機 NVIDIA 驅動與 Docker 全域設定。
- 不掛載 Docker socket，不使用 host PID／network 作為預設，不將主機整棵 cgroup 樹以可寫方式交給容器。
- 不以全面 `privileged` 或關閉 Slurm 隔離作為方便啟動的預設解法。
- 若需主機 systemd 委派設定、額外 capability 或權限變更，先列出最小需求、影響與回復方式，取得使用者同意再實施。
- 使用者已核准本專案計算容器所需的額外 capabilities 與 seccomp／AppArmor 放寬；實作使用 `SYS_ADMIN`、`BPF`、`SYS_RESOURCE`、`SYS_NICE`、`SYS_PTRACE`。`SYS_PTRACE` 於處理第 1 輪學員回饋時另行核准：slurmstepd 取樣 MaxRSS／AveCPU 需讀取 `/proc/<pid>/io`，缺少時 EACCES 導致全部 jobacct 取樣被捨棄。仍禁止全面 privileged、Docker socket 與主機整棵可寫 cgroup 掛載，不變更既有服務。
- 所有網路、volume、容器與 runtime 檔案具專案識別；停止／刪除流程僅作用於本專案，不執行全域 prune。

### cgroup v2 是前置驗證關卡

- 優先使用具 systemd 的計算節點映像，在適當委派的 cgroup 子樹內執行 Slurm；先驗證 Docker、systemd、D-Bus、Slurm 與 eBPF 裝置限制的相容性。
- 目標包含 `proctrack/cgroup`、`task/cgroup`，以及 `ConstrainCores`、`ConstrainRAMSpace`、`ConstrainDevices`；另外明確配置 swap 政策，不把 swap 當成額外作業 RAM。
- 容器上限與 Slurm job 上限是兩層不同保護；必須分別觀察，不能只用 Compose limits 通過驗收。
- 不以 `IgnoreSystemd` 或關閉 cgroup plugin 掩蓋整合問題。
- 如果可接受權限下無法完成，記錄實測阻礙並提出選項。VM 是需重新評估的替代方案，不可未經同意直接切換；尤其 GPU passthrough 會影響目前桌面用卡。

### GPU 共用限制

- Slurm 只控制它管理的作業，不會阻止主機上的 Ollama／桌面使用 GPU。
- GPU 計算驗收採低顯存、短時間工作，先確認餘裕；需要穩定結果時，另行協調非 Slurm GPU 工作的使用時段。
- `CUDA_VISIBLE_DEVICES` 只是可見性提示，不能代替裝置存取控制；沒有取得 GPU GRES 的 job 必須無法直接使用該 GPU。

## 5. 分階段實作

### 階段 0：檢查前提與固定版本

工作：

1. 重新檢查 CPU 拓樸、可用 RAM／磁碟／顯存、既有容器負載及主機 systemd 版本。
2. 選擇仍受維護且支援 cgroup v2 的 Slurm 穩定版本；控制與計算節點使用完全相同版本。
3. 固定基底映像 digest、Slurm 版本與必要依賴；建置可重現，不使用浮動 `latest`。
4. 選擇與驅動相容的 CUDA runtime／編譯工具版本；優先在映像內提供，不要求主機安裝 Toolkit。
5. 決定專案命名、UID/GID、共享路徑、volume 與金鑰管理方式。MUNGE 金鑰只在初始化時產生，使用限制權限保存，不提交 Git，也不寫入映像層。

驗收：版本清單、資源配置與所需權限均明確；確認不與既有服務衝突。缺少必要前提時在此列出，不進行破壞性自動調整。

### 階段 1：控制節點＋單一 CPU 節點，驗證困難路徑

工作：

1. 建立控制與計算節點映像；啟動 MUNGE、systemd 與 Slurm 所需程序，確保 daemon 失敗可由健康檢查／容器狀態觀察。
2. 實作相同 UID/GID、共享路徑與持久化控制狀態。
3. 僅啟動控制節點與 `cpu01`，確認節點登記、認證與版本一致。
4. 實作 cgroup 委派、CPU 拓樸映射與 job CPU／記憶體限制；由真實 `srun` 工作觀察 affinity、cgroup 限制及記憶體超限結果。

驗收：`cpu01` 可正常執行工作；要求 1 個 CPU 的 job 不會獲得整個主機 affinity；受控超額記憶體工作被限制，其他工作與節點 daemon 不受波及。此關卡未通過，不擴展節點，也不宣稱已具備資源隔離。

### 階段 2：完整 CPU 排程與節點生命週期

工作：

1. 加入 `cpu02`，驗證兩個節點不重複配置計算用 cpuset。
2. 提供 CPU 工作、job array、相依性與跨節點啟動範例。
3. 驗證工作排隊、取消、時間限制，以及節點 drain／恢復。
4. 提供小型 MPI 範例，固定相容的 MPI／PMIx 與 Slurm 建置；使用 Slurm 啟動，不以 SSH 偷渡繞過排程。
5. 驗證控制節點重啟後的狀態保存與節點重新連線；不承諾整個計算容器重啟後可恢復原本程序。

驗收：跨兩節點工作確實在不同 hostname 執行；MPI collective 結果正確；資源占滿時新工作保持 pending，釋放後執行；`scancel` 後沒有殘留工作子程序。

### 階段 3：GPU 節點與真實 CUDA 工作

工作：

1. 加入 `gpu01` 與 `gpu` partition，只映射指定的實體 GPU。
2. 配置 `gres.conf`，使用選定 Slurm 版本支援的偵測方式；以 `slurmd -G` 核對實際 GRES。
3. 提供 GPU 資訊範例及小型 CUDA 計算範例；後者需要比較計算結果，不能僅檢查 `nvidia-smi`。
4. 同時提交兩個各要求 1 張 GPU 的工作，驗證 GPU 不會重複分配。
5. 在 `gpu01` 執行不申請 GPU 的 job，驗證它無法存取 GPU；CPU 節點也不能存取 NVIDIA GPU。
6. 建置獨立的 Debian/Python Docker 作業映像，與 Ubuntu Slurm 節點映像分開；透過主機端 `docker export` 與 squashfs 轉換交給 Enroot，節點內沒有 Docker daemon／socket。
7. 使用 Pyxis `srun --container-image` 啟動映像內預先打包的 CUDA Driver API／PTX 工作；核對 image 身份、Slurm cgroup、非 root UID、CPU affinity 與全部 65,539 個計算結果。不能只執行節點上的 Python 或檢查 GPU 名稱。
8. 在沒有 GPU GRES 的容器化 job 中，刻意掛載 GPU 裝置路徑並嘗試開啟，要求得到存取拒絕，不能只依賴環境變數隱藏 GPU。
9. 以容器 GPU 工作占住整卡，證明第二個工作 pending；取消第一個工作後確認程序消失且第二個能完成 CUDA 計算。

驗收：`sbatch -p gpu --gres=gpu:1` 能完成真實 CUDA 計算並得到正確結果；第二個 GPU 作業在第一個持有資源時等待，釋放後才執行；無 GPU 配額的 job 無法繞過限制。

### 階段 4：操作文件與端到端交付

工作：

1. 整理建置、初始化、啟動、提交工作、查詢、停止、重新啟動與故障排除操作。
2. 提供一條入口的 smoke 驗收腳本，透過真實 Slurm 命令與作業輸出判斷結果，使用有限等待時間。
3. 核心模式不依賴 `sacct`；使用即時 `scontrol`／`squeue`、job stdout／stderr、退出結果與 daemon 紀錄完成驗收。
4. 正常停止保留狀態與輸出；另列明確的資料重設操作及刪除範圍。刪除持久化資料必須由使用者明確選擇。
5. 紀錄實際版本、必要權限、通過與未通過項目；確認沒有遺留測試 job 或臨時容器。

驗收：依 README 可從建置到完成 CPU、跨節點及 GPU 工作；可停止再啟動且保留既有輸出；所有核心驗收項目有可觀察證據。

## 6. 核心驗收矩陣

| 情境 | 預期結果／證據 |
| --- | --- |
| 節點註冊 | `sinfo` 顯示三個計算節點，partition 成員及資源正確，無非預期 drain |
| 基本 CPU 作業 | 非 root 使用者執行成功，輸出 hostname、結果與可核對的 job ID |
| CPU 隔離 | job affinity 符合申請與節點 cpuset；其他節點的 CPU 不在可用集合 |
| 記憶體隔離 | 小額限制下的受控超額配置觸發 job cgroup OOM／限制；節點與對照作業存活 |
| 資源排隊 | 已占滿資源時新工作 pending；資源釋放後執行，無超配 |
| Job array／相依性 | 各 array task 輸出正確索引；`afterok` 工作只在前置工作成功後執行 |
| 跨節點／MPI | 兩個 hostname 可觀察；小型 collective 產生預期數值 |
| 取消／超時 | 工作終止、子程序清除、資源可再次分配 |
| 節點 drain／恢復 | drain 後不接新工作；恢復後可以再次執行 |
| GPU 計算 | 取得唯一 GPU 配額的工作完成短 CUDA kernel，驗證數值結果 |
| GPU 排隊／隔離 | 兩個整卡工作不重疊取得配額；未申請 GPU 的工作無法直接存取裝置 |
| 獨立容器 GPU 計算 | 從獨立 Docker image rootfs 執行其內建程式；驗證 image 身份、Slurm cgroup、非 root UID 及全部 CUDA 結果 |
| 容器 GPU 無配額拒絕 | 即使顯式掛載 GPU 裝置路徑，未申請 GRES 的 job 開啟裝置仍被拒絕 |
| 容器 GPU 取消／再分配 | 取消持有整卡的容器工作後，其程序消失，等待中的容器工作取得配額並完成計算 |
| 重啟／持久化 | 控制器狀態及作業輸出保留，節點重新連線；不假設計算程序可跨容器重啟存活 |
| 主機影響 | 未修改／停止既有容器；主機沒有測試造成的 OOM，測試資源已釋放 |

本次完整驗收的 16 個案例均通過，且 cleanup 無錯誤；證據保存於 `shared/results/20261018T051635Z-8c19e082/report.json`。此表是功能驗收範圍，不包含叢集效能或吞吐量承諾。

## 7. 交付檔案

採最少必要結構；共用設定不為各節點複製一份，特殊差異透過角色或 Compose 設定處理。

- `compose.yaml`：四個核心角色、網路、資源上限、GPU 映射與持久化掛載。
- `docker/`：固定版本的映像建置檔、必要啟動流程與 systemd units。
- `config/`：`slurm.conf`、`cgroup.conf` 與 GPU 節點的 `gres.conf`。
- `scripts/`：安全初始化與端到端 smoke 入口；避免另造通用管理框架。
- `examples/`：CPU、array、dependency、MPI、GPU 工作及受控隔離驗證所需程式。
- `.gitignore`：排除金鑰、runtime 狀態、作業輸出與其他本機產物。
- `README.md`：操作、限制、權限需求、故障排除、保留資料及明確重設流程。
- `notebooks/`：marimo Gallery 課程 `00_start.py`、`01_architecture.py`、`02_basic_usage.py`、`03_sbatch_resources.py`、`04_scheduling.py`、`05_parallel.py`、`06_gpu_containers.py`、`07_troubleshooting.py`、`08_accounting.py`、`09_operations.py`、`10_capstone.py`（每章：章首、動畫概念、按鈕示範、迷你終端練習＋檢查、小測驗、收尾）。共用 helpers 位於 `scripts/`：`course_ui.py`（頁面元件）、`course_runner.py`（示範 run 背景執行）、`course_terminal.py`（白名單迷你終端）、`course_progress.py`（`shared/course/<代碼>/` 學習紀錄）、`course_diagrams.py`、`course_sim.py`、`course_tasks.py`、`course_questions.py`、`closing.py`（唯讀收尾清單）。逐章驗收：`marimo run notebooks/` 後以瀏覽器依序走 00–10，每章至少執行示範按鈕、終端任務「檢查」、小測驗與收尾清理。
- `tests/`：不經瀏覽器的單元回歸測試與實際擷取的 fixtures，以 `uv run --locked python -m unittest discover -s tests` 執行。

實作另外包含 `docker/job.Dockerfile`、`scripts/prepare-job-image.py`、Pyxis／Enroot 設定與 `scripts/gpu_smoke.py`。完整驗收入口為 `python3 scripts/smoke.py`。Docker rootfs 匯出不保留 ENV／CMD／ENTRYPOINT，因此範例提交腳本明確指定命令與環境；runtime 是 Enroot，不冒稱為 Slurm 直接管理 Docker Engine 容器。

選配 accounting 另含 `compose.accounting.yaml`、`config/accounting-{off,slurmdbd}.conf`、`config/slurmdbd.conf`、`config/mariadb-slurm.cnf` 與 `scripts/accounting-init.sh`。

## 8. 選配擴充：slurmdbd＋MariaDB

啟用時機：核心叢集完成，且需要持久化作業歷史、帳戶／QOS 政策或 fair-share 實驗。

狀態：已實作並實測（2026-10-24）；預設關閉，以 `.env` 的 `COMPOSE_FILE` 啟用，操作見 `README.md`。未啟用任何 enforcement／QOS／fair-share 政策；版本升級程序只有文件，未實際執行。

Gallery 第 08 章（`notebooks/08_accounting.py`）提供 `sacct` 歷史查詢、白名單迷你終端的 `sacct`／`sacctmgr show` 練習與本次專屬 account 的新增／提交／核對／刪除示範；MaxRSS 需要計算節點具 `SYS_PTRACE`（已加入），只有加入後提交的工作有 MaxRSS。

設計：

- 以獨立 Compose override 加上 `slurmdbd` 與 MariaDB，並配套切換 Slurm accounting 設定；不可只啟動資料庫而沒有更新控制器設定。
- 使用 `accounting_storage/slurmdbd` 連接 `slurmdbd`，後者使用 `accounting_storage/mysql` 連接 MariaDB。
- MariaDB 不對主機外部開放 port；採專用資料庫帳號、獨立資料 volume 與未提交 Git 的認證資料。
- 兩者合計起始 RAM 預算 2 GiB，CPU 與控制節點共用管理用 cpuset；再依實測調整，不占用計算節點的 Slurm 配額。
- 初始化 cluster、account 與 user association；需要 QOS／fair-share 時另行配置 enforcement 與 priority，不假設安裝資料庫就會自動生效。
- 記錄備份／還原及版本升級程序；說明啟用前未被持久化的作業歷史不會自動補回。

選配驗收：完成作業在 `sacct` 中可查，重啟相關服務後仍保留；`sacctmgr` 可管理關聯；若啟用政策，以真實工作證明限制與優先序符合設定。

## 9. 執行順序與完成定義

順序固定為：環境與版本 → 單 CPU 節點隔離 → 雙 CPU 節點與 MPI → GPU 節點 → 端到端驗收與文件。資料庫在核心交付之後獨立選用。

核心完成必須同時滿足：

1. 四個核心角色可重現建置與啟動。
2. 三個計算節點可執行對應工作，CPU／RAM／GPU 隔離通過實測。
3. 排隊、取消、超時、相依性、跨節點及持久化行為有驗收證據。
   容器化 GPU 工作也必須通過上述數值、裝置隔離、排隊與取消驗收；不能只用直接 GPU 工作代替。
4. 有可直接照做的操作文件，且不侵入既有服務。

不能以「容器都在 running」、「Slurm 可以列出節點」或「GPU 可被 nvidia-smi 看見」代替完成。

## 10. 官方參考

- Slurm cgroup v2：https://slurm.schedmd.com/cgroup_v2.html
- cgroup 限制設定：https://slurm.schedmd.com/cgroup.conf.html
- GPU／GRES：https://slurm.schedmd.com/gres.html
- Accounting：https://slurm.schedmd.com/accounting.html
- slurmdbd 設定：https://slurm.schedmd.com/slurmdbd.conf.html
- Pyxis：https://github.com/NVIDIA/pyxis
- Enroot：https://github.com/NVIDIA/enroot
