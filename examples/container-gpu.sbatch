#!/usr/bin/env bash
#SBATCH --job-name=container-gpu
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --gres=gpu:1
#SBATCH --mem=512M
#SBATCH --time=00:02:00
#SBATCH --chdir=/shared
#SBATCH --output=/shared/container-gpu-%j.out
#SBATCH --error=/shared/container-gpu-%j.err
set -euo pipefail

# The Python program is baked into an independently built Docker/OCI image.
# No source-code bind mount, Docker daemon, or root remapping is needed.
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=compute,utility
srun --container-image=/shared/images/gpu-job.sqsh \
    --container-mounts=/shared:/shared \
    --container-workdir=/shared \
    --no-container-mount-home --no-container-remap-root \
    /usr/local/bin/python3 /opt/gpu-job/gpu_compute.py
