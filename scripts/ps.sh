#!/bin/bash
# `docker compose ps` with the default columns and IMAGE capped at 30 chars.
# truncate is a no-op on the header row, so the IMAGE title survives.
set -euo pipefail
cd "$(dirname "$0")/.."
fit='table {{.Name}}\t{{truncate .Image 30}}\t{{.Command}}\t{{.Service}}\t{{.RunningFor}}\t{{.Status}}\t{{.Ports}}'
exec docker compose ps --format "$fit" "$@"
