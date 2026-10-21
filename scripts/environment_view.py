"""Read-only chapter 01 observations, shown as annotated terminal output."""
from html import escape
import json
import shlex

from notebook_queries import ROOT
from slurm_cli import compose_argv, run_command


TERMINAL_LIMIT = 65536
TERMINAL_CSS = '''<style>
.slurm-terminal {background:#0b111b;color:#d7e3f2;border:1px solid #29384b;
 border-radius:12px;overflow:hidden;margin:14px 0;box-shadow:0 8px 24px #00000024;
 font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;}
.slurm-terminal .st-bar {display:flex;align-items:center;gap:12px;padding:12px 16px;
 background:#121c2a;border-bottom:1px solid #29384b;flex-wrap:wrap;}
.slurm-terminal .st-dots {color:#8b9bb0;letter-spacing:4px;font-size:12px;}
.slurm-terminal .st-title {font-size:13px;font-weight:600;flex:1;}
.slurm-terminal .st-badge {font-size:11px;border:1px solid #35475c;border-radius:5px;
 padding:3px 7px;color:#afc0d4;}
.slurm-terminal .st-body {padding:16px 18px;}
.slurm-terminal .st-label {font-size:12px;font-weight:700;color:#70d9f1;margin:0 0 8px;}
.slurm-terminal .st-output-label {color:#9ce6b4;}
.slurm-terminal .st-error-label {color:#ffbd95;}
.slurm-terminal pre {background:transparent!important;color:#d7e3f2!important;
 font-family:inherit;font-size:13px;line-height:1.7;white-space:pre;overflow:auto;
 max-height:420px;margin:0 0 18px;padding:0;border:0;tab-size:4;}
.slurm-terminal .st-command {color:#b9eaf7!important;white-space:pre-wrap;overflow-wrap:anywhere;}
.slurm-terminal .st-note {font-size:12px;line-height:1.7;color:#bcc9da;
 border-top:1px dashed #35475c;padding-top:12px;white-space:pre-wrap;overflow-wrap:anywhere;}
.slurm-source-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
 gap:10px;margin:12px 0;}
.slurm-source-grid .ss-card {border:1px solid #8494a750;border-radius:9px;padding:12px;min-width:0;}
.slurm-source-grid .ss-card strong {display:block;margin-bottom:6px;}
.slurm-source-grid .ss-card p {margin:5px 0;font-size:12px;overflow-wrap:anywhere;}
[id^="env-"] {scroll-margin-top:24px;}
</style>'''


def read_environment_checks():
    """Query independently: Docker diagnostics survive scheduler failure."""
    commands = {
        'Compose': ['docker', 'compose', 'ps', '--all', '--no-trunc'],
        'Slurm 設定': compose_argv('cat', '/etc/slurm/slurm.conf'),
        'sinfo': compose_argv('sinfo', '-Nel'),
        '節點資源': compose_argv('scontrol', 'show', 'nodes'),
        'partitions': compose_argv('scontrol', 'show', 'partition'),
        'lab 身分／共享目錄': compose_argv(
            'python3', '-c',
            'import os,json;from pathlib import Path;print(json.dumps({'
            '"uid":os.getuid(),"shared_exists":Path("/shared").is_dir(),'
            '"shared_readable":os.access("/shared",os.R_OK),'
            '"shared_writable":os.access("/shared",os.W_OK)},indent=2))'),
    }
    checks = {}
    for name, argv in commands.items():
        try:
            result = run_command(argv, cwd=ROOT, timeout=5)
            checks[name] = dict(argv=argv, returncode=result.returncode,
                                stdout=result.stdout, stderr=result.stderr)
        except Exception as exc:
            checks[name] = dict(argv=argv, error=str(exc))
    return checks


def terminal_html(title, record, *, note='', stdin_note='未執行額外指令',
                  pending=False, blank_stdout=False, error_label='查詢例外（不是程式的 stderr）'):
    """Escape observed text so command output cannot inject HTML or CSS."""
    argv = record.get('argv') or []
    command = shlex.join(argv) if argv else stdin_note
    code = record.get('returncode')
    badge = 'NOT RUN' if pending else f'exit {code}' if code is not None else 'no exit code'
    stdout = record.get('stdout') or ''
    stderr = record.get('stderr') or ''
    body = ('<p class="st-label">stdin:</p><pre class="st-command">'
            + escape(command) + '</pre><p class="st-label st-output-label">stdout:</p><pre>'
            + escape(stdout[:TERMINAL_LIMIT] if stdout else
                     '' if blank_stdout else
                     '（尚未執行；目前沒有 stdout）' if pending else '（空輸出）') + '</pre>')
    if stderr:
        body += ('<p class="st-label st-error-label">stderr:</p><pre>'
                 + escape(stderr[:TERMINAL_LIMIT]) + '</pre>')
    if record.get('error'):
        body += ('<p class="st-label st-error-label">' + escape(error_label) + ':</p><pre>'
                 + escape(str(record['error'])[:TERMINAL_LIMIT]) + '</pre>')
    if len(stdout) > TERMINAL_LIMIT or len(stderr) > TERMINAL_LIMIT:
        note = '預覽截斷至各串流前 65536 字元；可從下方下載完整回應。\n' + note
    if note:
        body += '<div class="st-note">' + escape(note) + '</div>'
    return ('<section class="slurm-terminal" aria-label="' + escape(title, quote=True)
            + '"><div class="st-bar"><span class="st-dots" aria-hidden="true">● ● ●</span>'
            + '<span class="st-title">' + escape(title) + '</span>'
            + '<span class="st-badge">' + ('PREVIEW' if pending else 'READ ONLY')
            + '</span><span class="st-badge">'
            + escape(badge) + '</span></div><div class="st-body">' + body + '</div></section>')


def _terminal(mo, title, record, **kwargs):
    items = [mo.Html(terminal_html(title, record, **kwargs))]
    if any(len(record.get(key) or '') > TERMINAL_LIMIT for key in ('stdout', 'stderr')):
        payload = json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8')
        items.append(mo.download(lambda: payload, filename='terminal-response.json',
                                 mimetype='application/json', label='下載完整回應'))
    return mo.vstack(items)


def _check_panel(mo, title, check):
    failed = check.get('error') or check.get('returncode') != 0
    note = ('本次查詢失敗，無法判斷目前狀態。' if failed else
            'exit 0：這支查詢指令成功結束；仍要閱讀 stdout 判斷叢集狀態。')
    return _terminal(mo, title, check, note=note)


def source_rows(snapshot):
    """Keep failed, cached and disabled sources distinct in the overview."""
    names = {'controller': '排程控制器', 'nodes': '計算節點', 'jobs': '工作紀錄',
             'queue': '正在執行／排隊的工作', 'gpu': 'GPU 觀測'}
    rows = []
    for name, source in snapshot['sources'].items():
        verdict = {'ok': '查詢成功', 'disabled': '此部署未啟用'}.get(source['status'], '本次查詢失敗')
        if source.get('stale'):
            verdict += '；上次成功結果，不代表現在狀態'
        rows.append({'來源': names.get(name, name), '判讀': verdict,
                     '本次查詢時間': source.get('observed_at') or '未提供',
                     '最後成功時間': source.get('last_success_at') or '尚無成功紀錄',
                     '錯誤／說明': json.dumps(source['errors'], ensure_ascii=False)
                     if source.get('errors') else source.get('reason', '無'),
                     '警告': json.dumps(source['warnings'], ensure_ascii=False)
                     if source.get('warnings') else '無'})
    return rows


def _source_overview(mo, snapshot):
    cards = []
    for name, row in zip(snapshot['sources'], source_rows(snapshot)):
        cards.append('<article class="ss-card" id="env-source-' + escape(name, quote=True)
                     + '"><strong>' + escape(row['來源']) + '</strong>'
                     + ''.join('<p>' + escape(key) + '：' + escape(str(value)) + '</p>'
                               for key, value in row.items() if key != '來源') + '</article>')
    counts = snapshot.get('counts', {})
    labels = (('running', '執行中的工作'), ('pending', '排隊中的工作'),
              ('healthy_nodes', '符合健康狀態條件的節點'))
    count_text = ' ／ '.join(f'{label}：{counts[key] if counts.get(key) is not None else "無法判斷"}'
                            for key, label in labels)
    return mo.vstack([mo.Html('<div class="slurm-source-grid">' + ''.join(cards) + '</div>'),
                      mo.plain_text(count_text)])


def environment_panel(mo, snapshot, checks):
    """Show real command output with annotations, rather than duplicate tables."""
    gpu = snapshot['sources']['gpu']
    gpu_note = ('本次查詢失敗；stdout 是本次回應，完整 snapshot 的 data 可能是舊資料。'
                if gpu.get('stale') else 'GPU 整卡觀測，包含 Slurm 以外的使用量。')
    return mo.vstack([
        mo.Html(TERMINAL_CSS),
        mo.md('''## 先看這裡：目前查詢是否成功？
        下方 terminal 的 **stdin** 顯示實際執行的查詢指令，**stdout** 是程式回傳的文字，
        **stderr** 是另外的警告或錯誤輸出。這些是查詢紀錄，黑底區塊不會接受輸入或執行指令。
        `ok` 表示查詢成功；`stale` 表示 snapshot 正在保留上次成功的舊資料。
        各查詢依序執行，不是同一瞬間的叢集快照。'''),
        _source_overview(mo, snapshot),
        mo.Html('<span id="env-compose"></span>'),
        mo.md('''## Compose：Docker 裡有哪些服務？
        controller 負責接收提交與排程，cpu01／cpu02 負責執行工作，都在你這台電腦裡。
        看 `SERVICE` 與 `STATUS`：`Up` 表示容器在執行、`healthy` 表示容器健康檢查通過；
        Slurm 是否認得節點，還要看下一段。
        **`Up 3 hours` 是從容器最近一次啟動算起的時間，不是工作的執行時間。**
        重新啟動容器後重新計算；gpu01 則負責 GPU 工作。'''),
        _check_panel(mo, 'Docker Compose / 容器狀態', checks['Compose']),
        mo.accordion({'Compose 其他欄位怎麼讀？': mo.md('''
        - `NAME`：容器名稱；`SERVICE`：Compose 裡的服務名稱，例如 cpu01。
        - `IMAGE`：建立容器用的映像檔；`COMMAND`：容器啟動時執行的程式。
        - `CREATED`：容器建立於多久以前；`STATUS` 的 `Up` 則從最近一次啟動算起，兩者可能不同。
        - `PORTS`：容器連接埠與主機的對應；空白不代表容器之間無法連線。''')}),
        mo.Html('<span id="env-sinfo"></span>'),
        mo.md('''## sinfo：Slurm 認得哪些計算節點？
        先對照設定檔，再看控制器現在回報的節點狀態。
        **Compose 建立容器、主機名稱與網路；`slurm.conf` 宣告 Slurm 管理哪些節點、資源與分區。**

        下方讀取 controller 容器掛載的 `/etc/slurm/slurm.conf`。
        本實驗的 Compose 設定將 repo 的 `config/slurm.conf` 掛載到這個位置。
        若自行調整部署或掛載來源，以容器內實際讀到的內容為準。
        這裡讀到的是目前檔案內容；若剛改過檔案，仍須另外確認控制器是否已重新載入。'''),
        mo.Html('<span id="env-conf"></span>'),
        _check_panel(mo, 'slurm.conf / 容器掛載的設定檔', checks['Slurm 設定']),
        mo.md('''### 設定檔如何對應到 cpu01／cpu02？
        在上方 stdout 找 `SlurmctldHost`、`NodeName` 和 `PartitionName`：

        - **`SlurmctldHost=controller`**：控制器位於 controller，由 `slurmctld` 接收提交與排程。
        - **`NodeName=DEFAULT ...`**：後續節點共用的預設資源設定；DEFAULT 不是一台節點。
        - **`NodeName=cpu01 ...`／`NodeName=cpu02 ...`**：宣告兩台計算節點。
          `CPUs`、`SocketsPerBoard`、`CoresPerSocket`、`ThreadsPerCore` 描述 CPU 拓樸；
          `RealMemory` 宣告可排程 RAM，單位為 MiB；數值以目前設定檔為準。
        - **`CpuSpecList=...`**：保留、不分給一般工作的 CPU。
          這是 Slurm 的抽象 CPU 編號，不能直接當作 Linux CPU 編號。
          本實驗另外用 Docker cpuset 限制各容器的 CPU，讓每個節點有效可排程 CPU 為 4。
        - **`PartitionName=cpu Nodes=cpu01,cpu02 ...`**：把兩個節點放入 cpu 分區。
          `Default=YES` 對應下面的 `cpu*`；`MaxTime`、`DefMemPerCPU` 等是工作資源規則。

        **宣告節點之後，節點內的 `slurmd` 還要向控制器註冊。**
        節點名稱、網路、MUNGE 身分驗證與資源設定都必須相符，節點才可能正常提供服務。
        設定檔有 cpu01，不表示它現在一定在線；接著用 `sinfo` 確認。

        ### 現在查詢節點狀態
        先看 `NODELIST`、`PARTITION`、`STATE`。

        | 節點狀態（完整／縮寫） | 意思 | 讀這個狀態時要注意什麼？ |
        | --- | --- | --- |
        | `idle` | 空閒，目前沒有工作分配 | 能否接到你的工作，仍取決於資源需求與排程規則 |
        | `allocated`／`alloc` | 可分配的 CPU 已分給工作 | 不代表每個 CPU 都正在滿載計算 |
        | `mixed`／`mix` | 部分 CPU 已分配，部分仍空閒 | 還能不能接新工作，也要看 RAM 等資源是否足夠 |
        | `down` | 節點不可用 | 看 `Reason` 與服務日誌找原因 |
        | `draining`／`drng` | 停止接新工作，仍有既有工作執行 | 讓既有工作結束後，節點會進入 drained |
        | `drained`／`drain` | 已排空，不接新工作 | 管理員需處理原因並恢復節點，才會重新提供服務 |

        狀態可能帶有 `*` 等額外標記；節點狀態中的 `*` 表示沒有回應，
        與分區名稱 `cpu*` 中表示「預設分區」的星號不同。
        **這裡看的是 Slurm 節點狀態，與上方 Docker 容器的 Up／healthy 不同。**'''),
        _check_panel(mo, 'sinfo / 節點與分區', checks['sinfo']),
        mo.md('''### `S:C:T` 是什麼？
        **S = Sockets（每個節點的 CPU 插槽數）、C = Cores per socket（每個插槽的核心數）、
        T = Threads per core（每個核心的硬體執行緒數）。**

        例如 `1:8:2` 表示 **1 × 8 × 2 = 16 個邏輯 CPU**；請對照自己查到的數字。
        這是設定檔描述的 CPU 拓樸，不代表每個容器各自擁有這麼多專用 CPU。
        **要知道本實驗能分給工作多少 CPU，請看下一段的 `CPUEfctv`，預期每個節點為 4。**'''),
        mo.accordion({'sinfo 每個欄位怎麼讀？': mo.md('''
        - 第一行日期時間：這次查詢產生報表的時間，使用查詢環境的時區；不是節點啟動時間。
        - `NODELIST`：這一列的節點名稱，例如 cpu01。
        - `NODES`：這一列代表幾台節點；這裡各為 1，兩列共兩台。
        - `PARTITION`：所屬分區；`cpu*` 的星號表示預設分區，分區名稱本身是 cpu。
        - `STATE`：Slurm 眼中的節點狀態；`idle` 表示空閒。
        - `CPUS`：每個節點的 CPU 總數；保留資源後的有效數量另看 `CPUEfctv`。
        - `S:C:T`：插槽數 : 每個插槽的核心數 : 每個核心的執行緒數。
        - `MEMORY`：設定的每節點 RAM，單位 MiB；不是目前剩餘記憶體。
        - `TMP_DISK`：設定的每節點暫存磁碟容量，單位 MiB；0 不代表硬碟已滿。
        - `WEIGHT`：節點選用權重；其他條件相同時通常優先選較小值，不是 CPU 使用率。
        - `AVAIL_FE`：可用的節點特徵標籤（Available Features）；`(null)` 表示沒有設定標籤。
        - `REASON`：節點不可用等狀態的原因；正常 idle 時的 none 表示沒有原因記錄。

        欄位依據：[sinfo 官方說明](https://slurm.schedmd.com/sinfo.html)；
        設定依據：[slurm.conf 官方說明](https://slurm.schedmd.com/slurm.conf.html)。''')}),
        mo.Html('<span id="env-nodes"></span>'),
        mo.md('''### 再看 scontrol：有多少資源能分給工作？
        原始輸出已含完整資源欄位，可以直接對照，不再另外列一份表格。

        - **`CPUEfctv`**：有效可排程 CPU，本實驗每個節點預期為 4；`CPUTot` 是拓樸總數。
        - **`CPUAlloc`**：已分給工作的 CPU 配額，並非即時 CPU 使用率。
        - **`RealMemory`／`AllocMem`**：可排程／已分配的 RAM，單位 MiB；不是實際使用量。
        - **`State`／`Reason`**：節點狀態與原因；`Gres` 是 GPU 等額外資源。

        snapshot JSON 對應的名稱是 `effective_cpus`、`alloc_cpus`、`real_memory`、`alloc_memory`。
        不要用 `FreeMem` 推算自己能申請多少 RAM；還要符合排程與資源配額。'''),
        _check_panel(mo, 'scontrol show nodes / CPU 與 RAM', checks['節點資源']),
        mo.accordion({'scontrol show nodes 其他欄位怎麼讀？': mo.md('''
        - `NodeName`／`NodeHostName`／`NodeAddr`：Slurm 節點名稱、實際主機名稱與連線位址。
        - `Arch`／`OS`／`Version`：CPU 架構、作業系統與 Slurm 版本。
        - `Sockets`／`CoresPerSocket`／`ThreadsPerCore`：對應剛才的 S:C:T。
        - `CPULoad`：作業系統回報的負載指標，與已分配 CPU 數或百分比使用率不同。
        - `CfgTRES`／`AllocTRES`：設定的／已分配的可追蹤資源，例如 CPU、RAM、GPU。
        - `AvailableFeatures`／`ActiveFeatures`：設定的可用特徵／目前啟用的特徵。
        - `BootTime`／`SlurmdStartTime`：系統開機／節點 slurmd 啟動時間；容器可能看到主機核心的開機時間。
        - `LastBusyTime`：節點最近有工作執行的時間記錄，也會用於節點省電判斷。''')}),
        mo.Html('<span id="env-partitions"></span>'),
        mo.md('''## partitions：提交工作時可以選哪些分區？
        partition 是一組節點加上排程規則，例如 `sbatch -p cpu ...` 就是選 cpu 分區。
        **看 `PartitionName`、`Nodes`、`Default`、`State` 和 `MaxTime`。**
        `Default=YES` 表示不指定 `-p` 時的預設選擇；`State=UP` 表示分區啟用，不保證節點空閒。
        `MaxTime` 是分區的工作時間上限，`UNLIMITED` 表示此處未設上限；工作仍可能有自己的時間限制。
        `TotalCPUs` 是總數，不是剩餘可用數，也可能包含節點保留的 CPU。'''),
        _check_panel(mo, 'scontrol show partition / 排程規則', checks['partitions']),
        mo.accordion({'partition 其他欄位怎麼讀？': mo.md('''
        - `TotalNodes`：分區包含的節點總數；`MinNodes`／`MaxNodes`：單一工作可申請的節點數範圍。
        - `DefaultTime`：工作未指定 `--time` 時採用的時間；仍受 `MaxTime` 等限制。
        - `DefMemPerCPU`：每個申請 CPU 預設配多少 MiB RAM；工作可用 `--mem` 等選項提出需求。
        - `AllowGroups`／`AllowAccounts`／`AllowQos`：哪些群組、帳戶或服務等級可以使用分區。
        - `OverSubscribe`：是否允許多個工作共用已分配的運算資源。
        - `PriorityTier`：分區的排程優先層級；同時還有工作優先序與可用資源等條件。''')}),
        mo.Html('<span id="env-identity"></span>'),
        mo.md('''## lab 身分／共享目錄：誰在執行，結果寫到哪裡？
        這裡查的是 **controller 容器內** 的身分與權限。
        `uid` 預期為 **1000**，也就是 `lab`；主機使用者即使同為 UID 1000，仍須分辨是在主機或容器執行。
        **`shared_exists`、`shared_readable`、`shared_writable` 都預期為 `true`**，
        依序表示 `/shared` 存在、能讀取、能寫入。

        專案根目錄的 `shared/` 對應容器的 `/shared`，用來放工作輸入與結果。
        這裡只檢查目錄權限，個別檔案權限仍需另外確認。'''),
        _check_panel(mo, 'lab / 身分與共享目錄', checks['lab 身分／共享目錄']),
        mo.Html('<span id="env-gpu"></span>'),
        mo.md('''## GPU：這個實驗是否啟用？
        gpu01 的整卡使用量可能包含其他程式；`--mem` 指的是 RAM，不是顯示記憶體。
        查詢失敗時顯示實際錯誤，不能當成 GPU 空閒或未使用。'''),
        mo.md('**此部署未啟用 GPU，沒有執行 GPU 查詢。**') if gpu['status'] == 'disabled'
        else _terminal(mo, 'nvidia-smi / GPU 觀測', gpu, note=gpu_note),
        mo.Html('<span id="env-snapshot"></span>'),
        mo.md('''## 完整 snapshot／錯誤：需要追查時再展開
        這是本頁彙整的 JSON，沒有另外執行一支 snapshot 指令。
        每個來源的 `status`、`errors`、`warnings`、`stale` 和時間會保留。
        `data` 是整理後的資料，`raw`／`stdout` 保留原始回應；失敗時 `data` 可能是舊資料。
        `counts` 裡的 `null` 表示無法判斷，不是 0。'''),
        mo.accordion({'完整 snapshot／錯誤（原始 JSON）': _terminal(
            mo, 'Snapshot / 頁面彙整',
            {'stdout': json.dumps(snapshot, ensure_ascii=False, indent=2)},
            stdin_note='（無額外指令；由本頁各查詢結果彙整）',
            note='這份 JSON 是頁面彙整結果，不是另一支指令的 stdout。請先看 observed_at 與各來源的 stale。',
        )}),
    ])
