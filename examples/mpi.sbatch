#!/bin/bash
#SBATCH --partition=cpu
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=256M
#SBATCH --time=00:03:00
#SBATCH --chdir=/shared
#SBATCH --output=/shared/mpi-%j.out
set -euo pipefail
binary="/shared/mpi-sum-${SLURM_JOB_ID}"
trap 'rm -f "$binary"' EXIT
mpicc -O2 -Wall -Wextra /opt/lab/examples/mpi_sum.c -o "$binary"
srun --mpi=pmix --cpu-bind=threads "$binary"
