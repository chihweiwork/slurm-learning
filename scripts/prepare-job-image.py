#!/usr/bin/env python3
"""Build a real Docker image and export its rootfs for Slurm/Pyxis, without a node Docker socket."""
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'slurm-playground/gpu-job:1'

def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)

run(['docker', 'build', '-f', 'docker/job.Dockerfile', '-t', IMAGE, '.'])
image_id = run(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], capture_output=True).stdout.strip()
name = 'slurm-playground-export-' + uuid.uuid4().hex[:12]
archive = ROOT / 'shared/images/gpu-job.rootfs.tar'
archive.parent.mkdir(parents=True, exist_ok=True)
created = False
try:
    run(['docker', 'create', '--name', name, '--network', 'none', IMAGE])
    created = True
    run(['docker', 'export', '--output', str(archive), name])
    run(['docker', 'compose', 'exec', '-T', 'controller', 'bash', '-ec', '''
        work=$(mktemp -d)
        trap 'rm -rf "$work" /shared/images/gpu-job.sqsh.tmp' EXIT
        tar --numeric-owner -xf /shared/images/gpu-job.rootfs.tar -C "$work"
        mksquashfs "$work" /shared/images/gpu-job.sqsh.tmp -noappend -all-root -comp zstd -processors 2 -no-progress
        chmod 0644 /shared/images/gpu-job.sqsh.tmp
        mv /shared/images/gpu-job.sqsh.tmp /shared/images/gpu-job.sqsh
    '''])
finally:
    if created:
        run(['docker', 'rm', name])
    archive.unlink(missing_ok=True)
manifest = {'docker_image': IMAGE, 'image_id': image_id, 'slurm_image': '/shared/images/gpu-job.sqsh',
            'conversion': 'docker export rootfs -> squashfs; ENV/CMD supplied explicitly by sbatch'}
(ROOT / 'shared/images/gpu-job.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
