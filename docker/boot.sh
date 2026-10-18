#!/bin/bash
set -euo pipefail
role=${1:?init, controller or compute required}
if [[ $role == init ]]; then
    python3 -c 'import os,secrets; p="/etc/munge/munge.key"; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400) if not os.path.exists(p) else None; fd is None or os.write(fd,secrets.token_bytes(1024)); fd is None or os.close(fd)'
    [[ $(stat -c %s /etc/munge/munge.key) == 1024 ]]
    chown -R munge:munge /etc/munge
    chmod 0700 /etc/munge
    chmod 0400 /etc/munge/munge.key
    exit 0
fi
[[ -s /etc/munge/munge.key ]] || { echo 'Run the init service first' >&2; exit 1; }
install -d -m 0755 -o munge -g munge /run/munge /var/log/munge /var/lib/munge
install -d -m 0755 -o slurm -g slurm /var/log/slurm /var/lib/slurm/ctld
install -d -m 0755 /var/lib/slurm/slurmd
if [[ $role == controller ]]; then
    runuser -u munge -- /usr/sbin/munged --key-file=/etc/munge/munge.key
    exec /usr/local/sbin/slurmctld -D
elif [[ $role == compute ]]; then
    # Docker created a private cgroup namespace rooted at this container's scope.
    # Never bind-mount the host hierarchy here: this remount affects only our mount.
    [[ $(cat /proc/1/cgroup) == '0::/' ]] || { echo 'Private cgroup namespace required' >&2; exit 1; }
    mount -o remount,rw /sys/fs/cgroup
    exec /sbin/init
else
    echo "Unknown role: $role" >&2
    exit 2
fi
