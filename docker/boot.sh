#!/bin/bash
set -euo pipefail
role=${1:?init, controller, compute or slurmdbd required}
if [[ $role == init ]]; then
    python3 -c 'import os,secrets; p="/etc/munge/munge.key"; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400) if not os.path.exists(p) else None; fd is None or os.write(fd,secrets.token_bytes(1024)); fd is None or os.close(fd)'
    [[ $(stat -c %s /etc/munge/munge.key) == 1024 ]]
    chown -R munge:munge /etc/munge
    chmod 0700 /etc/munge
    chmod 0400 /etc/munge/munge.key
    # Present only when compose.accounting.yaml mounts the accounting-secret volume.
    if [[ -d /etc/slurm-accounting ]]; then
        python3 -c 'import os,secrets,sys
for p in sys.argv[1:]:
    if not os.path.exists(p):
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400); os.write(fd,secrets.token_hex(32).encode()); os.close(fd)' \
            /etc/slurm-accounting/db-password /etc/slurm-accounting/db-root-password
        chown -R root:root /etc/slurm-accounting
        chmod 0700 /etc/slurm-accounting
        chmod 0400 /etc/slurm-accounting/db-password /etc/slurm-accounting/db-root-password
    fi
    exit 0
fi
[[ -s /etc/munge/munge.key ]] || { echo 'Run the init service first' >&2; exit 1; }
install -d -m 0755 -o munge -g munge /run/munge /var/log/munge /var/lib/munge
install -d -m 0755 -o slurm -g slurm /var/log/slurm /var/lib/slurm/ctld
install -d -m 0755 /var/lib/slurm/slurmd
if [[ $role == controller ]]; then
    runuser -u munge -- /usr/sbin/munged --key-file=/etc/munge/munge.key
    exec /usr/local/sbin/slurmctld -D
elif [[ $role == slurmdbd ]]; then
    password=$(cat /run/secrets/accounting/db-password 2>/dev/null) || password=
    [[ $password =~ ^[0-9a-f]{64}$ ]] || { echo 'Run init with compose.accounting.yaml first' >&2; exit 1; }
    install -m 0600 -o slurm -g slurm /dev/null /etc/slurm/slurmdbd.conf
    { cat /etc/slurm/slurmdbd.conf.in; printf 'StoragePass=%s\n' "$password"; } > /etc/slurm/slurmdbd.conf
    unset password
    runuser -u munge -- /usr/sbin/munged --key-file=/etc/munge/munge.key
    exec /usr/local/sbin/slurmdbd -D
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
