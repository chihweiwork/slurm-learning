#!/bin/bash
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128M
#SBATCH --time=00:02:00
set -euo pipefail
if [ "$#" -ne 1 ]; then
    echo 'usage: pipeline-aggregate.sbatch CONTAINER_RUN_DIR' >&2
    exit 2
fi
srun --cpu-bind=threads python3 /opt/lab/examples/pipeline.py aggregate --run-dir "$1"
