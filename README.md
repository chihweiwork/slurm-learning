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

已經使用者核准：計算節點額外取得 `SYS_ADMIN`、`BPF`、`SYS_RESOURCE`、`SYS_NICE`，並在這些容器內放寬 seccomp／AppArmor。這是**高權限、可信工作專用的實驗環境**，不是多租戶安全沙箱。

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

固定版本：Slurm 26.05.5、Pyxis 0.24.0、Enroot 4.2.1、節點內 libnvidia-container 1.19.1。基底映像使用 digest，原始碼／外部套件下載使用 SHA256 驗證。Ubuntu apt 相依套件使用當時的套件庫版本，完整安裝清單保存在映像的 `/usr/local/share/node-packages.txt`；這不等於所有套件已做 bit-for-bit snapshot pinning。

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

開啟終端列出的帶 token loopback URL。Gallery 包含 Dashboard 與十一個實驗。
側欄以粗體、左側標線與「目前頁面」標示所在章節；使用原生連結保留 Gallery 的
`?file=...` 路由，切頁、重新整理與瀏覽器上一頁都會對應正確章節。
更新共用 Python helpers 後，需重啟 marimo server 才會載入修正；只刷新網頁不會重載已匯入的模組。
run 模式可以閱讀程式，但不能編輯。需要編輯時，先停止上述 server，再執行：

```bash
PYTHONPATH="$PWD/scripts" uv run --locked marimo edit notebooks/ \
  --host 127.0.0.1 --port 2719 --headless --token --no-sandbox
```

埠被占用時不停止既有服務；以終端實際 URL 為準，或用 `--port` 換本機埠。
不分享 token、不開放外部介面；這是使用主機 Docker 權限的可信單一使用者介面。
頁面載入、篩選與刷新只查詢；提交與維運必須按明確操作按鈕。
關閉頁面不取消 Slurm 工作。執行 CLI 驗收前，先完成或清理 notebook 工作。
瀏覽器 WASM／靜態 HTML 不能替代此主機 backend；關閉 server 後不能操作叢集。

### 實驗紀錄與查詢邊界

每次明確建立實驗才會新增 `shared/demos/<run-id>/`，參數在 `run.json` 凍結。
每個固定步驟先取得 exclusive claim，再呼叫外部命令；重開頁面不重送。
claim 存在但沒有 receipt，或提交逾時，代表結果 **unknown**，不是可安全重試。
先以紀錄中的唯一 job name、UID、工作目錄與提交時間人工核對；不能自動收編或掃殺工作。
清理保留證據，只處理本次已登記且重新核對身分的 job IDs 與仍屬本次 Reason 的 DRAIN。
Smoke 也透過 Slurm JSON 在取得 ID 後立即保存名稱、UID、WorkDir、SubmitTime；取消前重新核對，
不因控制器重設後 ID 重用而誤取消其他工作。維護前保存原 node 狀態及本次 Reason；
外部管理者改了 Reason，清理會拒絕 RESUME 並把報告標為失敗。

第 10／11 章的維護按鈕要求輸入 `DRAIN cpu02`、`RESUME cpu02`、
`RESTART controller` 或 `RESTORE controller`。DRAIN 不殺既有 holder；
holder 結束後 waiter 仍須等待，RESUME 才能執行。控制器復原只作用本專案 controller，
不重建計算節點、不刪 volume、不停止 Ollama。SIGKILL 或提交回應丟失後不自動重送。

Dashboard 的跨命令觀測不是原子快照；每個來源保存取得時間與最後成功時間。
Docker／controller 不可用時顯示 stale/error 或 N/A，不把缺資料補成零或成功。
Run 選單隨刷新發現新紀錄，並保留目前選取的 run；刷新不寫入 action receipts。
輸出預覽最多末 64 KiB，完整內容另行下載；僅允許所選實驗／驗收目錄內的已知檔案，
拒絕路徑穿越與 symlink。沒有 slurmdbd，過期且未保存的排程時間無法重建。

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

Gallery 第 04 章直接提交 `examples/pipeline-worker.sbatch` 與
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
報告標示選取範圍，只有包含全部 18 案例且無 skip 的執行才標示完整套件。

完整驗收包含刻意超過 128 MiB job 限制的 OOM 工作，以及一分鐘時間限制測試；這些預期失敗是隔離驗收的一部分，不是要求主機耗盡記憶體。OOM 工作最多嘗試配置 256 MiB。

驗收會暫時 drain/resume `cpu02`、重啟本專案控制器、提交與取消自己的工作，不取消其他工作。`--skip-lifecycle` 可明確跳過 drain／控制器重啟，但這不是完整驗收。

每次產生 `shared/results/<run-id>/report.json`，包含命令、輸出、案例結果、失敗診斷與 cleanup 結果。未使用 accounting 資料庫；已完成的 job 在控制器暫留至少一小時以利查驗，不承諾永久 `sacct` 歷史。

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

### marimo 實際操作證據

已在瀏覽器走完第 01–11 章：第 01 章只讀，其他章經真正按鈕提交、驗證及清理；
CSV 成功／修復與 cancel／自然 TIMEOUT 分開建立 run，共保存 12 份 passed 實驗報告。
完整路徑及 job IDs 見 [UI 驗證索引](shared/ui-evidence/verification.json)。

- [CSV 修復結果](shared/demos/20261018T063603Z-e39193a1d3a846a0a452cb4a5ff03e5d/pipeline/summary.json)：4 shards、4000 rows、value_sum=16004000。worker 2 非零退出、相依工作未執行、缺片彙總失敗，再只重送 shard 2 修復。
- [公開 GPU 容器輸出](shared/demos/20261018T064033Z-1d2c5296e8d74087ac96b76b8d9a5e53/container-100.out)：CUDA 實算並驗證 65539 元素，沒有 CPU fallback。
- OOM、CANCELLED、TIMEOUT、無 GRES 拒絕皆以具體證據驗證，不把任意失敗當通過；相鄰程序存活、後代清理及資源重用均已操作。
- controller 實際中斷時 Dashboard 顯示 stale/error、保留最後成功時間，缺資料計數為 N/A；明確 RESTORE 後恢復。重啟前後 holder StartTime、completed 輸出與 waiter 保存通過。
- 雙頁同時提交只產生一個 holder；claim 無 receipt 時保持 unknown、不重送。held／外部工作不被清場；外部 DRAIN Reason 改變時拒絕 RESUME 並記錄 failed。
- Run 模式唯讀 source、edit 模式實際編輯／重跑只讀 cell、窄視窗確認與清理控制項均已檢查。snapshot／CSV／report 的瀏覽器下載資源內容已解析核對；不以 HTTP 200 代替 UI 驗證。

畫面：[Gallery](shared/ui-evidence/gallery.png)、
[Dashboard 窄視窗](shared/ui-evidence/dashboard-narrow.png)、
[controller 中斷](shared/ui-evidence/dashboard-controller-stale.png)、
[controller 復原](shared/ui-evidence/11-recovery-passed.png)、
[窄視窗維護控制項](shared/ui-evidence/maintenance-narrow-controls.png)。
截圖不含 token；完整截圖與 JSON 證據保存在被 Git 忽略的 `shared/ui-evidence/`。

## 停止與資料保存

```bash
docker compose stop
# 使用現有映像與狀態恢復：
docker compose up -d --no-build --wait controller cpu01 cpu02 gpu01
```

`stop` 保留容器與資料。`docker compose down` 移除本專案容器／網路，但保留命名 volume 與主機 `shared/`。控制器狀態保存在 `controller-state` volume；MUNGE 金鑰在 `munge-key` volume。計算中的程序不能跨計算容器停止／重建存活。

**只有要重設叢集狀態及認證金鑰時**才執行 `docker compose down --volumes`；此命令會刪除本專案上述 volume，但不刪主機 `shared/`。不提供自動刪除作業輸出／其他 Docker 資源的操作，不使用全域 prune。重設後需再執行 `scripts/up.sh`。

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

MariaDB／slurmdbd 仍是未啟用的選配，見 [PLAN.md](PLAN.md)。
