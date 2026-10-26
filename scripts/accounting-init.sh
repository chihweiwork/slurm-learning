#!/bin/bash
# Idempotent accounting bootstrap (compose.accounting.yaml only): slurmctld
# registers cluster compose-lab itself; ensure account "lab" and user lab's
# default association. Never deletes or modifies existing associations.
set -euo pipefail
cd "$(dirname "$0")/.."
sacctmgr() { docker compose exec -T controller sacctmgr "$@"; }
for attempt in $(seq 60); do
    if [[ $(sacctmgr -nP show cluster format=cluster 2>/dev/null || true) == compose-lab ]]; then break; fi
    if (( attempt == 60 )); then echo 'Cluster compose-lab not registered in slurmdbd after 60s' >&2; exit 1; fi
    sleep 1
done
if [[ -z $(sacctmgr -nP show account lab format=account) ]]; then
    sacctmgr -i add account lab Description='Slurm lab users' Organization=lab
fi
if [[ -z $(sacctmgr -nP show association where user=lab account=lab format=user) ]]; then
    sacctmgr -i add user lab Account=lab DefaultAccount=lab
fi
sacctmgr -nP show association where user=lab format=cluster,account,user
