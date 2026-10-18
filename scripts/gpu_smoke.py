#!/usr/bin/env python3
"""Prove independent OCI-image GPU jobs execute and remain under Slurm control."""
import json
import shlex
import time

from slurm_cli import compose_argv


IMAGE = '/shared/images/gpu-job.sqsh'
GPU_PROGRAM = '/opt/gpu-job/gpu_compute.py'
CONTAINER = ('srun --container-image=' + IMAGE +
             ' --container-mounts=/shared:/shared --container-workdir=/shared'
             ' --no-container-mount-home --no-container-remap-root')
GPU_OPTIONS = ('--partition=gpu', '--gres=gpu:1', '--cpus-per-task=1', '--mem=512M')
ENV = 'export NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility; '


def direct_command():
    """CUDA workload on the allocation, without a nested job image."""
    return 'srun python3 /opt/lab/examples/gpu_compute.py'


def container_command():
    return ENV + CONTAINER + ' /usr/local/bin/python3 ' + GPU_PROGRAM


def denied_command(container):
    program = '''import errno,json,os
try:
    fd=os.open('/dev/nvidia0',os.O_RDWR)
except OSError as e:
    assert e.errno in (errno.EPERM,errno.EACCES), repr(e)
    print(json.dumps({'device_denied':True,'errno':e.errno,'uid':os.getuid()}))
else:
    os.close(fd)
    raise SystemExit('GPU device accessible without Slurm GRES')
'''
    if container:
        # Expose the path: ENOENT would not prove cgroup access denial.
        return ('export NVIDIA_VISIBLE_DEVICES=void CUDA_VISIBLE_DEVICES=0; ' + CONTAINER +
                ' --container-mounts=/dev/nvidia0:/dev/nvidia0'
                ' /usr/local/bin/python3 -c ' + shlex.quote(program))
    return 'export CUDA_VISIBLE_DEVICES=0; srun python3 -c ' + shlex.quote(program)


def cpu_absent_command():
    return 'srun python3 -c ' + shlex.quote(
        'from pathlib import Path; import json,socket; '
        'assert not Path("/dev/nvidia0").exists(); '
        'print(json.dumps({"hostname":socket.gethostname(),"gpu_device_absent":True}))')


def holder_command():
    program = ('import runpy,time; runpy.run_path(' + repr(GPU_PROGRAM) +
               ',run_name="__main__"); print("GPU_HELD",flush=True); time.sleep(120)')
    return ENV + CONTAINER + ' /usr/local/bin/python3 -u -c ' + shlex.quote(program)


def outer_cgroup_probe(pid):
    """Read the node-visible PID identity and its ancestor memory limits."""
    program = '''
import json,sys
from pathlib import Path
pid=int(sys.argv[1])
process=Path("/proc")/str(pid)
stat=process.joinpath("stat").read_text().rsplit(")",1)[1].split()
group=process.joinpath("cgroup").read_text().strip()
root=Path("/sys/fs/cgroup")
current=root/group.split("::",1)[1].lstrip("/")
limits=[]
while current == root or root in current.parents:
    limit=current/"memory.max"
    if limit.exists():
        limits.append({"path":str(current),"memory.max":limit.read_text().strip()})
    if current == root:
        break
    current=current.parent
print(json.dumps({"pid":pid,"starttime":stat[19],"state":stat[0],
                  "cgroup":group,"memory_limits":limits}))
'''
    return compose_argv('python3', '-c', program, str(int(pid)), service='gpu01', user='root')


def pid_cleanup_probe(pid, starttime):
    """Reject a live original process, without mistaking a reused PID for it."""
    program = '''
import json,sys
from pathlib import Path
pid=int(sys.argv[1])
path=Path("/proc")/str(pid)/"stat"
try:
    stat=path.read_text().rsplit(")",1)[1].split()
except FileNotFoundError:
    stat=None
live=stat is not None and stat[19] == sys.argv[2] and stat[0] not in ("Z","X")
print(json.dumps({"pid":pid,"expected_starttime":sys.argv[2],
                  "observed_starttime":stat[19] if stat else None,
                  "state":stat[0] if stat else None,"live":live}))
assert not live, "Cancelled container task remains alive"
'''
    return compose_argv('python3', '-c', program, str(int(pid)), str(int(starttime)),
                        service='gpu01', user='root')


def events(output):
    result = {}
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and 'event' in event:
            result[event['event']] = event
    return result


def verify_compute_output(output, job, container):
    """Verify the real CUDA result and execution identity for both entry points."""
    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    record = events(output)
    compute = record.get('gpu_compute', {})
    require(compute.get('status') == 'PASS' and compute.get('verified_elements') == 65539
            and compute.get('elements') == 65539 and compute.get('kernel_launched') is True
            and compute.get('synchronized') is True,
            'CUDA kernel numerical verification failed: ' + output)
    env = record['gpu_environment']
    require(env['uid'] == 1000, 'GPU job unexpectedly ran as root')
    require(len(env['affinity']) == 1 and set(env['affinity']) <= {4, 5, 12, 13},
            'GPU job escaped assigned CPU affinity: ' + str(env['affinity']))
    require(env['environment'].get('SLURM_JOB_ID') == str(job), 'Wrong Slurm job identity')
    require(record['gpu_device']['visible_devices'] == 1, 'Expected exactly one GPU')
    require(bool(record['gpu_device']['name']), 'Missing GPU model evidence')
    if container:
        require(env['image'] and env['image']['name'] == 'slurm-lab-gpu-job',
                'Not executing the independent job image')
        require(env['executable'].startswith('/usr/local/bin/python'), 'Wrong image Python')
    else:
        require(env['image'] is None, 'Direct job unexpectedly uses the nested image')
        require('slurmstepd' in env['cgroup'], 'Direct GPU process is outside its Slurm cgroup')
    return record


def verify_compute(s, job, container):
    return verify_compute_output(s.read_output(job), job, container)


def gpu_cases(s):
    """Construct callbacks without running commands or creating results."""
    def direct():
        job = s.submit('gpu-direct', direct_command(), GPU_OPTIONS)
        s.finish(job)
        return verify_compute(s, job, False)

    def container():
        job = s.submit('gpu-container', container_command(), GPU_OPTIONS)
        s.finish(job)
        return verify_compute(s, job, True)

    def deny(container):
        job = s.submit('gpu-denied-container' if container else 'gpu-denied-direct', denied_command(container),
                       ('-p', 'gpu', '-c', '1', '--mem=256M'))
        s.finish(job)
        s.require('"device_denied": true' in s.read_output(job), 'No explicit device denial evidence')
        return {"job_id": job, "output": s.read_output(job)}

    def cpu_nodes_have_no_gpu():
        evidence = []
        command = cpu_absent_command()
        for node in ("cpu01", "cpu02"):
            job = s.submit("no-gpu-" + node, command, ("--nodelist=" + node,))
            s.finish(job)
            evidence.append({"job_id": job, "output": s.read_output(job)})
        return evidence

    def queue_and_cancel():
        holder = s.submit('gpu-container-holder', holder_command(), GPU_OPTIONS)
        s.wait_state(holder, {'RUNNING'})
        deadline = time.monotonic() + 90
        while 'GPU_HELD' not in s.read_output(holder):
            s.require(time.monotonic() < deadline, 'GPU holder never completed CUDA startup')
            state = s.job(holder).get('JobState')
            s.require(state == 'RUNNING', 'GPU holder exited before queue check: ' + str(state))
            time.sleep(0.5)
        holder_record = verify_compute(s, holder, True)
        # Enroot namespaces /proc/self/cgroup to "/"; observe the live PID from
        # the outer node, rather than confusing namespace display with escape.
        pid = holder_record['gpu_environment']['pid']
        observed = json.loads(s.command(outer_cgroup_probe(pid), timeout=5).stdout)
        sluid = holder_record['gpu_environment']['environment']['SLURM_JOB_SLUID']
        s.require(sluid in observed['cgroup'], 'Container process escaped its allocated Slurm job')
        s.require(any(item['memory.max'] == str(512 * 1024 * 1024)
                      for item in observed['memory_limits']), 'Container lost the job memory limit')
        queued = s.submit('gpu-container-queued', container_command(), GPU_OPTIONS)
        s.wait_state(queued, {'PENDING'})
        time.sleep(2)
        s.require(s.job(queued).get('JobState') == 'PENDING', 'GPU allocated to two jobs simultaneously')
        s.cancel(holder)
        s.finish(holder, expected='CANCELLED')
        # The same node-visible PID must disappear when Slurm cancels the job.
        cleanup = json.loads(s.command(pid_cleanup_probe(pid, observed['starttime']), timeout=5).stdout)
        s.finish(queued)
        queued_record = verify_compute(s, queued, True)
        return {"cancelled_job": holder, "queued_job": queued,
                "holder": holder_record, "node_observation": observed,
                "pid_cleanup": cleanup, "released": queued_record}
    return [
        ('gpu_direct_cuda_numerical', direct),
        ('gpu_independent_oci_cuda_numerical', container),
        ('gpu_no_gres_direct_denied', lambda: deny(False)),
        ('gpu_no_gres_container_denied', lambda: deny(True)),
        ('cpu_nodes_no_gpu_device', cpu_nodes_have_no_gpu),
        ('gpu_container_queue_cancel_release', queue_and_cancel),
    ]


