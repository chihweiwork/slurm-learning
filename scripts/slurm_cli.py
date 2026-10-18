"""Shared argv-only transport for the CLI acceptance suite and notebooks."""
from pathlib import Path
import subprocess


def run_command(argv: list[str], *, cwd: Path, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, shell=False, text=True,
                          capture_output=True, timeout=timeout)


def compose_argv(*args: str, user: str = "lab", service: str = "controller") -> list[str]:
    return ["docker", "compose", "exec", "-T", "-u", user, service, *args]


def parse_job_id(stdout: str) -> str:
    job_id = stdout.strip().split(";", 1)[0]
    if not job_id.isascii() or not job_id.isdigit():
        raise ValueError(f"Invalid sbatch job ID: {stdout!r}")
    return job_id
