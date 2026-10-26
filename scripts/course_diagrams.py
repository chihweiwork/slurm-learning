"""Animated SVG diagrams for the Slurm course (第 01–09 章的概念圖).

Each diagram is a list of steps; SVG elements that belong to step ``i`` are
wrapped in ``<g class="s{i}">``. ``Diagram.render(k)`` returns a static SVG with
step ``k`` emphasised; ``Diagram.render(None)`` returns an auto-playing version
driven by scoped CSS keyframes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from xml.sax.saxutils import escape

ACCENT = '#f59e0b'
DIM = 0.15
SECONDS_PER_STEP = 2.5
BOX_FILL = 'rgba(99,102,241,0.10)'
BLOCK_COLORS = ('#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4')

# Placeholders substituted per render mode.
_S = '@S@'  # stroke colour of boxes/arrows
_M = '@M@'  # marker id for arrow heads


@dataclass(frozen=True)
class Step:
    caption: str
    detail: str


@dataclass(frozen=True)
class Diagram:
    id: str
    title: str
    steps: list[Step]
    height: int
    parts: tuple[tuple[int | None, str], ...]

    def render(self, step: int | None = None) -> str:
        """Static SVG with ``step`` emphasised, or auto-play HTML when ``None``."""
        if step is None:
            return f'<div class="dg-{self.id}"><style>{self._css()}</style>{self._svg("auto", None)}</div>'
        if not 0 <= step < len(self.steps):
            raise ValueError(f'step must be in 0..{len(self.steps) - 1}')
        return self._svg(f's{step}', step)

    def _svg(self, mode: str, current: int | None) -> str:
        plain, hot = f'arrow-{self.id}-{mode}', f'hot-{self.id}-{mode}'
        body = []
        for index, fragment in self.parts:
            if index is None:
                body.append(fragment.replace(_S, 'currentColor').replace(_M, plain))
            elif current is None:
                body.append(f'<g class="s{index}">{fragment.replace(_S, "currentColor").replace(_M, plain)}</g>')
            else:
                active = index == current
                fragment = fragment.replace(_S, ACCENT if active else 'currentColor').replace(_M, hot if active else plain)
                body.append(f'<g class="s{index}" opacity="{1 if active else DIM}">{fragment}</g>')
        defs = ''.join(
            f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
            for name, color in ((plain, 'currentColor'), (hot, ACCENT)))
        return (f'<svg viewBox="0 0 900 {self.height}" width="100%" xmlns="http://www.w3.org/2000/svg" '
                f'font-size="14" font-family="system-ui, sans-serif" role="img">'
                f'<title>{escape(self.title)}</title><defs>{defs}</defs>{"".join(body)}</svg>')

    def _css(self) -> str:
        n = len(self.steps)
        duration = f'{SECONDS_PER_STEP * n:g}s'
        rules = []
        for i in range(n):
            start, end = 100 * i / n, 100 * (i + 1) / n
            name = f'dg-{self.id}-{i}'
            rules.append(f'.dg-{self.id} .s{i} {{ animation: {name} {duration} linear infinite; }}')
            rules.append(f'.dg-{self.id} .s{i} .hl {{ animation: {name}-hl {duration} linear infinite; }}')
            rules.append(f'@keyframes {name} {{ {_frames(start, end, "opacity", "1", str(DIM))} }}')
            rules.append(f'@keyframes {name}-hl {{ {_frames(start, end, "stroke", ACCENT, "currentColor")} }}')
        return '\n'.join(rules)


def _frames(start: float, end: float, prop: str, on: str, off: str) -> str:
    """Hard-step keyframes: ``on`` during [start, end] percent, ``off`` elsewhere."""
    stops = [(0.0, off), (start, off), (start + 0.01, on)] if start > 0 else [(0.0, on)]
    stops.append((end, on))
    if end < 100:
        stops += [(end + 0.01, off), (100.0, off)]
    return ' '.join(f'{at:.2f}% {{ {prop}: {value}; }}' for at, value in stops)


def strip_style(html: str) -> str:
    """Return the bare ``<svg>…</svg>`` from a ``render(None)`` result."""
    match = re.search(r'<svg\b.*</svg>', html, re.S)
    if match is None:
        raise ValueError('no <svg> element found')
    return match.group(0)


class _Canvas:
    def __init__(self) -> None:
        self.parts: list[tuple[int | None, str]] = []

    def _add(self, step: int | None, svg: str) -> None:
        self.parts.append((step, svg))

    def text(self, x, y, label, *, step=None, anchor='middle', size=None, bold=False, mono=False, fill='currentColor'):
        attrs = f' font-size="{size}"' if size else ''
        attrs += ' font-weight="600"' if bold else ''
        attrs += ' font-family="ui-monospace, monospace"' if mono else ''
        self._add(step, f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}"{attrs}>{escape(label)}</text>')

    def box(self, x, y, w, h, title, *lines, step=None, dashed=False, fill=BOX_FILL, size=12, mono=False):
        dash = ' stroke-dasharray="5 4"' if dashed else ''
        svg = [f'<rect class="hl" x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
               f'stroke="{_S}" stroke-width="1.2"{dash}/>']
        rows = [(title, None, True)] + [(line, size, False) for line in lines]
        top = y + h / 2 - (len(rows) - 1) * 9 + 5
        family = ' font-family="ui-monospace, monospace"' if mono else ''
        for i, (label, font, bold) in enumerate(rows):
            weight = ' font-weight="600"' if bold else ''
            font_attr = f' font-size="{font}"' if font else ''
            svg.append(f'<text x="{x + w / 2:g}" y="{top + 18 * i:g}" text-anchor="middle" fill="currentColor"'
                       f'{font_attr}{weight}{family if not bold else ""}>{escape(label)}</text>')
        self._add(step, ''.join(svg))

    def outline(self, x, y, w, h, *, step=None):
        """Thick emphasis frame drawn over an existing box."""
        self._add(step, f'<rect class="hl" x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="10" '
                        f'fill="none" stroke="{_S}" stroke-width="2.5"/>')

    def block(self, x, y, w, h, label, color, *, step=None):
        self._add(step, f'<rect class="hl" x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{color}" '
                        f'fill-opacity="0.55" stroke="{_S}" stroke-width="1.2"/>'
                        f'<text x="{x + w / 2:g}" y="{y + h / 2 + 5:g}" text-anchor="middle" fill="currentColor" '
                        f'font-weight="600">{escape(label)}</text>')

    def arrow(self, x1, y1, x2, y2, *, step=None, both=False, dashed=False):
        start = f' marker-start="url(#{_M})"' if both else ''
        dash = ' stroke-dasharray="5 4"' if dashed else ''
        self._add(step, f'<line class="hl" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{_S}" stroke-width="1.6"'
                        f'{dash}{start} marker-end="url(#{_M})"/>')

    def path(self, d, *, step=None, dashed=False, marker=True):
        dash = ' stroke-dasharray="5 4"' if dashed else ''
        end = f' marker-end="url(#{_M})"' if marker else ''
        self._add(step, f'<path class="hl" d="{d}" fill="none" stroke="{_S}" stroke-width="1.6"{dash}{end}/>')

    def line(self, x1, y1, x2, y2, *, step=None, dashed=False):
        dash = ' stroke-dasharray="4 4"' if dashed else ''
        self._add(step, f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="currentColor" '
                        f'stroke-opacity="0.5" stroke-width="1"{dash}/>')


def _diagram(id: str, title: str, height: int, steps: list[tuple[str, str]], canvas: _Canvas) -> Diagram:
    return Diagram(id, title, [Step(caption, detail) for caption, detail in steps], height, tuple(canvas.parts))


def _components() -> Diagram:
    c = _Canvas()
    c.box(20, 30, 130, 64, '你的終端', '登入節點')
    c.box(260, 30, 200, 64, 'slurmctld', 'controller')
    c.box(600, 30, 130, 64, 'slurmdbd', '帳務服務')
    c.box(760, 30, 120, 64, 'MariaDB', '資料庫')
    for x, name in ((200, 'cpu01'), (370, 'cpu02'), (540, 'gpu01')):
        c.box(x, 180, 150, 64, name, 'slurmd')
    c.box(200, 320, 490, 44, '/shared（所有節點共用目錄）')
    c.text(20, 392, '所有元件用 munge 互相認證', anchor='start', size=13)
    # 1 submit
    c.arrow(150, 62, 258, 62, step=0)
    c.text(205, 52, 'sbatch job.sbatch', step=0, size=11, mono=True)
    # 2 JobID + queue
    c.outline(260, 30, 200, 64, step=1)
    c.text(20, 128, 'JobID=101，放進佇列', step=1, anchor='start', size=13)
    # 3 scheduler picks cpu01
    c.text(20, 152, '比對資源 → 選 cpu01', step=2, anchor='start', size=13)
    c.outline(200, 180, 150, 64, step=2)
    # 4 notify slurmd
    c.arrow(300, 94, 270, 178, step=3)
    c.text(250, 140, '啟動', step=3, size=12)
    # 5 cgroup
    c.box(210, 254, 130, 40, 'cgroup', 'job.sbatch', step=4, dashed=True, size=11)
    # 6 shared storage
    c.arrow(355, 294, 355, 318, step=5, both=True)
    c.line(445, 244, 445, 320, step=5, dashed=True)
    c.line(615, 244, 615, 320, step=5, dashed=True)
    c.text(700, 347, '每台都看到同一份', step=5, anchor='start', size=13)
    # 7 completion
    c.arrow(320, 178, 380, 96, step=6)
    c.text(395, 140, 'COMPLETED（exit 0）', step=6, anchor='start', size=12)
    # 8 accounting
    c.arrow(460, 62, 598, 62, step=7)
    c.arrow(730, 62, 758, 62, step=7)
    c.text(820, 116, 'sacct 從這裡查', step=7, size=13)
    return _diagram('components', 'Slurm 的元件與一個工作的一生', 400, [
        ('你在登入節點輸入 `sbatch job.sbatch`',
         'sbatch 只是用戶端程式：它把腳本與 #SBATCH 參數送給 controller，送出後立刻結束，不會等工作跑完。'),
        ('slurmctld（controller）收到請求、發 JobID、放進佇列',
         'slurmctld 是整個叢集唯一的大腦，本 lab 跑在 controller 容器；它回傳 JobID（例如 101），工作先以 PENDING 進入佇列。'),
        ('排程器比對 partition／CPU／記憶體／GPU，挑到 cpu01',
         '排程器是 slurmctld 裡的一部分，它找出符合 partition 與資源需求、而且現在有空的節點；本 lab 的 cpu01、cpu02 各有 4 CPU、7168 MiB。'),
        ('slurmctld 通知 cpu01 的 slurmd',
         '每個計算節點都跑一個 slurmd 常駐程式，它接到 controller 的指令後才會在本機啟動工作，工作狀態轉為 RUNNING。'),
        ('slurmd 建 cgroup（限制 CPU／記憶體），啟動你的腳本',
         'cgroup 是 Linux 核心的資源圍欄：工作只能用申請到的 CPU 核心，記憶體超過 --mem 會被核心 OOM-kill。'),
        ('腳本讀寫 `/shared`（所有節點都看得到同一份）',
         '/shared 掛載在每個節點的同一路徑，所以輸入檔與 slurm-<JobID>.out 不論工作排到哪個節點都找得到。'),
        ('結束：slurmd 回報結束碼，slurmctld 記下 COMPLETED',
         '腳本結束後 slurmd 把 exit code 回報給 slurmctld；結束碼 0 記為 COMPLETED，非 0 記為 FAILED。'),
        ('slurmctld 把紀錄送到 slurmdbd → MariaDB；之後 `sacct` 從這裡查',
         'controller 只暫留結束的工作 MinJobAge=3600 秒，長期紀錄由 slurmdbd 寫進 MariaDB，sacct 查的就是這份資料庫。'),
    ], c)


def _job_states() -> Diagram:
    c = _Canvas()
    c.box(20, 60, 140, 56, 'PENDING', '排隊中', step=0)
    c.text(20, 142, 'Reason：Resources／Priority／', step=0, anchor='start', size=12)
    c.text(20, 160, 'Dependency／ReqNodeNotAvail', step=0, anchor='start', size=12)
    c.arrow(160, 88, 228, 88, step=1)
    c.box(230, 60, 140, 56, 'RUNNING', '執行中', step=1)
    c.text(300, 46, 'squeue 看得到', step=1, size=12)
    c.arrow(370, 88, 438, 88, step=2)
    c.box(440, 60, 150, 56, 'COMPLETING', '收尾（很短）', step=2)
    c.arrow(590, 76, 678, 46, step=3)
    c.arrow(590, 100, 678, 108, step=3)
    c.box(680, 20, 190, 50, 'COMPLETED', 'ExitCode 0:0', step=3)
    c.box(680, 84, 190, 50, 'FAILED', 'ExitCode 非 0（例 1:0）', step=3)
    c.arrow(290, 116, 360, 218, step=4)
    c.arrow(330, 116, 530, 218, step=4)
    c.box(280, 220, 150, 50, 'TIMEOUT', '超過 --time', step=4)
    c.box(450, 220, 150, 50, 'CANCELLED', 'scancel', step=4)
    c.arrow(370, 108, 678, 175, step=5)
    c.box(680, 152, 190, 50, 'OUT_OF_MEMORY', '超過 --mem', step=5)
    return _diagram('job_states', '工作狀態機', 290, [
        ('PENDING：排隊中，Reason 告訴你為什麼（Resources／Priority／Dependency／ReqNodeNotAvail）',
         'PENDING 不代表出錯；先看 squeue 的 Reason 欄，它說明排程器現在為什麼還沒讓工作開始。'),
        ('RUNNING：節點上執行，`squeue` 看得到',
         '工作已經在計算節點的 cgroup 裡執行，squeue 的 NODELIST 欄會顯示它跑在哪個節點。'),
        ('COMPLETING：程式結束了，節點在收尾（很短）',
         '主程式已經結束，slurmd 正在清掉殘留程序與 cgroup；通常一兩秒就過去。'),
        ('COMPLETED／FAILED：ExitCode 0 或非 0',
         '腳本回傳 0 記為 COMPLETED，非 0 記為 FAILED；結束後要改用 sacct 查 State 與 ExitCode。'),
        ('TIMEOUT／CANCELLED：被時間限制或 scancel 終止',
         '超過 --time 時 allocation 記為 TIMEOUT 0:15；被 scancel 時記為 CANCELLED，並寫出是誰取消的（例如 CANCELLED by 1000）。'),
        ('OUT_OF_MEMORY：cgroup 殺掉超過 `--mem` 的程式',
         '記憶體超過 --mem 時核心在 cgroup 內 OOM-kill；本 lab 會看到 step 列 OUT_OF_MEMORY 0:125，allocation 列則是 FAILED 1:0。'),
    ], c)


def _allocation_step_task() -> Diagram:
    c = _Canvas()
    c.box(20, 30, 560, 270, '', step=0)
    c.text(300, 56, 'allocation：JobID 101（sbatch 要到的資源）', step=0, bold=True)
    c.box(40, 80, 250, 200, '', step=1)
    c.text(165, 104, 'step 101.0（第 1 個 srun）', step=1, size=13)
    c.box(310, 80, 250, 200, '', step=1)
    c.text(435, 104, 'step 101.1（第 2 個 srun）', step=1, size=13)
    for x in (50, 130, 210):
        c.box(x, 150, 70, 60, f'task {(x - 50) // 80}', '程序', step=2)
    for x in (340, 450):
        c.box(x, 150, 80, 60, f'task {(x - 340) // 110}', '程序', step=2)
    c.text(300, 250, '--ntasks 決定每個 step 有幾個 task', step=2, size=12)
    c.box(600, 30, 290, 140, '', step=3)
    c.text(615, 54, 'sacct -j 101', step=3, anchor='start', mono=True, size=12)
    c.text(615, 84, 'JobID   State      MaxRSS', step=3, anchor='start', mono=True, size=12)
    c.text(615, 108, '101     COMPLETED', step=3, anchor='start', mono=True, size=12)
    c.text(615, 132, '101.0   COMPLETED  48M', step=3, anchor='start', mono=True, size=12)
    c.text(615, 156, '101.1   COMPLETED  12M', step=3, anchor='start', mono=True, size=12)
    c.box(600, 200, 290, 100, '終端直接 srun', 'allocation 與 step 一起產生', '程式結束兩者一起結束', step=4)
    return _diagram('allocation_step_task', 'allocation、step、task 三層', 320, [
        ('`sbatch` 要到一份資源 = allocation（JobID 101）',
         'allocation 是排程器分給你的一組 CPU、記憶體與節點，在 JobID 存在的期間都歸你使用。'),
        ('腳本裡每個 `srun` 是一個 step（101.0、101.1）',
         '每執行一次 srun 就在同一份 allocation 裡開一個 step，編號依序是 JobID.0、JobID.1；腳本本身則記為 JobID.batch。'),
        ('step 裡的每個程序是一個 task（`--ntasks`）',
         '一個 step 會同時啟動 --ntasks 個程序（task），MPI 程式的每個 rank 就是一個 task。'),
        ('`sacct` 一列 allocation、一列 step；MaxRSS 記在 step 列',
         'allocation 列的 MaxRSS 是空白的，記憶體用量要看 101.0、101.batch 這類 step 列。'),
        ('`srun` 直接在終端執行時，allocation 和 step 一起產生',
         '不經過 sbatch 時，srun 會先要一份 allocation 再在裡面跑 step 0，程式結束兩者一起釋放。'),
    ], c)


def _scheduling() -> Diagram:
    c = _Canvas()
    x0, unit, top, row = 250, 68, 50, 40
    c.text(95, 34, '佇列', bold=True)
    c.box(20, 50, 150, 36, 'A 3 CPU 4 分', step=0, size=12)
    c.box(20, 94, 150, 36, 'B 4 CPU 3 分', step=0, size=12)
    c.box(20, 138, 150, 36, 'C 1 CPU 2 分', step=0, size=12)
    for r in range(4):
        c.text(x0 - 10, top + row * r + 24, f'CPU {r}', anchor='end', size=12)
        c.line(x0, top + row * r, x0 + 9 * unit, top + row * r)
    c.line(x0, top + 4 * row, x0 + 9 * unit, top + 4 * row)
    for t in range(10):
        c.line(x0 + t * unit, top, x0 + t * unit, top + 4 * row + 6)
        c.text(x0 + t * unit, top + 4 * row + 22, str(t), size=12)
    c.text(x0 + 9 * unit, top + 4 * row + 42, '時間（分）→', anchor='end', size=12)
    c.block(x0 + 2, top + 2, 4 * unit - 4, 3 * row - 4, 'A', BLOCK_COLORS[0], step=1)
    c.text(x0 + 3 * unit, top + 3 * row + 25, '剩 1 CPU', step=1, size=12)
    c.outline(20, 94, 150, 36, step=2)
    c.text(20, 205, 'B 等待：', step=2, anchor='start', size=13)
    c.text(20, 225, 'Reason=Resources', step=2, anchor='start', size=13, mono=True)
    c.block(x0 + 2, top + 3 * row + 2, 2 * unit - 4, row - 4, 'C', BLOCK_COLORS[2], step=3)
    c.text(20, 255, 'C 回填：2 分就結束，', step=3, anchor='start', size=13)
    c.text(20, 275, '不延後 B', step=3, anchor='start', size=13)
    c.line(x0 + 4 * unit, top - 10, x0 + 4 * unit, top + 4 * row + 6, step=4, dashed=True)
    c.text(x0 + 4 * unit, top - 14, 'A 結束', step=4, size=12)
    c.block(x0 + 4 * unit + 2, top + 2, 3 * unit - 4, 4 * row - 4, 'B', BLOCK_COLORS[1], step=4)
    return _diagram('scheduling', '排程與回填', 290, [
        ('佇列：A（3 CPU、4 分）、B（4 CPU、3 分）、C（1 CPU、2 分）',
         '三個工作依序提交到同一個 4 CPU 節點；排程器依優先順序（這裡就是提交順序）逐一考慮。'),
        ('A 先開始，節點剩 1 CPU',
         'A 要 3 個 CPU，節點有空就立刻開始，執行 4 分鐘；這段時間只剩 1 個 CPU 可用。'),
        ('B 要 4 CPU 放不下 → PENDING Reason=Resources',
         'B 需要整台節點的 4 個 CPU，只能等 A 結束；排程器算出 B 最早在第 4 分鐘開始，並為它保留這個時間。'),
        ('C 只要 1 CPU、2 分鐘內會結束、不影響 B 的預計開始 → 回填先跑',
         '回填（backfill）讓後面的小工作用掉空檔，前提是它在 B 的預計開始時間前結束；所以 --time 寫得準，越容易被回填。'),
        ('A 結束，B 開始',
         '第 4 分鐘 A 釋放 CPU，B 按預定時間開始；C 早已在第 2 分鐘跑完，整體沒有浪費。'),
    ], c)


def _array_dependency() -> Diagram:
    c = _Canvas()
    c.box(20, 125, 170, 60, 'sbatch --array=0-3', 'array job 200', step=0, size=12)
    nodes = ('cpu01', 'cpu02', 'cpu01', 'cpu02')
    for i in range(4):
        y = 30 + 65 * i
        c.arrow(190, 155, 268, y + 25, step=0)
        c.box(270, y, 170, 50, f'200_{i}', f'SLURM_ARRAY_TASK_ID={i}', step=0, size=11)
        c.box(455, y + 10, 70, 30, nodes[i], step=1, size=11)
        c.arrow(525, y + 25, 638, 155, step=3)
    c.text(490, 22, '同時執行', step=1, size=12)
    c.text(760, 108, '--dependency=afterok:200', step=2, mono=True, size=12)
    c.box(640, 120, 240, 70, '彙總 job 204', 'PENDING Reason=Dependency', step=2, size=12)
    c.text(760, 220, '全部 COMPLETED → 開始', step=3, size=13)
    c.text(760, 244, '任一失敗 → 被取消', step=3, size=13)
    return _diagram('array_dependency', 'array 與 dependency', 300, [
        ('`--array=0-3` 一次送 4 個同腳本的 task，`$SLURM_ARRAY_TASK_ID` 不同',
         '一個 array job 共用一個母 JobID（200），每個 task 記為 200_0…200_3；腳本用 $SLURM_ARRAY_TASK_ID 決定要處理哪一份輸入。'),
        ('它們可以同時在不同節點跑',
         '每個 array task 都是獨立排程的工作，資源夠時會分散到 cpu01、cpu02 同時執行；%2 這類後綴可以限制同時執行數。'),
        ('`--dependency=afterok:<array job>` 的彙總工作先 PENDING Reason=Dependency',
         '彙總工作提交後立刻拿到 JobID，但排程器在條件滿足前不會考慮它，Reason 顯示 Dependency。'),
        ('全部成功後彙總才開始；任一失敗則彙總永遠不跑（`kill_invalid_depend` 會取消它）',
         'afterok 要求 array 的每個 task 都 COMPLETED；本 lab 設了 SlurmctldParameters=kill_invalid_depend，條件不可能成立時 slurmctld 直接取消彙總工作。'),
    ], c)


def _gpu_gres() -> Diagram:
    c = _Canvas()
    c.box(20, 40, 230, 70, 'sbatch', '--partition=gpu --gres=gpu:1', step=0, size=12)
    c.arrow(250, 75, 318, 75, step=0)
    c.box(320, 40, 180, 70, 'slurmctld', 'controller')
    c.box(600, 20, 130, 48, 'cpu01', '無 GRES', size=11)
    c.box(600, 78, 130, 48, 'cpu02', '無 GRES', size=11)
    c.box(600, 150, 280, 150, '')
    c.text(740, 172, 'gpu01（gres/gpu=1）', bold=True)
    c.text(745, 48, '✗ 不符', step=1, anchor='start', size=12)
    c.text(745, 106, '✗ 不符', step=1, anchor='start', size=12)
    c.arrow(500, 90, 598, 190, step=1)
    c.box(615, 185, 140, 60, '你的 job', 'cgroup', step=2, dashed=True, size=11)
    c.box(775, 190, 95, 40, '/dev/nvidia0', size=11)
    c.arrow(755, 210, 773, 210, step=2)
    c.text(700, 268, '允許使用裝置', step=2, size=12)
    c.box(20, 210, 230, 60, '沒申請 GRES 的 job', 'nvidia-smi -L 看得到名稱', step=3, size=11)
    c.path('M250,285 H822 V232', step=3, dashed=True)
    c.text(540, 278, '✗ CUDA：Permission denied', step=3, size=12)
    return _diagram('gpu_gres', 'GPU 是一種 GRES', 320, [
        ('`--partition=gpu --gres=gpu:1`',
         'GPU 在 Slurm 裡是一種 GRES（generic resource），必須明確申請；本 lab 只有 gpu 分區的 gpu01 有 1 顆 GPU。'),
        ('slurmctld 只挑有 GRES 的 gpu01',
         '排程器把 gres/gpu=1 當成和 CPU、記憶體一樣的條件，cpu01、cpu02 沒有 GPU 所以不會被選中。'),
        ('slurmd 在 cgroup 開放 `/dev/nvidia0` 給這個 job',
         'gpu01 的 slurmd 依 gres.conf 把 /dev/nvidia0 的存取權加進這個工作的 device cgroup，程式才開得了 GPU。'),
        ('沒申請 GRES 的 job 看得到裝置名稱卻開不了（Permission）',
         '裝置節點仍在檔案系統裡，nvidia-smi -L 也可能列出名稱，但 cgroup 擋下實際開啟，CUDA 會回報權限錯誤或找不到可用裝置。'),
    ], c)


def _failure_layers() -> Diagram:
    c = _Canvas()
    layers = (
        ('程式／訊號層', 'OOM-kill（SIGKILL）、SIGTERM、exit 1'),
        ('cgroup 層', 'memory.events：oom_kill 0 → 1'),
        ('step 列', '101.0 OUT_OF_MEMORY 0:125 ／ CANCELLED 0:15 ／ TIMEOUT'),
        ('allocation 列', '101 FAILED 1:0 ／ TIMEOUT 0:15 ／ CANCELLED by 1000'),
    )
    for i, (name, example) in enumerate(layers):
        y = 20 + 72 * i
        c.box(20, y, 860, 60, '', step=i)
        c.text(40, y + 36, name, step=i, anchor='start', bold=True)
        c.text(200, y + 36, example, step=i, anchor='start', mono=True, size=13)
        if i:
            c.arrow(850, y - 14, 850, y + 2, step=i)
    c.text(450, 330, '同一事件四層寫法不同，不是矛盾', bold=True)
    return _diagram('failure_layers', '一次失敗留下的四層證據', 345, [
        ('程式／訊號層：OOM-kill、SIGTERM、exit 1',
         '最底層是程式本身怎麼結束：被核心 SIGKILL、被 Slurm 送 SIGTERM，或程式自己 exit 1；線索在 .out／.err 的最後幾行。'),
        ('cgroup 層：`memory.events oom_kill`',
         '記憶體超過 --mem 時，工作 cgroup 的 memory.events 裡 oom_kill 計數會從 0 變 1，這是 OOM 最直接的證據。'),
        ('step 列：`OUT_OF_MEMORY 0:125`／`CANCELLED`／`TIMEOUT`',
         'sacct 的 step 列記錄單一 step 的結果：OOM 時 101.0 是 OUT_OF_MEMORY 0:125，TIMEOUT 時各 step 多半記為 CANCELLED 0:15。'),
        ('allocation 列與 accounting：`FAILED 1:0`、`TIMEOUT`、`CANCELLED by 1000`',
         'allocation 列反映整個工作的結局：OOM 後腳本回傳 1 所以是 FAILED 1:0，超時是 TIMEOUT 0:15，自己 scancel 則是 CANCELLED by 1000。'),
    ], c)


def _accounting_flow() -> Diagram:
    c = _Canvas()
    c.box(20, 40, 270, 170, 'slurmctld 記憶體', 'retained record', 'MinJobAge=3600 秒', 'scontrol show job', step=0)
    c.arrow(290, 125, 313, 125, step=1)
    c.box(315, 40, 270, 170, 'slurmdbd → MariaDB', 'sacct 查得到', '本 lab 沒設 purge', step=1)
    c.box(610, 40, 270, 170, '檔案', 'shared/demos/', 'shared/course/', '手動刪除才消失', step=2)
    c.arrow(20, 250, 880, 250)
    c.text(880, 275, '時間 →', anchor='end', size=12)
    c.line(155, 242, 155, 258, step=0)
    c.text(155, 236, '1 小時後消失', step=0, size=12)
    c.text(450, 236, '永久保存', step=1, size=12)
    c.text(745, 236, '直到手動刪除', step=2, size=12)
    return _diagram('accounting_flow', '紀錄保存在哪裡、多久', 290, [
        ('slurmctld 記憶體中的 retained record：`MinJobAge=3600` 秒後消失，`scontrol show job` 查不到',
         '工作結束後 controller 只在記憶體保留 MinJobAge=3600 秒，期間 scontrol show job 還看得到細節，之後就查不到了。'),
        ('slurmdbd → MariaDB：`sacct` 永久查得到（本 lab 沒設 purge）',
         'slurmdbd 把每個工作與 step 的紀錄寫進 MariaDB，本 lab 沒有設定 Purge 參數，所以 sacct 可以一直查到。'),
        ('教材的 run 目錄 `shared/demos/`、你的 `shared/course/`：手動刪除才消失',
         '輸出檔、示範 run 的收據與你的學習紀錄都是 /shared 上的普通檔案，Slurm 不會自動清除它們。'),
    ], c)


def _drain_flow() -> Diagram:
    c = _Canvas()
    c.box(20, 40, 250, 64, '管理者', 'scontrol update … State=DRAIN', step=0, size=11)
    c.arrow(270, 72, 338, 72, step=0)
    c.box(340, 40, 300, 210, '')
    c.text(360, 64, 'cpu02', anchor='start', bold=True)
    c.text(625, 64, 'State: DRAIN（drng）', step=0, anchor='end', size=13)
    c.box(360, 100, 260, 50, '執行中的 job', '繼續跑完', step=1, fill=BOX_FILL)
    c.box(20, 160, 250, 64, '新 job', 'Reason=ReqNodeNotAvail', step=2, size=11)
    c.arrow(270, 192, 330, 192, step=2, dashed=True)
    c.text(305, 182, '✗', step=2, bold=True)
    c.box(20, 270, 250, 64, '管理者', 'scontrol update … State=RESUME', step=3, size=11)
    c.path('M270,302 H490 V252', step=3)
    c.text(490, 232, 'State: IDLE', step=3, size=13)
    c.box(700, 40, 180, 64, 'cpu01', '照常接新工作', size=11)
    return _diagram('drain_flow', 'DRAIN 不是關機', 345, [
        ('`scontrol update NodeName=cpu02 State=DRAIN Reason=…`',
         '只有管理者能改節點狀態；Reason 必填，寫清楚是誰、為什麼，其他人看到才知道能不能動。'),
        ('執行中的工作繼續跑完',
         'DRAIN 不會殺掉任何程序；有工作還在跑時 sinfo 顯示 drng（draining），跑完後才變成 drain。'),
        ('新工作不會被排到 cpu02（Reason=ReqNodeNotAvail）',
         '排程器把 DRAIN 的節點視為不可用；指定要 cpu02 的工作會 PENDING，Reason 顯示 ReqNodeNotAvail。'),
        ('`State=RESUME` 後恢復 idle',
         'RESUME 清掉 DRAIN 與 Reason，節點回到 idle，等待中的工作很快就會被排上去。'),
    ], c)


COMPONENTS = _components()
JOB_STATES = _job_states()
ALLOCATION_STEP_TASK = _allocation_step_task()
SCHEDULING = _scheduling()
ARRAY_DEPENDENCY = _array_dependency()
GPU_GRES = _gpu_gres()
FAILURE_LAYERS = _failure_layers()
ACCOUNTING_FLOW = _accounting_flow()
DRAIN_FLOW = _drain_flow()

ALL = [COMPONENTS, JOB_STATES, ALLOCATION_STEP_TASK, SCHEDULING, ARRAY_DEPENDENCY,
       GPU_GRES, FAILURE_LAYERS, ACCOUNTING_FLOW, DRAIN_FLOW]
