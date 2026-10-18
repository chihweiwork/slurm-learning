#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init.py
docker compose config --quiet
docker compose build controller
docker compose run --rm --no-deps init
docker compose up -d --no-build --wait --wait-timeout 180 controller cpu01 cpu02 gpu01
python3 scripts/prepare-job-image.py
docker compose exec -T controller sinfo -Nel
