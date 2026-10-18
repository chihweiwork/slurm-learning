#!/bin/bash
# Run as lab on controller: bash /opt/lab/examples/dependency.sh
set -euo pipefail
first=$(sbatch --parsable /opt/lab/examples/cpu.sbatch)
first=${first%%;*}
second=$(sbatch --parsable --dependency="afterok:${first}" /opt/lab/examples/cpu.sbatch)
printf 'prerequisite=%s dependent=%s\n' "$first" "$second"
