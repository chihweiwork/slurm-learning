#!/bin/bash
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128M
#SBATCH --time=00:02:00
#SBATCH --chdir=/shared
#SBATCH --output=/shared/cpu-%j.out
set -euo pipefail
srun --cpu-bind=threads python3 /opt/lab/examples/cpu_probe.py affinity
