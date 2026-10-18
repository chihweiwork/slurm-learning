"""Presentation shared by the twelve marimo notebooks; no external effects."""
from html import escape
from urllib.parse import quote

CHAPTERS = [
    ('00_dashboard.py', '總覽 Dashboard'),
    ('01_environment.py', '01 環境與資源'),
    ('02_submit_and_observe.py', '02 提交與觀察'),
    ('03_resources_and_queue.py', '03 資源與排隊'),
    ('04_csv_pipeline.py', '04 CSV Pipeline'),
    ('05_cross_node_mpi.py', '05 跨節點 MPI'),
    ('06_container_gpu.py', '06 CUDA 與容器'),
    ('07_gpu_isolation_and_queue.py', '07 GPU 隔離與排隊'),
    ('08_memory_failure.py', '08 記憶體失敗'),
    ('09_cancel_and_timeout.py', '09 取消與逾時'),
    ('10_drain_and_resume.py', '10 DRAIN 與恢復'),
    ('11_controller_recovery.py', '11 控制器復原'),
]


def navigation(mo, current_chapter):
    """Use native links: nav_menu rewrites Gallery query-string routes."""
    links = ['<a href="/" target="_self">Gallery</a>']
    for name, title in CHAPTERS:
        current = name.startswith(current_chapter + '_')
        attribute = ' aria-current="page"' if current else ''
        label = escape(title) + (' <small>（目前頁面）</small>' if current else '')
        links.append(f'<a href="/?file={quote(name)}" target="_self"{attribute}>{label}</a>')
    return mo.Html(
        '<style>.lab-navigation a {display:block;padding:0.45rem 0.6rem;'
        'border-left:3px solid transparent;color:inherit;text-decoration:none;}'
        '.lab-navigation a:hover {text-decoration:underline;}'
        '.lab-navigation a[aria-current="page"] {border-left-color:currentColor;font-weight:700;}'
        '</style><nav class="lab-navigation" aria-label="實驗頁面">'
        + ''.join(links) + '</nav>'
    )


def json_view(mo, value):
    import json
    text = json.dumps(value, ensure_ascii=False, indent=2)
    preview = mo.plain_text(text[:65536])
    if len(text) <= 65536:
        return preview
    return mo.vstack([mo.md('JSON 預覽截斷至前 65536 字元；完整證據可下載。'), preview,
                      mo.download(lambda: text.encode('utf-8'), filename='evidence.json',
                                  mimetype='application/json', label='下載完整 JSON 證據')])


def table_rows(rows):
    import json
    return [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
             for k, v in row.items() if k != 'raw'} for row in rows]
