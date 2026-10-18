FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

LABEL org.opencontainers.image.title="slurm-lab-gpu-job" \
      org.opencontainers.image.description="Independent Python CUDA Driver API numerical job; no Slurm daemon or CUDA toolkit"

# The driver libraries/devices come from Enroot's official NVIDIA hook, not
# from the image. Keep this filesystem distinct from the Ubuntu Slurm nodes.
RUN groupadd --gid 1000 lab \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash lab \
    && mkdir -p /opt/gpu-job /shared \
    && printf '%s\n' '{"name":"slurm-lab-gpu-job","base":"python:3.12.15-slim-bookworm","base_digest":"sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258","runtime":"CUDA Driver API + embedded PTX"}' > /etc/slurm-lab-job-image.json
COPY examples/gpu_compute.py /opt/gpu-job/gpu_compute.py
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
USER 1000:1000
WORKDIR /shared
CMD ["/usr/local/bin/python3", "/opt/gpu-job/gpu_compute.py"]
