import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="01 環境與資源")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    from slurm_cli import compose_argv, run_command
    from notebook_queries import ROOT, read_snapshot
    from notebook_views import navigation, json_view, table_rows

    return (
        ROOT,
        compose_argv,
        json_view,
        mo,
        navigation,
        read_snapshot,
        run_command,
        table_rows,
    )


@app.cell
def _(mo, navigation):
    refresh = mo.ui.refresh(options=['5s','15s','1m'], default_interval=None, label='只讀檢查')
    mo.sidebar(mo.vstack([navigation(mo), refresh]), width=290)
    return (refresh,)


@app.cell
def _(mo):
    mo.md("""
    # 01 環境、身分與可排程資源

    **目標**：辨認 Compose 節點、partition、共享路徑與 UID，理解 CPU 拓樸和可排程資源的差異。
    本頁只有查詢，不建立 run、不提交工作、不恢復節點。即使叢集有別人的工作也可以觀察。

    - `CPUTot=16` 描述主機拓樸；`CPUEfctv=4` 才是本節點的有效可排程 CPU。不能從 `alloc_idle_cpus` 或主機 `free_mem` 猜可用配額。
    - `cpu01`／`cpu02` 是同一實體工作站的不同容器，不是兩台實體機器。
    - 主機 `shared/` 對應各節點 `/shared`；一般命令由 lab（UID 1000）執行。root 只用於明列維運與診斷。
    - GPU 整卡觀測含桌面／Ollama；GRES 只約束 Slurm jobs，`--mem` 是 RAM 而非 VRAM。

    **預期**：controller 可回應、三個計算節點各有效 CPU 4、cpu/gpu partition、gpu01 一張 GRES。
    查詢失敗時保留錯誤與最後成功時間，不能顯示假綠燈；請先看 Compose、scontrol ping、daemon logs。
    """)
    return


@app.cell
def _(
    ROOT,
    compose_argv,
    json_view,
    mo,
    read_snapshot,
    refresh,
    run_command,
    table_rows,
):
    refresh.value
    snapshot = read_snapshot()
    checks = {}
    if snapshot['sources']['controller']['status'] == 'ok':
        for _name, _argv in [
            ('Compose', ['docker','compose','ps']),
            ('sinfo', compose_argv('sinfo','-Nel')),
            ('partitions', compose_argv('scontrol','show','partition','-o')),
            ('lab 身分／共享目錄', compose_argv('python3','-c', 'import os,json;from pathlib import Path;print(json.dumps({"uid":os.getuid(),"shared_exists":Path("/shared").is_dir(),"shared_readable":os.access("/shared",os.R_OK),"shared_writable":os.access("/shared",os.W_OK)}))')),
        ]:
            try:
                _result = run_command(_argv,cwd=ROOT,timeout=5)
                checks[_name] = {'argv':_argv,'returncode':_result.returncode,'stdout':_result.stdout,'stderr':_result.stderr}
            except Exception as _exc:
                checks[_name] = {'argv':_argv,'error':str(_exc)}
    else:
        checks['依賴查詢'] = {'status':'skipped','reason':'controller／Docker 不可用，請看 snapshot errors'}
    mo.vstack([
        mo.ui.table(table_rows(snapshot['sources']['nodes']['data'] or []),selection=None),
        mo.ui.table(snapshot['sources']['gpu']['data'] or [],selection=None),
        mo.accordion({name:json_view(mo,value) for name,value in checks.items()},multiple=True),
        mo.accordion({'完整 snapshot／錯誤':json_view(mo,snapshot)},multiple=True),
        mo.md('''## 診斷與獨立驗收
        本頁沒有清理動作。叢集空閒時，於終端執行：
        ```bash
        python3 scripts/smoke.py --case nodes-partitions
        docker compose logs --no-color --tail=100 controller
        docker compose exec -T -u root cpu01 journalctl -u slurmd -u munge --no-pager -n 100
        ```
        不改 Compose、不掛 Docker socket、不自動 chown 或重建叢集。
        ''')
    ])
    return


if __name__ == "__main__":
    app.run()
