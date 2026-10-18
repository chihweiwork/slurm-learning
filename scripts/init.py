#!/usr/bin/env python3
"""Create project-owned shared directories; MUNGE stays in a private Docker volume."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name in ('images', 'results', 'bin'):
    (ROOT / 'shared' / name).mkdir(parents=True, exist_ok=True)
if os.getuid() != 1000:
    raise SystemExit('This workstation configuration expects host UID 1000; adjust lab UID and shared ownership before starting')
print('Shared directories ready; run the Compose init service to initialize MUNGE.')
