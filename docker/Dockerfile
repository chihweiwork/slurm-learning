FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential pkg-config python3 munge libmunge-dev \
    systemd systemd-sysv dbus libdbus-1-dev libhwloc-dev hwloc libpam0g-dev \
    libssl-dev libjson-c-dev libhttp-parser-dev libyaml-dev libbpf-dev \
    libpmix-dev openmpi-bin libopenmpi-dev libnuma-dev procps iproute2 \
    autoconf automake libtool \
    && rm -f /etc/munge/munge.key && rm -rf /var/lib/apt/lists/*
ARG SLURM_COMMIT=ad46cad8e0969e8e5945b88f0a21f6bed0f9a3bf
ARG SLURM_SHA256=88d22fc5c88e9d61a2c9855755cd66fc37bb6c82360aec250b19358a935222ba
RUN curl -fsSL "https://codeload.github.com/SchedMD/slurm/tar.gz/${SLURM_COMMIT}" -o /tmp/slurm.tar.gz \
    && echo "${SLURM_SHA256}  /tmp/slurm.tar.gz" | sha256sum -c - \
    && mkdir /tmp/slurm-src && tar -xzf /tmp/slurm.tar.gz -C /tmp/slurm-src --strip-components=1 \
    && cd /tmp/slurm-src \
    && ./configure --prefix=/usr/local --sysconfdir=/etc/slurm --with-pmix=/usr/lib/x86_64-linux-gnu/pmix2 --with-hwloc=/usr --with-munge=/usr \
    && make -j4 && make install && ldconfig \
    && rm -rf /tmp/slurm-src /tmp/slurm.tar.gz
COPY docker/install-job-runtime.sh /tmp/install-job-runtime.sh
COPY docker/enroot-nested-ldconfig.patch /tmp/enroot-nested-ldconfig.patch
RUN bash /tmp/install-job-runtime.sh && rm /tmp/install-job-runtime.sh /tmp/enroot-nested-ldconfig.patch
COPY config/enroot.conf /etc/enroot/enroot.conf
RUN if getent passwd ubuntu; then userdel -r ubuntu; fi \
    && groupadd -g 1000 lab && useradd -m -u 1000 -g 1000 -s /bin/bash lab \
    && groupadd -g 64030 slurm && useradd -r -u 64030 -g slurm -d /var/lib/slurm -s /usr/sbin/nologin slurm \
    && install -d -m 0755 /etc/slurm /var/lib/slurm /var/log/slurm \
    && systemctl mask getty.target console-getty.service systemd-udevd.service systemd-logind.service \
    && rm -f /etc/machine-id && touch /etc/machine-id
COPY docker/slurmd.service /etc/systemd/system/slurmd.service
COPY docker/boot.sh /usr/local/sbin/lab-boot
RUN chmod 0755 /usr/local/sbin/lab-boot \
    && systemctl enable munge.service slurmd.service \
    && dpkg-query -W > /usr/local/share/node-packages.txt
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENTRYPOINT ["/usr/local/sbin/lab-boot"]
