"""Tiny Slurm-like scheduler simulator for the course pages (pure functions, no I/O).

Time is measured in whole minutes. The simulator is event driven: at each event time
it releases finished jobs, then scans pending jobs in submission order (FIFO).
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape

NODES = {
    'cpu01': {'cpus': 4, 'gpus': 0, 'partition': 'cpu'},
    'cpu02': {'cpus': 4, 'gpus': 0, 'partition': 'cpu'},
    'gpu01': {'cpus': 4, 'gpus': 1, 'partition': 'gpu'},
}
SINGLE_NODE = {'cpu01': NODES['cpu01']}

UNSCHEDULABLE = 'ReqNodeNotAvail（沒有任何節點符合要求）'
COLORS = ('#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4')


@dataclass(frozen=True)
class Job:
    id: str
    cpus: int
    minutes: int
    gpus: int = 0
    partition: str = 'cpu'


@dataclass(frozen=True)
class Placement:
    job_id: str
    node: str | None
    start: int | None
    end: int | None
    slots: tuple[int, ...]
    reason: str


PRESETS = {
    '先來先服務／回填': ([Job('A', 3, 4), Job('B', 4, 3), Job('C', 1, 2)], SINGLE_NODE),
    'GPU 分區': ([Job('A', 2, 3, partition='cpu'), Job('G1', 1, 4, gpus=1, partition='gpu'),
                Job('G2', 1, 2, gpus=1, partition='gpu')], NODES),
}


def _candidates(job, nodes):
    return [name for name, spec in nodes.items() if spec['partition'] == job.partition]


def _ever_fits(job, nodes):
    return any(job.cpus <= nodes[n]['cpus'] and job.gpus <= nodes[n]['gpus'] for n in _candidates(job, nodes))


def _fit(job, nodes, free_cpus, free_gpus):
    """Return (node, slots) for the first node in the partition that fits now, else None."""
    for name in _candidates(job, nodes):
        if len(free_cpus[name]) >= job.cpus and free_gpus[name] >= job.gpus:
            return name, tuple(sorted(free_cpus[name])[:job.cpus])
    return None


def _shadow(job, nodes, free_cpus, free_gpus, running, now):
    """Earliest time the blocked head job could start if running jobs release in end order."""
    cpus = {n: set(s) for n, s in free_cpus.items()}
    gpus = dict(free_gpus)
    for end, node, slots, used_gpus in sorted(running, key=lambda r: r[0]):
        cpus[node] |= set(slots)
        gpus[node] += used_gpus
        if _fit(job, nodes, cpus, gpus):
            return end
    return now  # unreachable for jobs that can ever fit


def schedule(jobs, *, backfill=True, nodes=NODES):
    """Simulate FIFO scheduling, optionally with backfill; return placements in ``jobs`` order.

    - Without backfill the first pending job that does not fit blocks everyone behind it.
    - With backfill a later job may start early only if it fits now and finishes no later
      than the blocked head job's earliest possible start (its shadow time).
    - ``reason`` shows the reason at t=0: jobs started at t=0 get ``''``; of the jobs still
      waiting at t=0 the first gets ``'Resources'`` and the rest ``'Priority'``.
    - Jobs that can never fit any node of their partition get ``node=start=end=None``,
      ``slots=()`` and a reason starting with ``ReqNodeNotAvail``; they never block the queue.
    """
    result: dict[int, Placement] = {}
    free_cpus = {n: set(range(spec['cpus'])) for n, spec in nodes.items()}
    free_gpus = {n: spec['gpus'] for n, spec in nodes.items()}
    running = []  # (end, node, slots, gpus)
    pending = []
    for index, job in enumerate(jobs):
        if _ever_fits(job, nodes):
            pending.append(index)
        else:
            result[index] = Placement(job.id, None, None, None, (), UNSCHEDULABLE)
    started: dict[int, tuple] = {}
    waiting_at_zero: list[int] = []
    now = 0
    while pending:
        for item in [r for r in running if r[0] <= now]:
            running.remove(item)
            _, node, slots, used_gpus = item
            free_cpus[node] |= set(slots)
            free_gpus[node] += used_gpus
        shadow = None
        for index in list(pending):
            job = jobs[index]
            fit = _fit(job, nodes, free_cpus, free_gpus)
            if shadow is not None and fit and now + job.minutes > shadow:
                fit = None
            if fit is None:
                if shadow is None:
                    if not backfill:
                        break
                    shadow = _shadow(job, nodes, free_cpus, free_gpus, running, now)
                continue
            node, slots = fit
            free_cpus[node] -= set(slots)
            free_gpus[node] -= job.gpus
            running.append((now + job.minutes, node, slots, job.gpus))
            started[index] = (node, now, now + job.minutes, slots)
            pending.remove(index)
        if now == 0:
            waiting_at_zero = list(pending)
        if pending:
            now = min(r[0] for r in running)
    for index, (node, start, end, slots) in started.items():
        if index in waiting_at_zero:
            reason = 'Resources' if index == waiting_at_zero[0] else 'Priority'
        else:
            reason = ''
        result[index] = Placement(jobs[index].id, node, start, end, slots, reason)
    return [result[i] for i in range(len(jobs))]


def gantt_svg(placements, *, nodes, width=900):
    """Draw placements as swim lanes (one 18px row per CPU per node) over a minute axis."""
    left, right, top, row, gap = 110, 20, 10, 18, 12
    horizon = max([p.end for p in placements if p.end is not None] + [1])
    scale = (width - left - right) / horizon
    step = 1 if horizon <= 20 else 5 if horizon <= 100 else 10 * (horizon // 100 + 1)
    parts = []
    lane_top = {}
    y = top
    for name, spec in nodes.items():
        lane_top[name] = y
        parts.append(f'<rect x="{left}" y="{y}" width="{width - left - right}" height="{row * spec["cpus"]}" '
                     'fill="none" stroke="currentColor" stroke-width="1" />')
        for cpu in range(spec['cpus']):
            parts.append(f'<text x="{left - 6}" y="{y + cpu * row + 13}" text-anchor="end" '
                         f'fill="currentColor">{escape(name)} CPU{cpu}</text>')
        y += row * spec['cpus'] + gap
    axis = y
    parts.append(f'<line x1="{left}" y1="{axis}" x2="{width - right}" y2="{axis}" stroke="currentColor" />')
    for minute in range(0, horizon + 1, step):
        x = left + minute * scale
        parts.append(f'<line x1="{x:.1f}" y1="{axis}" x2="{x:.1f}" y2="{axis + 4}" stroke="currentColor" />')
        parts.append(f'<text x="{x:.1f}" y="{axis + 18}" text-anchor="middle" fill="currentColor">{minute}</text>')
    parts.append(f'<text x="{left - 6}" y="{axis + 18}" text-anchor="end" fill="currentColor">分鐘</text>')
    for order, p in enumerate(placements):
        if p.node is None or p.node not in lane_top:
            continue
        color = COLORS[order % len(COLORS)]
        x = left + p.start * scale
        w = (p.end - p.start) * scale
        for slot in p.slots:
            sy = lane_top[p.node] + slot * row
            parts.append(f'<rect x="{x:.1f}" y="{sy + 1}" width="{w:.1f}" height="{row - 2}" rx="3" '
                         f'fill="{color}" fill-opacity="0.75" stroke="{color}" />')
            parts.append(f'<text x="{x + w / 2:.1f}" y="{sy + 13}" text-anchor="middle" '
                         f'fill="currentColor">{escape(p.job_id)}</text>')
    y = axis + 40
    for p in placements:
        if p.node is None:
            parts.append(f'<text x="{left}" y="{y}" fill="currentColor">無法排程：{escape(p.job_id)}（ReqNodeNotAvail）</text>')
            y += 18
    height = y
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'font-size="12">' + ''.join(parts) + '</svg>')
