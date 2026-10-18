"""Explicit, at-most-once notebook actions; importing and reading never mutate Slurm.

Register fixed steps in notebook source with ``register_chapter`` and ``Step``.
A step's argv builder receives the saved run (including frozen parameters); its
optional read-only precondition receives that run and fresh query envelopes in
``snapshot['sources']``. Return None to permit, a reason string to block, or a
JSON-serializable evidence dict to permit and preserve in the claim. Registration
is in-memory and may be repeated when notebook code is reloaded. Never register
builders that accept user-provided shell programs, or mutating preconditions.

Only explicit callbacks call prepare_run, execute_once, verify_run or cleanup_run.
Claims survive interruption; a missing receipt is UNKNOWN, never permission to
retry. The flock coordinates these helpers, not an external CLI: use one operator
window. All subprocesses use the existing project's Compose transport.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable
import uuid

from notebook_queries import (
    download_log as _download_log,
    query_jobs,
    query_nodes,
    query_queue,
    read_log as _read_log,
    read_snapshot,
)
from slurm_cli import compose_argv, parse_job_id, run_command

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "shared" / "demos"
EFFECTS = frozenset({"submit", "interactive", "cancel", "drain", "resume",
                     "restart-controller", "restore-controller", "local"})
TERMINAL = frozenset({"COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY",
                      "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"})
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_JOB_ID = re.compile(r"[0-9]+\Z")
_PROBE = "/opt/lab/examples/cpu_probe.py"


@dataclass(frozen=True)
class Step:
    effect: str
    argv: Callable[[dict], list[str]]
    precondition: Callable[[dict, dict], str | dict | None] | None = None


_CHAPTERS: dict[str, tuple[dict[str, Step], Callable[[dict], list[dict]] | None]] = {}


def register_chapter(chapter: str, steps: dict[str, Step], *,
                     verify: Callable[[dict], list[dict]] | None = None) -> None:
    """Register trusted source-code callbacks, without filesystem or CLI effects.

    Verifiers are read-only and return nonempty case records containing ``name``,
    ``status`` (passed/failed/running) and concrete ``evidence``. They may run read-only
    diagnostics. Only verify_run saves their result; refresh never does so.
    """
    _component(chapter)
    if not isinstance(steps, dict) or not steps:
        raise ValueError("A chapter needs fixed, named steps")
    for name, step in steps.items():
        _component(name)
        if not isinstance(step, Step) or step.effect not in EFFECTS or not callable(step.argv):
            raise ValueError(f"Invalid step registration: {name}")
        if step.precondition is not None and not callable(step.precondition):
            raise ValueError(f"Invalid precondition: {name}")
    if verify is not None and not callable(verify):
        raise ValueError("verify must be a read-only callable")
    _CHAPTERS[chapter] = (dict(steps), verify)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _component(value: str) -> str:
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value) or ".." in value:
        raise ValueError("IDs must be 1–64 letters, digits, underscores or hyphens; no paths")
    return value


def _safe(base: Path, path: Path) -> Path:
    """Reject traversal and all symlinks, including the run/base ancestors."""
    if ".." in path.parts:
        raise ValueError(f"Parent traversal is forbidden: {path}")
    absolute = path if path.is_absolute() else base / path
    absolute.relative_to(base)
    absolute.resolve().relative_to(base.resolve())
    current = absolute
    while current != ROOT:
        if current.is_symlink():
            raise ValueError(f"Symlinks are forbidden in run paths: {current}")
        parent = current.parent
        if parent == current:
            raise ValueError("Run paths must remain inside the project")
        current = parent
    return absolute


def _run_path(run_id: str) -> Path:
    return _safe(DEMOS, DEMOS / _component(run_id))


def _json(path: Path, base: Path) -> dict:
    path = _safe(base, path)
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: Path, value: dict, base: Path) -> None:
    path = _safe(base, path)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _claim(path: Path, value: dict, base: Path) -> None:
    path = _safe(base, path)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


class _Busy(Exception):
    pass


@contextmanager
def _action_lock():
    path = _safe(DEMOS, DEMOS / ".actions.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise _Busy("Another explicit action is busy; no command was queued. Try again after it finishes.") from exc
        yield
    finally:
        os.close(fd)


def _blocked(reason: str, **extra) -> dict:
    return {"status": "blocked", "reason": reason, **extra}


def prepare_run(chapter: str, parameters: dict) -> dict:
    """Create a new frozen run only; no scheduler query or job submission."""
    _component(chapter)
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be a JSON object")
    parameters = json.loads(json.dumps(parameters, allow_nan=False))
    _safe(ROOT, DEMOS).mkdir(parents=True, exist_ok=True)
    try:
        with _action_lock():
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
            directory = _run_path(run_id)
            directory.mkdir(exist_ok=False)
            (directory / "actions").mkdir(exist_ok=False)
            metadata = {"run_id": run_id, "chapter": chapter, "parameters": parameters, "started": _now()}
            _atomic_json(directory / "run.json", metadata, directory)
            report = {"run_id": run_id, "started": metadata["started"], "finished": None,
                      "status": "running", "cases": [], "commands": [],
                      "created_job_ids": [], "cleanup_errors": []}
            _atomic_json(directory / "report.json", report, directory)
            _fsync_directory(DEMOS)
            return load_run(run_id)
    except _Busy as exc:
        return _blocked(str(exc))


def load_run(run_id: str) -> dict:
    """Load frozen parameters; a missing run raises FileNotFoundError, never creates one."""
    directory = _run_path(run_id)
    metadata = _json(directory / "run.json", directory)
    if metadata.get("run_id") != run_id or not isinstance(metadata.get("parameters"), dict):
        raise ValueError(f"Invalid run metadata: {directory / 'run.json'}")
    _component(metadata.get("chapter"))
    if not isinstance(metadata.get("started"), str):
        raise ValueError("Run metadata has no start time")
    return {**metadata, "run_dir": str(directory), "container_dir": f"/shared/demos/{run_id}"}


def job_name(run_id: str, step_id: str) -> str:
    name = f"demo-{_component(run_id)}-{_component(step_id)}"
    if len(name) > 128:
        raise ValueError("Combined run and step IDs exceed the 128-character job name limit")
    return name


def local_argv(run_id: str, operation: str, *args: str) -> list[str]:
    """Build a real, bounded local command; paths are relative to this run.

    Operations: release(path), copy(source,destination),
    csv-set(path,zero_based_row,column,value), pipeline-prepare(new_directory).
    All operations reject symlinks/traversal and are run with the same claims.
    """
    return [sys.executable, str(Path(__file__).resolve()), "local", _component(run_id), operation, *args]


def _relative(run: dict, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("Local file paths must be nonempty run-relative paths")
    directory = Path(run["run_dir"])
    path = _safe(directory, directory / value)
    relative = path.relative_to(directory)
    if not relative.parts or relative.parts[0] in {"actions", "run.json", "report.json"}:
        raise ValueError("Local actions cannot modify run metadata, claims or receipts")
    return path


def _container_path(run: dict, value: str) -> Path:
    container = Path(run["container_dir"])
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected an absolute path inside {container}: {value}")
    return _safe(Path(run["run_dir"]), Path(run["run_dir"]) / path.relative_to(container))


def _local_targets(run: dict, argv: list[str]) -> dict:
    prefix = local_argv(run["run_id"], "")[:-1]
    if argv[:len(prefix)] != prefix or len(argv) <= len(prefix):
        raise ValueError("local only permits commands built by local_argv")
    operation, *args = argv[len(prefix):]
    arity = {"release": 1, "copy": 2, "csv-set": 4, "pipeline-prepare": 1}
    if operation not in arity or len(args) != arity[operation]:
        raise ValueError("Invalid bounded local operation or arguments")
    paths = args[:2] if operation == "copy" else args[:1]
    resolved = [_relative(run, value) for value in paths]
    if operation == "csv-set" and (not args[1].isdigit() or not args[2]):
        raise ValueError("csv-set requires a nonnegative row and named column")
    if operation == "copy" and resolved[0] == resolved[1]:
        raise ValueError("Source and destination must differ")
    return {"operation": operation, "paths": [str(path) for path in resolved]}


def _options(command: list[str]) -> tuple[dict[str, str | bool], list[str]]:
    options: dict[str, str | bool] = {}
    index = 1
    flags = {"--parsable", "--exclusive", "--overlap", "--wait", "--hold"}
    while index < len(command) and command[index].startswith("-"):
        option = command[index]
        if not option.startswith("--") or option == "--":
            raise ValueError("Use explicit long Slurm options, not short aliases")
        if "=" in option:
            key, value = option.split("=", 1)
        elif option in flags:
            key, value = option, True
        else:
            if index + 1 >= len(command):
                raise ValueError(f"Missing option value: {option}")
            key, value = option, command[index + 1]
            index += 1
        if key in options:
            raise ValueError(f"Duplicate Slurm option: {key}")
        options[key] = value
        index += 1
        if key == "--wrap":
            break
    return options, command[index:]


def _validate_argv(run: dict, step_id: str, argv: list[str], effect: str, timeout: float) -> dict:
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or "\0" in x for x in argv):
        raise ValueError("argv must be a nonempty list of strings without NULs")
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    maximum = 15 if effect == "interactive" else 90 if effect in {"restart-controller", "restore-controller"} else 30
    if timeout > maximum:
        raise ValueError(f"{effect} timeout may not exceed {maximum} seconds")
    if effect == "local":
        return _local_targets(run, argv)
    if effect == "restart-controller":
        if argv != ["docker", "compose", "restart", "controller"]:
            raise ValueError("restart-controller may only restart this project's controller")
        return {"service": "controller"}
    if effect == "restore-controller":
        if argv != ["docker", "compose", "up", "-d", "--no-build", "controller"]:
            raise ValueError("restore-controller requires compose up -d --no-build controller")
        return {"service": "controller"}
    if effect in {"drain", "resume"}:
        expected = compose_argv("scontrol", "update", "NodeName=cpu02", f"State={'DRAIN' if effect == 'drain' else 'RESUME'}", user="root")
        if effect == "drain":
            expected.append(f"Reason=demo-{run['run_id']}")
        if argv != expected:
            raise ValueError(f"{effect} only permits the exact owned cpu02 maintenance command")
        return {"node": "cpu02", "reason": f"demo-{run['run_id']}"}
    prefix = compose_argv()
    if argv[:len(prefix)] != prefix:
        raise ValueError("Scheduler commands must use compose_argv with user lab and service controller")
    command = argv[len(prefix):]
    if effect == "cancel":
        if len(command) < 2 or command[0] != "scancel" or any(not _JOB_ID.fullmatch(x) for x in command[1:]):
            raise ValueError("cancel requires explicit numeric parent job IDs; selectors and flags are forbidden")
        if len(set(command[1:])) != len(command[1:]):
            raise ValueError("Duplicate cancellation IDs")
        return {"job_ids": command[1:]}
    expected_command = "sbatch" if effect == "submit" else "srun"
    if not command or command[0] != expected_command:
        raise ValueError(f"{effect} requires {expected_command}")
    options, workload = _options(command)
    expected_name = job_name(run["run_id"], step_id)
    if options.get("--job-name") != expected_name:
        raise ValueError(f"This step must use --job-name={expected_name}")
    _container_path(run, str(options.get("--chdir", "")))
    logs = []
    for option in ("--output", "--error"):
        if option in options:
            path = str(options[option])
            _container_path(run, path)
            if re.search(r"%(?![jAa])", path):
                raise ValueError("Output templates may only use %j, %A and %a")
            logs.append(path)
    if effect == "submit":
        if options.get("--parsable") is not True or "--wait" in options:
            raise ValueError("submit requires --parsable and forbids --wait")
        if not logs or "--output" not in options:
            raise ValueError("submit requires an explicit output path inside this run")
        if not workload and "--wrap" not in options:
            raise ValueError("submit requires a registered script or fixed --wrap workload")
        if "--wrap" in options and workload:
            raise ValueError("--wrap must be the final option; hidden overrides after its program are forbidden")
        if "--array" in options and any("%A" not in path or "%a" not in path for path in logs):
            raise ValueError("Array output/error templates must contain both %A and %a")
    else:
        permitted = {"--job-name", "--chdir", "--partition", "--nodes", "--ntasks", "--cpus-per-task", "--mem",
                     "--immediate", "--time", "--cpu-bind", "--nodelist", "--output", "--error"}
        if set(options) - permitted or workload != ["python3", _PROBE, "affinity"]:
            raise ValueError("interactive only permits the short CPU affinity probe, not arbitrary srun programs")
        required = {"--partition": "cpu", "--nodes": "1", "--ntasks": "1", "--mem": "128M", "--immediate": "5", "--cpu-bind": "threads"}
        if any(options.get(key) != value for key, value in required.items()):
            raise ValueError("interactive requires one CPU task, 128M, cpu partition, threads binding and --immediate=5")
        if options.get("--cpus-per-task") not in {"1", "4"} or options.get("--nodelist") not in {"cpu01", "cpu02"}:
            raise ValueError("interactive requires cpu01/cpu02 and 1 or 4 CPUs")
        if options.get("--time") not in {"00:00:15", "00:00:30", "00:01:00"}:
            raise ValueError("interactive requires a Slurm time limit of at most one minute")
    return {"job_name": expected_name, "logs": list(dict.fromkeys(logs)), "working_directory": str(options["--chdir"])}


def _unknown(claim: dict) -> dict:
    return {**claim, "status": "unknown", "returncode": None, "stdout": "", "stderr": "",
            "seconds": None, "job_id": None,
            "error": "Command result unconfirmed: claim exists without a receipt. Do not resubmit; reconcile the unique job name manually."}


def _records(run: dict) -> tuple[list[dict], list[dict], list[dict]]:
    directory = Path(run["run_dir"])
    actions = _safe(directory, directory / "actions")
    claims, receipts, errors = [], [], []
    if not actions.is_dir():
        return [], [], [{"path": str(actions), "error": "Missing actions directory"}]
    for path in sorted(actions.glob("*.claim")):
        try:
            _component(path.stem)
            claim = _json(path, directory)
            if claim.get("run_id") != run["run_id"] or claim.get("step_id") != path.stem or claim.get("parameters") != run["parameters"]:
                raise ValueError("Claim identity or frozen parameters do not match run")
            if claim.get("effect") not in EFFECTS or not isinstance(claim.get("argv"), list) or not claim["argv"]:
                raise ValueError("Invalid claim command or effect")
            if any(not isinstance(arg, str) or "\0" in arg for arg in claim["argv"]):
                raise ValueError("Invalid claim argv")
            targets = claim.get("targets")
            if not isinstance(targets, dict):
                raise ValueError("Invalid claim targets")
            if claim["effect"] in {"submit", "interactive"}:
                if targets.get("job_name") != job_name(run["run_id"], path.stem):
                    raise ValueError("Claim job name does not match its fixed run/step")
                _container_path(run, targets.get("working_directory", ""))
                if not isinstance(targets.get("logs"), list):
                    raise ValueError("Invalid claim output paths")
                for value in targets["logs"]:
                    _container_path(run, value)
            if claim["effect"] in {"drain", "resume"} and (
                targets.get("node") != "cpu02" or targets.get("reason") != f"demo-{run['run_id']}"
            ):
                raise ValueError("Invalid maintenance ownership in claim")
            claims.append(claim)
            receipt_path = path.with_suffix(".json")
            if receipt_path.exists() or receipt_path.is_symlink():
                receipt = _json(receipt_path, directory)
                for key in ("run_id", "step_id", "argv", "effect", "parameters", "targets"):
                    if receipt.get(key) != claim.get(key):
                        raise ValueError(f"Receipt differs from claim: {key}")
                if receipt.get("status") not in {"succeeded", "failed", "unknown"}:
                    raise ValueError("Invalid receipt status")
                identifier = receipt.get("job_id")
                if identifier is not None:
                    if claim["effect"] not in {"submit", "interactive"} or not isinstance(identifier, str) or not _JOB_ID.fullmatch(identifier):
                        raise ValueError("Invalid recorded job ID")
                    identity = receipt.get("identity")
                    if not isinstance(identity, dict) or not isinstance(identity.get("submit_times"), dict):
                        raise ValueError("Invalid recorded job identity")
                receipts.append(receipt)
            else:
                receipts.append(_unknown(claim))
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    for path in sorted(actions.glob("*.json")):
        if not path.with_suffix(".claim").exists():
            errors.append({"path": str(path), "error": "Receipt has no matching durable claim"})
    return claims, receipts, errors


def _fresh(*names: str) -> dict:
    queries = {"jobs": query_jobs, "nodes": query_nodes, "queue": query_queue}
    snapshot = {"observed_at": _now(), "sources": {}}
    failed = None
    for name in names:
        if failed:
            source = {"status": "error", "data": None, "stale": False,
                      "observed_at": _now(), "errors": [f"Skipped after {failed} query failed"], "warnings": []}
        else:
            source = queries[name]()
            if source.get("status") != "ok":
                failed = name
        snapshot["sources"][name] = source
    return snapshot


def _data(snapshot: dict, name: str) -> list[dict]:
    source = snapshot["sources"].get(name)
    if not source or source.get("status") != "ok" or source.get("stale") or not isinstance(source.get("data"), list):
        detail = (source or {}).get("errors", ["query unavailable"])
        raise ValueError(f"Fresh complete {name} query required: {detail}")
    return source["data"]


def _owned(receipts: list[dict]) -> dict[str, dict]:
    result = {}
    for receipt in receipts:
        identifier = receipt.get("job_id")
        if identifier is None:
            continue
        if receipt["effect"] not in {"submit", "interactive"} or not isinstance(identifier, str) or not _JOB_ID.fullmatch(identifier):
            raise ValueError("Invalid recorded job ID; manual reconciliation required")
        if identifier in result:
            raise ValueError(f"Job ID {identifier} occurs in multiple receipts; manual reconciliation required")
        result[identifier] = receipt
    return result


def _related(jobs: list[dict], identifier: str) -> list[dict]:
    return [job for job in jobs if job.get("job_id") == identifier or job.get("array_job_id") == identifier]


def _verify_identity(receipt: dict, jobs: list[dict], *, required: bool = True) -> list[dict]:
    identifier = receipt["job_id"]
    matches = _related(jobs, identifier)
    if required and not matches:
        raise ValueError(f"Job {identifier} has no retained identity record; do not infer completion or cancellation authority")
    identity = receipt.get("identity", {})
    expected_name = receipt["targets"].get("job_name")
    expected_directory = receipt["targets"].get("working_directory")
    seen = set()
    for job in matches:
        key = (job.get("job_id"), job.get("array_task_id"))
        if key in seen:
            raise ValueError(f"Ambiguous duplicate scheduler records for {identifier}")
        seen.add(key)
        if job.get("name") != expected_name or job.get("user_id") != 1000 or job.get("current_working_directory") != expected_directory:
            raise ValueError(f"Job {identifier} identity no longer matches saved name, UID 1000 and working directory; refusing ownership")
        saved_time = identity.get("submit_time")
        saved_records = identity.get("submit_times", {})
        if str(job.get("job_id")) in saved_records:
            saved_time = saved_records[str(job["job_id"])]
        if saved_time is not None and job.get("submit_time") != saved_time:
            raise ValueError(f"Job {identifier} SubmitTime changed; possible reused ID, refusing cancellation")
    return matches


def _gate(run: dict, receipts: list[dict], effect: str, targets: dict, snapshot: dict) -> None:
    owned = _owned(receipts)
    if effect == "local":
        return
    if effect == "restore-controller":
        restarts = [r for r in receipts if r["effect"] == "restart-controller"]
        if not restarts:
            raise ValueError("Restore is only permitted after this run attempted a controller restart")
        if all(r["status"] == "succeeded" for r in restarts):
            source = snapshot["sources"].get("jobs", {})
            if source.get("status") == "ok":
                raise ValueError("Controller query is healthy; restore is unnecessary")
        return
    if effect == "cancel":
        jobs = _data(snapshot, "jobs")
        for identifier in targets["job_ids"]:
            if identifier not in owned:
                raise ValueError(f"Job {identifier} is not authorized by a saved submission receipt")
            _verify_identity(owned[identifier], jobs)
        return
    nodes = _data(snapshot, "nodes")
    if effect == "resume":
        if not any(r["effect"] == "drain" and r["targets"].get("node") == targets["node"] for r in receipts):
            raise ValueError("This run never claimed a DRAIN on that node")
        matches = [node for node in nodes if node.get("name") == targets["node"]]
        if len(matches) != 1 or matches[0].get("reason") != targets["reason"]:
            raise ValueError("Current node Reason is not owned by this run; refusing RESUME")
        targets["original_state"] = matches[0].get("state")
        targets["original_reason"] = matches[0].get("reason")
        return
    jobs, queue = _data(snapshot, "jobs"), _data(snapshot, "queue")
    unknown = [r["step_id"] for r in receipts if r["status"] == "unknown" and r["effect"] in {"submit", "interactive", "drain", "restart-controller"}]
    if unknown:
        raise ValueError(f"Unconfirmed earlier effects require manual reconciliation before new work: {unknown}")
    for task in queue:
        identifier = task.get("parent_job_id") or task.get("job_id", "").split("_", 1)[0]
        if identifier not in owned:
            raise ValueError(f"Active queue contains external job/task {task.get('job_id')}; no new work or disruptive maintenance allowed")
        _verify_identity(owned[identifier], jobs)
    drained_here = {r["targets"].get("node") for r in receipts if r["effect"] == "drain"}
    if {node.get("name") for node in nodes} != {"cpu01", "cpu02", "gpu01"}:
        raise ValueError("Expected all three project compute nodes in the fresh query")
    for node in nodes:
        state = node.get("state", [])
        if not isinstance(state, list):
            raise ValueError("Invalid node state schema")
        bad = [flag for flag in state if any(word in flag for word in ("DOWN", "DRAIN", "FAIL", "UNKNOWN", "NO_RESPOND", "NOT_RESPONDING", "INVAL"))]
        own_drain = node["name"] in drained_here and node.get("reason") == f"demo-{run['run_id']}"
        if bad and not (own_drain and all("DRAIN" in flag for flag in bad)):
            raise ValueError(f"Node {node['name']} is unavailable or under external maintenance: {state}; {node.get('reason')}")
    if effect == "drain":
        node = next(node for node in nodes if node["name"] == targets["node"])
        if any("DRAIN" in flag for flag in node["state"]):
            raise ValueError("cpu02 is already DRAIN; this action cannot take over its maintenance")
        targets["original_state"] = node["state"]
        targets["original_reason"] = node.get("reason")


def _report(run: dict) -> dict:
    report = _json(Path(run["run_dir"]) / "report.json", Path(run["run_dir"]))
    if report.get("run_id") != run["run_id"]:
        raise ValueError("Report identity does not match run")
    for key in ("cases", "commands", "created_job_ids", "cleanup_errors"):
        if not isinstance(report.get(key), list):
            raise ValueError(f"Invalid report field: {key}")
    return report


def _save_report(run: dict, *, reset: bool = False, report: dict | None = None) -> dict:
    report = _report(run) if report is None else report
    _, receipts, errors = _records(run)
    if errors:
        raise ValueError(f"Cannot save over damaged action records: {errors}")
    report["created_job_ids"] = sorted(_owned(receipts), key=int)
    report["commands"] = receipts + [r for r in report["commands"] if r.get("kind") == "cleanup"]
    if reset:
        report.update(status="running", finished=None)
    if report["cleanup_errors"]:
        report.update(status="failed", finished=_now())
    _atomic_json(Path(run["run_dir"]) / "report.json", report, Path(run["run_dir"]))
    return report


def _interactive_job_id(stdout: str) -> str | None:
    identifiers = set()
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("job_id"), str) and _JOB_ID.fullmatch(record["job_id"]):
            identifiers.add(record["job_id"])
    return next(iter(identifiers)) if len(identifiers) == 1 else None


def _text(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else value or ""


def _invoke(argv: list[str], timeout: float) -> dict:
    started = time.monotonic()
    result = {"argv": argv, "started": _now(), "returncode": None, "stdout": "", "stderr": ""}
    try:
        process = run_command(argv, cwd=ROOT, timeout=timeout)
        result.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr,
                      status="succeeded" if process.returncode == 0 else "failed")
    except subprocess.TimeoutExpired as exc:
        result.update(status="unknown", stdout=_text(exc.stdout), stderr=_text(exc.stderr),
                      error="Command timed out; its external effect is unconfirmed. Do not resubmit.")
    except OSError as exc:
        result.update(status="failed", error=str(exc))
    result.update(seconds=round(time.monotonic() - started, 3), finished=_now())
    return result


def execute_once(run_id: str, step_id: str, argv: list[str], *, effect: str, timeout: float = 30) -> dict:
    """Execute one registered step at most once; blocked attempts consume no claim."""
    run = load_run(run_id)
    _component(step_id)
    if effect not in EFFECTS:
        raise ValueError(f"Unknown action effect: {effect}")
    try:
        with _action_lock():
            claims, receipts, errors = _records(run)
            if errors:
                return _blocked(f"Damaged action history needs manual repair: {errors}")
            previous = next((r for r in receipts if r["step_id"] == step_id), None)
            if previous is not None:
                if previous["argv"] != argv or previous["effect"] != effect:
                    return _blocked("This step was already consumed with different argv/effect. Create a new run.")
                return previous
            registration = _CHAPTERS.get(run["chapter"])
            step = registration[0].get(step_id) if registration else None
            if step is None:
                return _blocked("Step is not registered in this chapter's source code")
            try:
                if step.effect != effect or step.argv(load_run(run_id)) != argv:
                    raise ValueError("argv/effect differs from the fixed step built from frozen run parameters")
                targets = _validate_argv(run, step_id, argv, effect, timeout)
                _report(run)
                names = () if effect == "local" else ("jobs",) if effect in {"cancel", "restore-controller"} else ("nodes",) if effect == "resume" else ("jobs", "nodes", "queue")
                snapshot = _fresh(*names)
                _gate(run, receipts, effect, targets, snapshot)
                evidence = step.precondition(load_run(run_id), snapshot) if step.precondition else None
                if isinstance(evidence, str):
                    return _blocked(evidence)
                if evidence is not None and not isinstance(evidence, dict):
                    raise ValueError("Precondition must return None, a blocking reason, or an evidence dict")
                json.dumps(evidence, allow_nan=False)
            except Exception as exc:
                return _blocked(str(exc))
            claim = {"run_id": run_id, "step_id": step_id, "argv": list(argv), "effect": effect,
                     "parameters": run["parameters"], "targets": targets, "job_name": targets.get("job_name"),
                     "started": _now(), "timeout": timeout, "before": snapshot, "evidence": evidence}
            directory = Path(run["run_dir"])
            _claim(directory / "actions" / f"{step_id}.claim", claim, directory)
            outcome = _invoke(argv, timeout)
            receipt = {**claim, **outcome, "job_id": None}
            if effect in {"submit", "interactive"}:
                try:
                    identifier = parse_job_id(receipt["stdout"]) if effect == "submit" else _interactive_job_id(receipt["stdout"])
                except ValueError:
                    identifier = None
                if identifier is not None:
                    receipt["job_id"] = identifier
                    receipt["identity"] = {"job_id": identifier, "name": targets["job_name"], "user_id": 1000,
                                           "submit_time": None, "submit_times": {},
                                           "current_working_directory": targets["working_directory"]}
                elif receipt["status"] == "succeeded":
                    receipt.update(status="unknown", error="Command returned success without a unique job ID; reconcile its job name manually. No automatic retry.")
            receipt_path = directory / "actions" / f"{step_id}.json"
            _atomic_json(receipt_path, receipt, directory)
            _save_report(run, reset=True)
            if receipt.get("job_id") is not None:
                observed = query_jobs()
                receipt["identity_observation"] = observed
                if observed.get("status") == "ok":
                    try:
                        matches = _verify_identity(receipt, observed["data"])
                        times = {str(job["job_id"]): job["submit_time"] for job in matches if job.get("submit_time") is not None}
                        receipt["identity"]["submit_times"] = times
                        if times and len(set(times.values())) == 1:
                            receipt["identity"]["submit_time"] = next(iter(times.values()))
                    except (ValueError, KeyError) as exc:
                        receipt["identity_error"] = str(exc)
                _atomic_json(receipt_path, receipt, directory)
                _save_report(run)
            return receipt
    except _Busy as exc:
        return _blocked(str(exc))


def _log_paths(run: dict, receipts: list[dict], jobs: list[dict]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}
    for receipt in receipts:
        identifier = receipt.get("job_id")
        if not identifier:
            continue
        candidates = []
        recorded = receipt.get("identity_observation", {})
        saved_jobs = (recorded.get("data") or []) if recorded.get("status") == "ok" else []
        related = []
        for records in (saved_jobs, jobs):
            try:
                related.extend(_verify_identity(receipt, records, required=False))
            except ValueError:
                # Never authorize filenames using records for a reused ID.
                continue
        for template in receipt.get("targets", {}).get("logs", []):
            expanded = []
            for job in related:
                value = template.replace("%j", job["job_id"]).replace("%A", identifier)
                if job.get("array_task_id") is not None:
                    value = value.replace("%a", str(job["array_task_id"]))
                if "%" not in value:
                    expanded.append(_container_path(run, value))
            concrete = template.replace("%j", identifier).replace("%A", identifier)
            host_pattern = _container_path(run, concrete)
            if "%a" not in concrete:
                if not expanded:
                    expanded.append(host_pattern)
            else:
                pattern = re.escape(host_pattern.name).replace(re.escape("%a"), r"[0-9]+")
                for path in sorted(host_pattern.parent.glob(host_pattern.name.replace("%a", "*"))):
                    if re.fullmatch(pattern, path.name):
                        expanded.append(_safe(Path(run["run_dir"]), path))
                if not expanded:
                    # Preserve a missing-output indication before tasks materialize.
                    expanded.append(host_pattern)
            candidates.extend(str(path) for path in expanded)
        paths[identifier] = list(dict.fromkeys(candidates))
    return paths


def read_run(run_id: str) -> dict:
    """Merge saved evidence with fresh observations, without writing any file.

    Missing retained records are ``record-unavailable``, never COMPLETED. Unknown
    claims expose name-matched candidates for manual inspection, not ownership.
    """
    run = load_run(run_id)
    claims, receipts, errors = _records(run)
    try:
        report = _report(run)
    except (OSError, ValueError, TypeError) as exc:
        report = None
        errors.append({"path": str(Path(run["run_dir"]) / "report.json"), "error": str(exc)})
    source = query_jobs()
    jobs = source.get("data") if source.get("status") == "ok" else []
    jobs = jobs or []
    current, candidates = {}, {}
    for receipt in receipts:
        identifier = receipt.get("job_id")
        if identifier:
            try:
                matches = _verify_identity(receipt, jobs, required=False)
                current[identifier] = {"status": "observed" if matches else "record-unavailable" if source.get("status") == "ok" else "query-error", "records": matches}
            except ValueError as exc:
                current[identifier] = {"status": "identity-mismatch", "records": _related(jobs, identifier), "error": str(exc)}
        elif receipt["status"] == "unknown" and receipt["effect"] in {"submit", "interactive"}:
            candidates[receipt["step_id"]] = [job for job in jobs if job.get("name") == receipt.get("job_name")]
    outputs = {}
    for receipt in receipts:
        try:
            for identifier, paths in _log_paths(run, [receipt], jobs).items():
                outputs[identifier] = [_read_log(Path(run["run_dir"]), path) for path in paths]
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"step_id": receipt["step_id"], "error": f"Unsafe or unavailable log: {exc}"})
    return {**run, "report": report, "claims": claims, "receipts": receipts,
            "created_job_ids": sorted({r["job_id"] for r in receipts if r.get("job_id")}, key=int),
            "jobs": current, "job_query": source, "unknown_candidates": candidates,
            "outputs": outputs, "errors": errors, "observed_at": _now()}


def _authorized_log(run_id: str, path: str | Path) -> tuple[dict, Path]:
    run = load_run(run_id)
    _, receipts, errors = _records(run)
    if errors:
        raise ValueError(f"Cannot authorize logs from damaged receipts: {errors}")
    requested = Path(path)
    if str(requested).startswith("/shared/"):
        requested = _container_path(run, str(requested))
    elif not requested.is_absolute():
        requested = Path(run["run_dir"]) / requested
    requested = _safe(Path(run["run_dir"]), requested)
    known = _log_paths(run, receipts, [])
    for values in known.values():
        for value in values:
            candidate = _container_path(run, value) if value.startswith("/shared/") else Path(value)
            if candidate == requested:
                return run, requested
    raise ValueError("Only output paths recorded by this run's submission receipts may be read")


def read_log(run_id: str, path: str | Path) -> dict:
    """Preview only authorized job output, at most the final 64 KiB."""
    run, requested = _authorized_log(run_id, path)
    return _read_log(Path(run["run_dir"]), requested)


def download_log(run_id: str, path: str | Path) -> bytes:
    """Return complete authorized output bytes for an explicit UI download."""
    run, requested = _authorized_log(run_id, path)
    return _download_log(Path(run["run_dir"]), requested)


def verify_run(run_id: str) -> dict:
    """Explicitly run the registered evidence verifier and persist its case results."""
    run = load_run(run_id)
    registration = _CHAPTERS.get(run["chapter"])
    verifier = registration[1] if registration else None
    if verifier is None:
        return _blocked("No evidence verifier is registered for this chapter")
    try:
        with _action_lock():
            view = read_run(run_id)
            if view["errors"]:
                return _blocked(f"Repair unreadable evidence before verification: {view['errors']}")
            try:
                cases = verifier(view)
                if not isinstance(cases, list) or not cases:
                    raise ValueError("Verifier must return concrete, nonempty case evidence")
                names = set()
                for case in cases:
                    if not isinstance(case, dict) or not isinstance(case.get("name"), str) or not case["name"] or case["name"] in names:
                        raise ValueError("Verification case names must be nonempty and unique")
                    names.add(case["name"])
                    if case.get("status") not in {"passed", "failed", "running"} or not case.get("evidence"):
                        raise ValueError("Every case needs passed/failed/running and concrete evidence; missing work cannot pass")
                json.dumps(cases, allow_nan=False)
            except Exception as exc:
                cases = [{"name": "verification", "status": "failed", "evidence": {"error": str(exc)}}]
            if not view["receipts"]:
                cases.append({"name": "no-actions", "status": "running", "evidence": {"reason": "No experiment steps have executed"}})
            if any(r["status"] == "unknown" for r in view["receipts"]):
                cases.append({"name": "unconfirmed-actions", "status": "running", "evidence": {"steps": [r["step_id"] for r in view["receipts"] if r["status"] == "unknown"]}})
            active = [identifier for identifier, observation in view["jobs"].items()
                      if observation["status"] == "observed"
                      and any(not (set(job["job_state"]) & TERMINAL) for job in observation["records"])]
            if active:
                cases.append({"name": "unfinished-jobs", "status": "running", "evidence": {"job_ids": active}})
            report = _report(run)
            status = "failed" if any(c["status"] == "failed" for c in cases) else "running" if any(c["status"] == "running" for c in cases) else "passed"
            report.update(cases=cases, finished=None if status == "running" else _now(), status=status)
            report["verification"] = {"observed_at": view["observed_at"], "jobs": view["jobs"], "job_query": view["job_query"]}
            return _save_report(run, report=report)
    except _Busy as exc:
        return _blocked(str(exc))


def cleanup_run(run_id: str) -> dict:
    """Retryable explicit recovery of exact owned IDs/Reasons; preserve all evidence.

    Never adopts jobs discovered by name. Controller restoration requires its own
    registered restore step rather than an implicit restart from this function.
    External queue entries do not prevent recovery of this run's resources.
    """
    run = load_run(run_id)
    try:
        with _action_lock():
            _, receipts, damaged = _records(run)
            if damaged:
                return _blocked(f"Cannot clean up damaged ownership records: {damaged}")
            report = _report(run)
            errors, commands = [], []
            owned = _owned(receipts)
            drains = {r["targets"]["node"]: r for r in receipts if r["effect"] == "drain"}
            for receipt in receipts:
                if receipt["status"] == "unknown" and receipt["effect"] in {"submit", "interactive"} and not receipt.get("job_id"):
                    errors.append(f"Unconfirmed step {receipt['step_id']}: manually reconcile job name {receipt.get('job_name')}; no candidate was adopted or cancelled")
            if not owned and any(r["effect"] == "restart-controller" for r in receipts):
                try:
                    _data(_fresh("jobs"), "jobs")
                except ValueError as exc:
                    errors.append(str(exc) + "; explicitly restore this run's controller before cleanup")
            if owned:
                snapshot = _fresh("jobs", "queue")
                try:
                    jobs, queue = _data(snapshot, "jobs"), _data(snapshot, "queue")
                except ValueError as exc:
                    errors.append(str(exc) + "; explicitly restore the controller before cleanup if restart failed")
                else:
                    active = {task.get("parent_job_id") or task.get("job_id", "").split("_", 1)[0] for task in queue}
                    for identifier, receipt in owned.items():
                        try:
                            matches = _verify_identity(receipt, jobs, required=identifier in active)
                            if not matches:
                                # A complete queue proves no active task here, not historical success.
                                continue
                            if identifier not in active and all(set(job.get("job_state", [])) & TERMINAL for job in matches):
                                continue
                            # Refresh identity immediately before each destructive command.
                            refreshed = _data(_fresh("jobs"), "jobs")
                            _verify_identity(receipt, refreshed)
                            command = {**_invoke(compose_argv("scancel", identifier), 30), "kind": "cleanup", "effect": "cancel", "job_id": identifier}
                            commands.append(command)
                            if command["status"] != "succeeded":
                                errors.append(f"Cancellation of {identifier}: {command.get('error') or command['stderr'] or command['status']}")
                        except (ValueError, OSError) as exc:
                            errors.append(str(exc))
            for node_name, receipt in drains.items():
                try:
                    nodes = _data(_fresh("nodes"), "nodes")
                    matches = [node for node in nodes if node.get("name") == node_name]
                    if len(matches) != 1:
                        raise ValueError(f"Cannot uniquely query node {node_name}")
                    node = matches[0]
                    if node.get("reason") != receipt["targets"]["reason"]:
                        resumed = any(r["effect"] == "resume" and r["status"] == "succeeded"
                                      and r["targets"].get("node") == node_name for r in receipts)
                        resumed = resumed or any(r.get("kind") == "cleanup" and r.get("effect") == "resume"
                                                 and r.get("node") == node_name and r.get("status") == "succeeded"
                                                 for r in report["commands"])
                        untouched = receipt["status"] == "failed" and node.get("reason") == receipt["targets"].get("original_reason")
                        if any("DRAIN" in flag for flag in node.get("state", [])) or not (resumed or untouched):
                            raise ValueError(f"Node {node_name} Reason changed; preserving external state: {node.get('reason')}")
                        continue
                    if not any("DRAIN" in flag for flag in node.get("state", [])):
                        continue
                    command = {**_invoke(compose_argv("scontrol", "update", f"NodeName={node_name}", "State=RESUME", user="root"), 30), "kind": "cleanup", "effect": "resume", "node": node_name, "reason": node["reason"]}
                    commands.append(command)
                    if command["status"] != "succeeded":
                        errors.append(f"Resume {node_name}: {command.get('error') or command['stderr'] or command['status']}")
                except (ValueError, OSError) as exc:
                    errors.append(str(exc))
            report["commands"].extend(commands)
            report.setdefault("cleanup_attempts", []).append({"observed_at": _now(), "commands": commands, "errors": errors})
            # Keep prior cleanup errors as evidence and do not silently restore a passed flag.
            report["cleanup_errors"].extend(errors)
            _save_report(run, report=report)
            return {"run_id": run_id, "status": "failed" if errors else "succeeded", "commands": commands,
                    "cleanup_errors": errors, "report_status": report["status"]}
    except _Busy as exc:
        return _blocked(str(exc))


def _local_main(argv: list[str]) -> int:
    """Private bounded local command entry point; no scheduler operations."""
    if len(argv) < 3 or argv[0] != "local":
        raise ValueError("Only the bounded local command entry point is supported")
    run = load_run(argv[1])
    operation, args = argv[2], argv[3:]
    _local_targets(run, local_argv(run["run_id"], operation, *args))
    paths = [_relative(run, value) for value in (args[:2] if operation == "copy" else args[:1])]
    if operation == "release":
        fd = os.open(paths[0], os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    elif operation == "pipeline-prepare":
        script = ROOT / "examples" / "pipeline.py"
        if not script.is_file():
            raise FileNotFoundError("Public examples/pipeline.py is not installed")
        process = run_command([sys.executable, str(script), "prepare", "--run-dir", str(paths[0])], cwd=ROOT, timeout=25)
        print(process.stdout, end="")
        print(process.stderr, end="", file=sys.stderr)
        return process.returncode
    else:
        if operation == "copy":
            content = paths[0].read_bytes()
            destination = paths[1]
        else:
            with paths[0].open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            row = int(args[1])
            if fields is None or args[2] not in fields or row >= len(rows):
                raise ValueError("CSV row/column does not exist")
            rows[row][args[2]] = args[3]
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            content = stream.getvalue().encode("utf-8")
            destination = paths[0]
        fd, temporary = tempfile.mkstemp(prefix=".local-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print(json.dumps({"operation": operation, "paths": [str(path) for path in paths]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_local_main(sys.argv[1:]))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
