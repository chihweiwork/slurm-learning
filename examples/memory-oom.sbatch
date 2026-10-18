#!/bin/bash
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128M
#SBATCH --time=00:02:00
#SBATCH --chdir=/shared
#SBATCH --output=/shared/memory-oom-%j.out
# This intentionally triggers a job cgroup OOM; srun propagates a nonzero exit.
# The probe touches at most 256 MiB, even if job isolation is misconfigured.
set -euo pipefail
srun --cpu-bind=threads python3 /opt/lab/examples/cpu_probe.py memory
