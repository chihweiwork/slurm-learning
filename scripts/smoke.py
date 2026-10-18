#!/usr/bin/env python3
"""Exercise the real Compose/Slurm lab; save command evidence under shared/results.

Agreed test seams: docker compose CLI, non-root Slurm submission/query CLI,
actual job stdout and task-observed affinity/cgroups, and root lifecycle CLI.
There are no mocked schedulers, source-text checks, or accounting dependencies.
Run only against this project while its lab nodes are otherwise idle. Every
created job is tracked; cleanup never cancels jobs belonging to another run.

List scenarios without touching Docker or results with --list-cases. Repeat
--case NAME to select scenarios (nodes-partitions always runs first), or use
--section core/gpu. Selection cannot be combined with --skip-lifecycle.
Reports identify full-suite, selected-case, section, and skipped-suite runs.
"""
import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from dataclasses import dataclass
from functools import partial
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import traceback
import uuid

from slurm_cli import compose_argv, parse_job_id, run_command
from gpu_smoke import gpu_cases
from pipeline_smoke import csv_pipeline_failure_recovery, csv_pipeline_success


ROOT = Path(__file__).resolve().parents[1]
CPUSETS = {"cpu01": {0, 1, 8, 9}, "cpu02": {2, 3, 10, 11}, "gpu01": {4, 5, 12, 13}}
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"}
PROBE = "/opt/lab/examples/cpu_probe.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fields(line):
    return dict(re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9_]*)=(\S+)", line))


def json_lines(text):
    values = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


class Smoke:
    def __init__(self):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.run_host = ROOT / "shared" / "results" / self.run_id
        self.run_host.mkdir(parents=True)
        self.run_dir = "/shared/results/" + self.run_id
        self.jobs = set()
        self.outputs = {}
        self.output_templates = {}
        self.drained = set()
        self.report = {"run_id": self.run_id, "started": datetime.now(timezone.utc).isoformat(),
                       "status": "running", "cases": [], "commands": [], "created_job_ids": [],
                       "cleanup_errors": [], "job_ownership": {}, "submissions": []}

    require = staticmethod(require)

    def save(self):
        temporary = self.run_host / ".report.json.tmp"
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.replace(self.run_host / "report.json")

    def command(self, argv, timeout=30, check=True):
        started = time.monotonic()
        record = {"argv": list(argv)}
        try:
            result = run_command(argv, cwd=ROOT, timeout=timeout)
            record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record["error"] = str(exc)
            raise
        finally:
            record["seconds"] = round(time.monotonic() - started, 3)
            self.report["commands"].append(record)
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {shlex.join(argv)}\n{result.stdout}\n{result.stderr}")
        return result

    def compose(self, *args, user="lab", service="controller", timeout=30, check=True):
        return self.command(compose_argv(*args, user=user, service=service), timeout, check)

    def _submit(self, name, arguments, options, defaults=(), array_output=False):
        options = tuple(options)
        array_output = array_output or any(option == "--array" or option.startswith("--array=")
                                           or option.startswith("-a") for option in options)
        pattern = "%A_%a" if array_output else "%j"
        output = f"{self.run_dir}/{name}-{pattern}.out"
        for index, option in enumerate(options):
            if option in ("--output", "-o"):
                output = options[index + 1]
            elif option.startswith("--output="):
                output = option.split("=", 1)[1]
            elif option.startswith("-o"):
                output = option[2:]
        argv = compose_argv("sbatch", "--parsable", *defaults,
                            f"--job-name=smoke-{self.run_id}-{name}", f"--chdir={self.run_dir}",
                            f"--output={output}", *options, *arguments)
        attempt = {"name": name, "argv": argv, "status": "unknown",
                   "started": datetime.now(timezone.utc).isoformat()}
        self.report["submissions"].append(attempt)
        self.save()
        result = self.command(argv, check=False)
        if result.returncode:
            attempt.update(status="failed", returncode=result.returncode, stderr=result.stderr)
            self.save()
            raise RuntimeError(f"sbatch failed: {result.stderr}")
        job_id = parse_job_id(result.stdout)
        self.jobs.add(job_id)
        if not output.startswith("/"):
            output = f"{self.run_dir}/{output}"
        self.output_templates[job_id] = output
        self.outputs[job_id] = output.replace("%A", job_id).replace("%j", job_id).replace("%a", "4294967294")
        attempt.update(status="succeeded", job_id=job_id)
        self.report["job_ownership"][job_id] = {
            "name": f"smoke-{self.run_id}-{name}", "uid": 1000,
            "work_dir": self.run_dir, "submit_time": None,
        }
        self.report["created_job_ids"] = sorted(self.jobs, key=int)
        self.save()
        records = self.owned_records(job_id)
        times = {record["submit_time"]["number"] for record in records}
        if len(times) == 1:
            self.report["job_ownership"][job_id]["submit_time"] = times.pop()
            self.save()
        return job_id

    def submit(self, name, command, options=()):
        return self._submit(name, ("--wrap", "set -eu; " + command), options,
                            ("--partition=cpu", "--nodes=1", "--ntasks=1",
                             "--cpus-per-task=1", "--mem=128M", "--time=00:04:00"))

    def submit_script(self, name, script, script_args=(), options=()):
        """Run a public sbatch file, preserving its resource and array defaults."""
        # %A/%a also work for non-arrays (%a is Slurm's NO_VAL sentinel).
        # This handles arrays declared inside the script, not only CLI options.
        return self._submit(name, (str(script), *map(str, script_args)), options, array_output=True)

    def owned_records(self, job_id):
        job_id = str(job_id)
        require(job_id in self.jobs and job_id in self.report["job_ownership"],
                f"Job {job_id} has no saved submission ownership")
        result = self.compose("scontrol", "--json", "show", "jobs", job_id, check=False, timeout=5)
        if result.returncode:
            require("Invalid job id" in result.stderr, f"Ownership query failed: {result.stderr}")
            return []
        payload = json.loads(result.stdout)
        require(isinstance(payload, dict) and payload.get("errors") == []
                and isinstance(payload.get("jobs"), list), f"Invalid ownership response: {payload}")
        records = payload["jobs"]
        identity = self.report["job_ownership"][job_id]
        for record in records:
            array_id = record["array_job_id"]
            parent = array_id.get("number") if array_id.get("set") and not array_id.get("infinite") else None
            require(str(record["job_id"]) == job_id or str(parent) == job_id,
                    f"Unexpected job in parent lookup: {record}")
            require(record["name"] == identity["name"] and record["user_id"] == identity["uid"]
                    and record["current_working_directory"] == identity["work_dir"],
                    f"Refusing reused or foreign job {job_id}: {record}")
            submitted = record["submit_time"]
            require(submitted.get("set") and not submitted.get("infinite")
                    and isinstance(submitted.get("number"), int) and submitted["number"] > 0,
                    f"Missing SubmitTime for job {job_id}: {submitted}")
            require(identity["submit_time"] is None or submitted["number"] == identity["submit_time"],
                    f"SubmitTime changed for job {job_id}; refusing cancellation")
            require(isinstance(record["job_state"], list) and record["job_state"],
                    f"Missing job state for owned job {job_id}")
        return records

    def cancel(self, job_id):
        records = self.owned_records(job_id)
        if not any(not (set(record["job_state"]) & TERMINAL) for record in records):
            return
        result = self.compose("scancel", str(job_id), check=False, timeout=15)
        require(not result.returncode or "Invalid job id" in result.stderr
                or "already completing or completed" in result.stderr,
                f"scancel {job_id}: {result.stderr}")

    def resume_owned(self, node):
        require(node in self.drained, f"No owned DRAIN for {node}")
        current = fields(self.compose("scontrol", "show", "node", node, "-o").stdout)
        require(current.get("Reason") == f"smoke-{self.run_id}",
                f"Refusing RESUME: {node} Reason changed: {current.get('Reason')}")
        if "DRAIN" in current.get("State", ""):
            self.compose("scontrol", "update", f"NodeName={node}", "State=RESUME", user="root", timeout=20)
        self.drained.remove(node)

    def job(self, job_id):
        result = self.compose("scontrol", "show", "job", "-o", str(job_id))
        records = [fields(line) for line in result.stdout.splitlines() if "JobId=" in line]
        require(len(records) == 1, f"Expected one retained job record for {job_id}: {result.stdout}")
        return records[0]

    def wait_until(self, description, predicate, timeout=120):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(1)
        raise TimeoutError(f"Timed out after {timeout}s: {description}; last={last!r}")

    def wait_state(self, job_id, states, timeout=120):
        if isinstance(states, str):
            states = {states}
        def ready():
            record = self.job(job_id)
            state = record.get("JobState")
            if state in states:
                return record
            require(state not in TERMINAL, f"Job {job_id} ended unexpectedly: {record}; output={self.read_output(job_id)}")
            return False
        return self.wait_until(f"job {job_id} state in {sorted(states)}", ready, timeout)

    def finish(self, job_id, expected="COMPLETED", timeout=120):
        record = self.wait_state(job_id, TERMINAL, timeout)
        require(record["JobState"] == expected, f"Job {job_id}: expected {expected}, got {record}; output={self.read_output(job_id)}")
        if expected == "COMPLETED":
            require(record.get("ExitCode") == "0:0", f"Job {job_id} nonzero exit: {record}")
        return record

    def read_output(self, job_id):
        job_id = str(job_id)
        path = self.outputs.get(job_id)
        if not path and "_" in job_id:
            parent, index = job_id.split("_", 1)
            template = self.output_templates.get(parent)
            if template and index.isdigit():
                physical_id = self.job(job_id)["JobId"] if "%j" in template else job_id
                path = template.replace("%A", parent).replace("%a", index).replace("%j", physical_id)
                self.outputs[job_id] = path
        if not path:
            return ""
        host_path = ROOT / "shared" / Path(path).relative_to("/shared")
        return host_path.read_text(errors="replace") if host_path.exists() else ""

    def probe(self, mode, *args):
        return shlex.join(["srun", "--cpu-bind=threads", "python3", PROBE, mode, *args])

    def release(self, name):
        (self.run_host / name).touch()

    def wait_started(self, job_id):
        self.wait_state(job_id, "RUNNING")
        return self.wait_until(f"job {job_id} workload starts", lambda: json_lines(self.read_output(job_id)))

    def pending_for(self, job_id, seconds=3):
        records = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            record = self.job(job_id)
            require(record.get("JobState") == "PENDING", f"Job {job_id} was not kept pending: {record}")
            records.append(record)
            time.sleep(1)
        return records

    def inventory(self):
        self.compose("scontrol", "ping")
        active_queue = self.compose("squeue", "--all", "--array", "--noheader", "--format=%i|%T|%P|%R").stdout
        require(not active_queue.strip(),
                f"Smoke requires an empty active queue, including held/pending jobs; existing jobs left untouched:\n{active_queue}")
        nodes_text = self.compose("scontrol", "show", "nodes", "-o").stdout
        nodes = {record["NodeName"]: record for record in map(fields, nodes_text.splitlines()) if "NodeName" in record}
        require(set(nodes) == set(CPUSETS), f"Unexpected nodes: {nodes}")
        for name, node in nodes.items():
            require(int(node.get("CPUEfctv", "0")) == 4, f"Expected four schedulable CPUs: {node}")
            require(int(node.get("RealMemory", "0")) == (14336 if name == "gpu01" else 7168), f"Wrong node memory: {node}")
            require(not any(bad in node.get("State", "") for bad in ("DOWN", "DRAIN", "FAIL", "UNKNOWN", "NOT_RESPONDING")), f"Unhealthy node: {node}")
            require(node.get("CPUAlloc") == "0", f"Smoke requires idle lab nodes, found existing allocation: {node}")
        partitions = {}
        for line in self.compose("scontrol", "show", "partition", "-o").stdout.splitlines():
            record = fields(line)
            if "PartitionName" in record:
                partitions[record["PartitionName"]] = record
        for name, members in (("cpu", {"cpu01", "cpu02"}), ("gpu", {"gpu01"})):
            require(name in partitions, f"Missing {name} partition")
            actual = set(self.compose("scontrol", "show", "hostnames", partitions[name]["Nodes"]).stdout.split())
            require(actual == members, f"Wrong {name} partition members: {actual}")
            require(partitions[name]["State"] == "UP", f"Partition unavailable: {partitions[name]}")
        require(partitions["cpu"].get("Default") == "YES", "cpu must be the default partition")
        require(re.search(r"(?:^|,)gpu(?::[^:,()]+)?:1(?:\(|,|$)", nodes["gpu01"].get("Gres", "")), f"Expected exactly one GPU GRES: {nodes['gpu01']}")
        for name in ("cpu01", "cpu02"):
            require("gpu" not in nodes[name].get("Gres", ""), f"GPU duplicated onto {name}")
        config = self.compose("scontrol", "show", "config").stdout
        return {"nodes": nodes, "partitions": partitions, "config": config, "active_queue": active_queue,
                "slurm_version": self.compose("srun", "--version").stdout,
                "compose_version": self.command(["docker", "compose", "version"]).stdout}

    def cpu_affinity(self):
        evidence = []
        for node in ("cpu01", "cpu02"):
            for cpus in (1, 4):
                job_id = self.submit(f"affinity-{node}-{cpus}", self.probe("affinity"),
                                     (f"--nodelist={node}", f"--cpus-per-task={cpus}"))
                self.finish(job_id)
                records = json_lines(self.read_output(job_id))
                require(len(records) == 1, f"Missing task result: {self.read_output(job_id)}")
                record = records[0]
                actual = set(record["affinity"])
                require(record["hostname"] == node and record["uid"] == 1000 and record["job_id"] == job_id,
                        f"Wrong task identity: {record}")
                require(record["sum"] == 50005000, f"CPU computation incorrect: {record}")
                require(actual <= CPUSETS[node] and len(actual) == cpus, f"CPU affinity violates {node} cpuset or requested {cpus} threads: {record}")
                evidence.append(record)
        return evidence

    def memory_oom(self):
        release = "memory-neighbor.release"
        neighbor = self.submit("memory-neighbor", self.probe("hold", "--release", f"{self.run_dir}/{release}"), ("--nodelist=cpu01",))
        self.wait_started(neighbor)
        command = ("set +e; " + self.probe("memory") + "; status=$?; "
                   "python3 " + PROBE + " oom-events; exit \"$status\"")
        offender = self.submit("memory-oom", command, ("--nodelist=cpu01", "--mem=128M"))
        ended = self.wait_state(offender, TERMINAL)
        require(ended.get("ExitCode") != "0:0", "Memory offender unexpectedly succeeded")
        records = json_lines(self.read_output(offender))
        require(records and "limits" in records[0], f"OOM workload did not report its own cgroup: {records}")
        numeric = [int(entry["memory.max"]) for entry in records[0]["limits"] if entry["memory.max"].isdigit()]
        require(numeric and min(numeric) == 128 * 1024 * 1024, f"Missing 128 MiB per-job limit: {records}")
        require(any(entry["memory.max"] == str(128 * 1024 * 1024) and entry["memory.swap.max"] == "0"
                    for entry in records[0]["limits"]), f"Job swap is not disabled: {records}")
        observations = [record for record in records if record.get("event") == "oom_observation"]
        require(observations and any(
            entry["memory.max"] == str(128 * 1024 * 1024) and entry["events"].get("oom_kill", 0) > 0
            for entry in observations[0]["limits"]),
            f"No kernel OOM-kill event in the job's 128 MiB cgroup: {observations}")
        require(self.job(neighbor)["JobState"] == "RUNNING", "OOM terminated the neighboring job")
        self.release(release)
        neighbor_result = self.finish(neighbor)
        control = self.submit("memory-after", self.probe("affinity"), ("--nodelist=cpu01",))
        self.finish(control)
        return {"oom": ended, "task": records, "neighbor": neighbor_result, "subsequent_job": control}

    def resource_queue(self):
        release = "queue.release"
        blocker = self.submit("queue-blocker", self.probe("hold", "--release", f"{self.run_dir}/{release}"),
                              ("--nodelist=cpu01", "--cpus-per-task=4", "--exclusive"))
        self.wait_started(blocker)
        waiter = self.submit("queue-waiter", self.probe("affinity"), ("--nodelist=cpu01",))
        self.wait_state(waiter, "PENDING")
        pending = self.pending_for(waiter)
        require(any(record.get("Reason") in {"Resources", "Priority"} for record in pending), f"Not pending for resource contention: {pending}")
        self.release(release)
        self.finish(blocker)
        return {"pending": pending, "released": self.finish(waiter)}

    def arrays_dependencies(self):
        array_id = self.submit("array", self.probe("array"), ("--array=0-3", f"--output={self.run_dir}/array-%A_%a.out"))
        array_results = []
        for index in range(4):
            task_id = f"{array_id}_{index}"
            self.finish(task_id)
            values = json_lines(self.read_output(task_id))
            require(len(values) == 1 and values[0]["array_index"] == index and values[0]["array_job_id"] == array_id,
                    f"Wrong array index output: {values}")
            array_results.append(values[0])
        release = "dependency.release"
        first = self.submit("dependency-first", self.probe("hold", "--release", f"{self.run_dir}/{release}"))
        self.wait_started(first)
        after = self.submit("dependency-after", self.probe("affinity"), (f"--dependency=afterok:{first}",))
        pending = self.pending_for(after)
        require(all(record.get("Reason") == "Dependency" for record in pending), f"Missing dependency wait: {pending}")
        self.release(release)
        first_result = self.finish(first)
        after_result = self.finish(after)
        require(after_result["StartTime"] >= first_result["EndTime"], f"Dependent started before successful prerequisite ended: {after_result}")
        failure = self.submit("dependency-failure", "exit 7")
        forbidden = self.submit("dependency-never", "printf 'DEPENDENCY_MUST_NOT_RUN\\n'", (f"--dependency=afterok:{failure}", "--kill-on-invalid-dep=no"))
        failure_result = self.finish(failure, "FAILED")
        require(failure_result.get("ExitCode") == "7:0", f"Wrong prerequisite failure: {failure_result}")
        never = self.pending_for(forbidden, seconds=4)
        require(all(record.get("Reason") in {"Dependency", "DependencyNeverSatisfied"} for record in never), f"Failed prerequisite not blocking dependent: {never}")
        require(not self.read_output(forbidden), "Dependent of failed prerequisite executed")
        self.cancel(forbidden)
        self.finish(forbidden, "CANCELLED")
        return {"array": array_results, "success": [first_result, after_result], "failed": failure_result, "blocked": never}

    def mpi(self):
        binary = f"{self.run_dir}/mpi-sum"
        self.compose("mpicc", "-O2", "-Wall", "-Wextra", "/opt/lab/examples/mpi_sum.c", "-o", binary, timeout=60)
        job_id = self.submit("mpi", shlex.join(["srun", "--mpi=pmix", "--cpu-bind=threads", binary]),
                             ("--nodes=2", "--ntasks=2", "--ntasks-per-node=1", "--nodelist=cpu01,cpu02", "--mem=256M"))
        self.finish(job_id)
        records = json_lines(self.read_output(job_id))
        require(len(records) == 2 and {record.get("hostname") for record in records} == {"cpu01", "cpu02"}, f"MPI did not span nodes: {records}")
        require({record.get("rank") for record in records} == {0, 1} and all(record.get("size") == 2 and record.get("sum") == 3 and record.get("valid") is True for record in records), f"MPI collective incorrect: {records}")
        return records

    def descendant_case(self, timeout_job=False):
        name = "timeout" if timeout_job else "cancel"
        marker = f"{self.run_dir}/{name}-process"
        options = ["--nodelist=cpu01"]
        if timeout_job:
            options.append("--time=00:01:00")
        job_id = self.submit(name, self.probe("descendants", "--marker", marker, "--seconds", "180"), options)
        self.wait_state(job_id, "RUNNING")
        self.wait_until("all three descendants record process identities", lambda: len(list(self.run_host.glob(f"{name}-process.*.json"))) == 3)
        if not timeout_job:
            self.cancel(job_id)
        ended = self.finish(job_id, "TIMEOUT" if timeout_job else "CANCELLED", timeout=150)
        def gone():
            result = self.compose("python3", PROBE, "check-processes", "--marker", marker, user="root", service="cpu01", check=False)
            require(result.returncode in (0, 1), f"Process cleanup observation failed: {result.stderr}")
            values = json_lines(result.stdout)
            require(len(values) == 1 and values[0]["record_count"] == 3, f"Missing process evidence: {result.stdout}")
            return values[0] if result.returncode == 0 else False
        cleaned = self.wait_until("cancelled descendants disappear", gone, timeout=30)
        next_job = self.submit(name + "-after", self.probe("affinity"), ("--nodelist=cpu01", "--cpus-per-task=4", "--exclusive"))
        self.finish(next_job)
        return {"job": ended, "descendants": cleaned, "resource_reuse_job": next_job}

    def drain_resume(self):
        node = "cpu02"
        before = fields(self.compose("scontrol", "show", "node", node, "-o").stdout)
        require("DRAIN" not in before.get("State", ""), "Refusing to alter an already-drained node")
        release = "drain.release"
        holder = self.submit("drain-holder", self.probe("hold", "--release", f"{self.run_dir}/{release}",
                                                     "--seconds", "180"),
                             (f"--nodelist={node}", "--cpus-per-task=4", "--exclusive"))
        self.wait_started(holder)
        self.drained.add(node)
        self.report.setdefault("maintenance", []).append(
            {"node": node, "before": before, "reason": f"smoke-{self.run_id}"})
        self.save()
        self.compose("scontrol", "update", f"NodeName={node}", "State=DRAIN", f"Reason=smoke-{self.run_id}", user="root")
        drained = fields(self.compose("scontrol", "show", "node", node, "-o").stdout)
        require("DRAIN" in drained.get("State", ""), f"Node did not drain: {drained}")
        require(self.job(holder)["JobState"] == "RUNNING", "DRAIN killed an existing holder")
        waiter = self.submit("drain-waiter", self.probe("affinity"), (f"--nodelist={node}",))
        pending = self.pending_for(waiter)
        self.release(release)
        holder_result = self.finish(holder)
        after_release = self.pending_for(waiter)
        self.resume_owned(node)
        return {"before": before, "drained": drained, "pending": pending, "holder": holder_result,
                "pending_after_holder_finished": after_release, "resumed_job": self.finish(waiter)}

    def controller_restart(self):
        completed = self.submit("restart-completed", self.probe("affinity"), ("--nodelist=cpu02",))
        self.finish(completed)
        saved_output = self.read_output(completed)
        release = "restart.release"
        active = self.submit("restart-active", self.probe("hold", "--release", f"{self.run_dir}/{release}", "--seconds", "240"),
                             ("--nodelist=cpu01", "--cpus-per-task=4", "--exclusive", "--time=00:05:00"))
        self.wait_started(active)
        queued = self.submit("restart-queued", self.probe("affinity"), ("--nodelist=cpu01",))
        pending = self.pending_for(queued)
        before = self.job(active)
        self.command(["docker", "compose", "restart", "controller"], timeout=90)
        def controller_ready():
            try:
                result = self.compose("scontrol", "ping", timeout=10, check=False)
            except subprocess.TimeoutExpired:
                return False
            return result.returncode == 0 and "UP" in result.stdout
        self.wait_until("controller returns after restart", controller_ready, timeout=120)
        after = self.job(active)
        require(after["JobState"] == "RUNNING" and after["StartTime"] == before["StartTime"], f"Active job not preserved: before={before}, after={after}")
        self.pending_for(queued)
        self.finish(completed)
        require(self.read_output(completed) == saved_output, "Completed job output changed across controller restart")
        self.release(release)
        active_result = self.finish(active)
        queued_result = self.finish(queued)
        reconnected = {}
        for node in CPUSETS:
            def responsive(node=node):
                record = fields(self.compose("scontrol", "show", "node", node, "-o").stdout)
                state = record.get("State", "")
                return record if state and not any(bad in state for bad in ("DOWN", "UNKNOWN", "NOT_RESPONDING", "DRAIN", "FAIL")) else False
            reconnected[node] = self.wait_until(f"{node} reconnects", responsive)
        return {"active_before": before, "active_after": after, "active_completed": active_result,
                "queued_before": pending, "queued_completed": queued_result, "preserved_completed_job": completed,
                "nodes": reconnected}

    def failure_evidence(self):
        evidence = {}
        for args in (("sinfo", "-Nel"), ("squeue", "--all", "--long"), ("scontrol", "show", "nodes", "-o")):
            try:
                result = self.compose(*args, check=False, timeout=15)
                evidence[shlex.join(args)] = {"stdout": result.stdout, "stderr": result.stderr}
            except Exception as exc:
                evidence[shlex.join(args)] = str(exc)
        try:
            evidence["controller logs"] = self.command(
                ["docker", "compose", "logs", "--no-color", "--tail=100", "controller"],
                check=False, timeout=15).stdout
        except Exception as exc:
            evidence["controller logs"] = str(exc)
        for service in ("cpu01", "cpu02", "gpu01"):
            try:
                evidence[service + " journal"] = self.compose(
                    "journalctl", "--no-pager", "-n", "100", "-u", "slurmd", "-u", "munge",
                    user="root", service=service, check=False, timeout=15).stdout
            except Exception as exc:
                evidence[service + " journal"] = str(exc)
        evidence["job_outputs"] = {job_id: self.read_output(job_id) for job_id in self.outputs}
        return evidence

    def run_case(self, name, callback):
        started = time.monotonic()
        case = {"name": name}
        self.report["cases"].append(case)
        try:
            case["evidence"] = callback()
            case["status"] = "passed"
            print(f"PASS {name}", flush=True)
        except Exception as exc:
            case.update(status="failed", error=str(exc), traceback=traceback.format_exc())
            case["diagnostics"] = self.failure_evidence()
            print(f"FAIL {name}: {exc}", file=sys.stderr, flush=True)
            raise
        finally:
            case["seconds"] = round(time.monotonic() - started, 3)
            self.save()

    def cleanup(self):
        # Exact owned IDs only; never scancel --user, --all, or a partition.
        for job_id in sorted(self.jobs, key=int):
            try:
                self.cancel(job_id)
            except Exception as exc:
                self.report["cleanup_errors"].append(f"scancel {job_id}: {exc}")
        for node in sorted(self.drained.copy()):
            try:
                self.resume_owned(node)
            except Exception as exc:
                self.report["cleanup_errors"].append(f"resume {node}: {exc}")
        if self.jobs:
            try:
                def jobs_gone():
                    result = self.compose("squeue", "--noheader", "--jobs=" + ",".join(sorted(self.jobs, key=int)), "--format=%i %T", check=False)
                    require(result.returncode == 0 or "Invalid job id" in result.stderr, f"Cleanup query failed: {result.stderr}")
                    return not result.stdout.strip()
                self.wait_until("all smoke jobs leave the active queue", jobs_gone, timeout=45)
            except Exception as exc:
                self.report["cleanup_errors"].append(str(exc))
        self.report["created_job_ids"] = sorted(self.jobs, key=int)
        unknown = [attempt for attempt in self.report["submissions"] if attempt["status"] == "unknown"]
        if unknown:
            self.report["cleanup_errors"].append(
                "Unconfirmed submissions require manual name/UID/workdir/time reconciliation; never automatically retry")


@dataclass(frozen=True)
class Case:
    name: str
    section: str
    maintenance: bool
    callback: Callable[[], object]


def case_catalog(smoke=None):
    """Build the sole scenario catalog; construction never executes a case."""
    return [
        Case("nodes-partitions", "core", False, partial(Smoke.inventory, smoke)),
        Case("cpu-affinity", "core", False, partial(Smoke.cpu_affinity, smoke)),
        Case("memory-oom-isolation", "core", False, partial(Smoke.memory_oom, smoke)),
        Case("resource-queue-release", "core", False, partial(Smoke.resource_queue, smoke)),
        Case("arrays-and-dependencies", "core", False, partial(Smoke.arrays_dependencies, smoke)),
        Case("cross-node-mpi", "core", False, partial(Smoke.mpi, smoke)),
        Case("cancellation-descendant-cleanup", "core", False, partial(Smoke.descendant_case, smoke)),
        Case("time-limit-descendant-cleanup", "core", False,
             partial(Smoke.descendant_case, smoke, timeout_job=True)),
        Case("drain-resume", "core", True, partial(Smoke.drain_resume, smoke)),
        Case("controller-restart-persistence", "core", True, partial(Smoke.controller_restart, smoke)),
        Case("csv-pipeline-success", "core", False, partial(csv_pipeline_success, smoke)),
        Case("csv-pipeline-failure-recovery", "core", False, partial(csv_pipeline_failure_recovery, smoke)),
        *(Case(name, "gpu", False, callback) for name, callback in gpu_cases(smoke)),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-cases", action="store_true", help="List case names without Docker or filesystem side effects")
    parser.add_argument("--case", action="append", dest="cases", metavar="NAME",
                        help="Select a case; repeat to select more (inventory always runs first)")
    parser.add_argument("--skip-lifecycle", action="store_true", help="Skip drain/resume and controller restart; not a full-suite pass")
    parser.add_argument("--section", choices=("core", "gpu", "all"), default=None,
                        help="Select real acceptance scenarios; default includes independent-image GPU jobs")
    args = parser.parse_args()
    catalog = case_catalog()
    names = {case.name for case in catalog}
    if args.list_cases and (args.cases is not None or args.section is not None or args.skip_lifecycle):
        parser.error("--list-cases cannot be combined with execution options")
    if args.cases is not None:
        if args.section is not None or args.skip_lifecycle:
            parser.error("--case cannot be combined with --section or --skip-lifecycle")
        unknown = set(args.cases) - names
        if unknown:
            parser.error("unknown case(s): " + ", ".join(sorted(unknown)))
    if args.list_cases:
        for case in catalog:
            print(case.name)
        return 0

    section = args.section or "all"
    requested = set(args.cases or ())
    selected = [case for case in catalog
                if case.name == "nodes-partitions"
                or (case.name in requested if args.cases is not None
                    else section == "all" or case.section == section)]
    selected_names = {case.name for case in selected}
    skipped = {case.name for case in selected if args.skip_lifecycle and case.maintenance}
    full_suite = selected_names == names and not skipped
    scope = ("case-selection" if args.cases is not None else
             "section" if section != "all" else
             "partial-suite" if skipped else "full-suite")
    smoke = Smoke()
    smoke.report.update(scope=scope, full_suite=full_suite, section=section,
                        selected_cases=[case.name for case in selected])
    smoke.save()
    failed = False
    try:
        for case in case_catalog(smoke):
            if case.name not in selected_names:
                continue
            if case.name in skipped:
                smoke.report["cases"].append({"name": case.name, "status": "skipped",
                                              "reason": "--skip-lifecycle"})
                smoke.save()
            else:
                smoke.run_case(case.name, case.callback)
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        smoke.report["error"] = str(exc) or type(exc).__name__
    finally:
        smoke.cleanup()
        failed = failed or bool(smoke.report["cleanup_errors"])
        smoke.report["status"] = "failed" if failed else "partial" if skipped else "passed"
        smoke.report["finished"] = datetime.now(timezone.utc).isoformat()
        smoke.save()
        print(f"Evidence: {smoke.run_host / 'report.json'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
