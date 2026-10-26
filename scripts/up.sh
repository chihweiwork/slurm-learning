#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init.py
docker compose config --quiet
services=$(docker compose config --services)
accounting=no
if grep -qx slurmdbd <<<"$services"; then accounting=yes; fi
docker compose build controller
docker compose run --rm --no-deps init
if [[ $accounting == yes ]]; then
    docker compose up -d --no-build --wait --wait-timeout 180 mariadb slurmdbd
fi
docker compose up -d --no-build --wait --wait-timeout 180 controller cpu01 cpu02 gpu01
if [[ $accounting == yes ]]; then
    bash scripts/accounting-init.sh
fi
python3 scripts/prepare-job-image.py
docker compose exec -T controller sinfo -Nel
