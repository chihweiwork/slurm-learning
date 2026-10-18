#!/usr/bin/env python3
"""Small, bounded workloads observed by scripts/smoke.py through Slurm."""
import argparse
import json
import os
from pathlib import Path
import socket
import time


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def identity():
    return {
        "hostname": socket.gethostname(),
        "uid": os.getuid(),
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "affinity": sorted(os.sched_getaffinity(0)),
        "sum": sum(range(10001)),
    }


def memory_limits():
    """Read the task's cgroup and ancestors, not the container's top limit."""
    relative = next(line.split(":", 2)[2] for line in
                    Path("/proc/self/cgroup").read_text().splitlines()
                    if line.startswith("0::"))
    root = Path("/sys/fs/cgroup")
    current = root / relative.lstrip("/")
    result = []
    while current == root or root in current.parents:
        memory = current / "memory.max"
        if memory.exists():
            result.append({"path": str(current), "memory.max": memory.read_text().strip(),
                           "memory.swap.max": (current / "memory.swap.max").read_text().strip(),
                           "events": {key: int(value) for key, value in
                                      (line.split() for line in (current / "memory.events").read_text().splitlines())}})
        if current == root:
            break
        current = current.parent
    return result


def process_identity():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": os.getpid(), "starttime": fields[19], "hostname": socket.gethostname()}


def hold(release, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if release and Path(release).exists():
            emit({"released": True, **identity()})
            return
        time.sleep(0.2)
    if release:
        raise SystemExit("release marker not received before workload deadline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("affinity", "array", "memory", "oom-events", "hold", "descendants", "check-processes"))
    parser.add_argument("--release")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--marker")
    args = parser.parse_args()
    if args.mode == "affinity":
        emit(identity())
    elif args.mode == "array":
        emit({**identity(), "array_index": int(os.environ["SLURM_ARRAY_TASK_ID"]),
              "array_job_id": os.environ["SLURM_ARRAY_JOB_ID"]})
    elif args.mode == "memory":
        limits = memory_limits()
        emit({**identity(), "limits": limits, "allocation_ceiling_mib": 256})
        # Never stress the 8 GiB container/host: touch at most twice the requested
        # 128 MiB job limit, even if the job cgroup is accidentally unconfigured.
        blocks = []
        for _ in range(256):
            block = bytearray(1024 * 1024)
            for offset in range(0, len(block), 4096):
                block[offset] = 1
            blocks.append(block)
            time.sleep(0.005)
        emit({"unexpected_allocation_success_mib": len(blocks)})
        raise SystemExit(42)
    elif args.mode == "oom-events":
        emit({"event": "oom_observation", "limits": memory_limits()})
    elif args.mode == "hold":
        emit({"started": True, **identity()})
        hold(args.release, args.seconds)
    elif args.mode == "descendants":
        # Both child and grandchild remain in the Slurm step cgroup. Every
        # process records starttime to distinguish cleanup from PID reuse.
        role = "parent"
        child = os.fork()
        if child == 0:
            role = "child"
            if os.fork() == 0:
                role = "grandchild"
        record = {**process_identity(), "role": role}
        Path(f"{args.marker}.{role}.json").write_text(json.dumps(record))
        emit(record)
        hold(None, args.seconds)
    elif args.mode == "check-processes":
        live = []
        records = sorted(Path(args.marker).parent.glob(Path(args.marker).name + ".*.json"))
        for record_file in records:
            record = json.loads(record_file.read_text())
            stat = Path(f"/proc/{record['pid']}/stat")
            try:
                fields = stat.read_text().rsplit(")", 1)[1].split()
            except FileNotFoundError:
                continue
            if fields[19] == record["starttime"] and fields[0] != "Z":
                live.append(record)
        emit({"record_count": len(records), "live": live})
        raise SystemExit(bool(live))


if __name__ == "__main__":
    main()
