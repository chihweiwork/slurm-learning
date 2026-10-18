"""Real public CSV workloads for the standalone, standard-library smoke CLI."""
import csv
import json


PIPELINE = "/opt/lab/examples/pipeline.py"
WORKER = "/opt/lab/examples/pipeline-worker.sbatch"
AGGREGATE = "/opt/lab/examples/pipeline-aggregate.sbatch"


def _prepare(s, name):
    directory = f"{s.run_dir}/{name}"
    result = s.compose("python3", PIPELINE, "prepare", "--run-dir", directory)
    return s.run_host / name, directory, result.stdout


def _ended(s, job_id, expected="COMPLETED"):
    state = s.finish(job_id, expected=expected)
    if expected == "FAILED":
        s.require(state.get("ExitCode") not in (None, "0:0"),
                  f"Failed pipeline job lacks nonzero exit evidence: {state}")
    return {"job_id": job_id, "state": state, "stdout": s.read_output(job_id)}


def _partial(s, directory, index):
    value = json.loads((directory / "partials" / f"{index}.json").read_text())
    # Sum of 2*i over this shard, from the difference of triangular numbers.
    lower, upper = index * 1000, (index + 1) * 1000
    expected = {"index": index, "row_count": 1000,
                "value_sum": upper * (upper + 1) - lower * (lower + 1)}
    s.require(isinstance(value, dict) and value == expected
              and all(type(item) is int for item in value.values()),
              f"Incorrect shard {index} result: {value!r}; expected {expected}")
    return value


def _results(s, directory):
    partials = [_partial(s, directory, index) for index in range(4)]
    summary = json.loads((directory / "summary.json").read_text())
    expected = {"shards": 4, "row_count": 4000, "value_sum": 4000 * 4001}
    s.require(isinstance(summary, dict) and summary == expected
              and all(type(item) is int for item in summary.values()),
              f"Incorrect pipeline summary: {summary!r}; expected {expected}")
    return {"partials": partials, "summary": summary}


def csv_pipeline_success(s):
    """Run four public array workers and their afterok aggregate."""
    host, directory, prepared = _prepare(s, "pipeline-success")
    parent = s.submit_script("csv-success-workers", WORKER, (directory,),
                             ("--array=0-3%2",))
    aggregate = s.submit_script("csv-success-aggregate", AGGREGATE, (directory,),
                                (f"--dependency=afterok:{parent}",))
    tasks = [_ended(s, f"{parent}_{index}") for index in range(4)]
    aggregate_result = _ended(s, aggregate)
    return {"directory": directory, "prepare_stdout": prepared, "array_parent": parent,
            "tasks": tasks, "aggregate": aggregate_result, **_results(s, host)}


def csv_pipeline_failure_recovery(s):
    """Observe rejected input/dependencies, then rerun only the repaired shard."""
    host, directory, prepared = _prepare(s, "pipeline-failure-recovery")
    shard = host / "input" / "shard-2.csv"
    backup = host / "input" / "shard-2.csv.backup"
    backup.write_bytes(shard.read_bytes())
    with shard.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    rows[1][1] = "not-an-integer"
    with shard.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)

    parent = s.submit_script("csv-failure-workers", WORKER, (directory,),
                             ("--array=0-3%2",))
    dependent = s.submit_script("csv-failure-dependent", AGGREGATE, (directory,),
                                (f"--dependency=afterok:{parent}", "--kill-on-invalid-dep=no"))
    tasks = [_ended(s, f"{parent}_{index}", "FAILED" if index == 2 else "COMPLETED")
             for index in range(4)]
    s.require(not (host / "partials" / "2.json").exists(),
              "Failed shard published a success partial")
    prior_partials = [_partial(s, host, index) for index in (0, 1, 3)]
    preserved = {index: (host / "partials" / f"{index}.json").read_bytes()
                 for index in (0, 1, 3)}
    pending = s.pending_for(dependent)
    s.require(pending and all(record.get("Reason") in {"Dependency", "DependencyNeverSatisfied"}
                              for record in pending),
              f"Failed array did not block its aggregate on dependency: {pending}")
    s.require(not (host / "summary.json").exists(), "Blocked aggregate published a summary")
    blocked_stdout = s.read_output(dependent)
    s.require(not blocked_stdout, f"Blocked aggregate unexpectedly ran: {blocked_stdout}")
    s.require("Shard 2 row 1: expected two integer fields" in tasks[2]["stdout"],
              f"Shard 2 failed for an unexpected reason: {tasks[2]}")

    missing = s.submit_script("csv-missing-aggregate", AGGREGATE, (directory,))
    missing_result = _ended(s, missing, "FAILED")
    s.require("partials/2.json" in missing_result["stdout"],
              f"Aggregate did not report the missing shard: {missing_result}")
    s.require(not (host / "summary.json").exists(), "Missing-shard aggregate published a summary")
    s.require(not (host / "partials" / "2.json").exists(), "Missing-shard aggregate created shard 2")

    s.require(dependent in s.jobs, f"Refusing to cancel unowned dependent {dependent}")
    s.cancel(dependent)
    cancelled = _ended(s, dependent, "CANCELLED")
    shard.write_bytes(backup.read_bytes())
    repair = s.submit_script("csv-repair-worker", WORKER, (directory,), ("--array=2",))
    aggregate = s.submit_script("csv-repaired-aggregate", AGGREGATE, (directory,),
                                (f"--dependency=afterok:{repair}",))
    repaired_task = _ended(s, f"{repair}_2")
    aggregate_result = _ended(s, aggregate)
    results = _results(s, host)
    unchanged = {}
    for index, before in preserved.items():
        after = (host / "partials" / f"{index}.json").read_bytes()
        s.require(after == before, f"Repair changed previously successful partial {index}")
        unchanged[str(index)] = {"before": before.decode("utf-8"),
                                 "after": after.decode("utf-8"), "unchanged": True}
    return {"directory": directory, "prepare_stdout": prepared, "array_parent": parent,
            "tasks": tasks, "partials_before_repair": prior_partials,
            "failed_partial_absent": True, "summary_before_repair_absent": True,
            "dependent": {"job_id": dependent, "pending": pending, "stdout": blocked_stdout,
                          "cancelled": cancelled},
            "missing_aggregate": missing_result, "repair_array_parent": repair,
            "repair_task": repaired_task, "aggregate": aggregate_result,
            "preserved_partial_bytes": unchanged, **results}
