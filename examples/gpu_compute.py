#!/usr/bin/env python3
"""Launch a CUDA Driver API vector-add kernel; no CUDA toolkit or CPU fallback."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import socket
import sys


ELEMENTS = 65_539  # Deliberately not a multiple of the block size.
PTX = b"""
.version 6.0
.target sm_52
.address_size 64

.visible .entry vector_add(
    .param .u64 input_a,
    .param .u64 input_b,
    .param .u64 output_c,
    .param .u32 count
)
{
    .reg .pred %p;
    .reg .b32 %r<5>;
    .reg .b64 %rd<8>;
    .reg .f32 %f<4>;
    ld.param.u64 %rd1, [input_a];
    ld.param.u64 %rd2, [input_b];
    ld.param.u64 %rd3, [output_c];
    ld.param.u32 %r4, [count];
    mov.u32 %r1, %ctaid.x;
    mov.u32 %r2, %ntid.x;
    mov.u32 %r3, %tid.x;
    mad.lo.u32 %r1, %r1, %r2, %r3;
    setp.ge.u32 %p, %r1, %r4;
    @%p bra done;
    mul.wide.u32 %rd4, %r1, 4;
    add.u64 %rd5, %rd1, %rd4;
    add.u64 %rd6, %rd2, %rd4;
    add.u64 %rd7, %rd3, %rd4;
    ld.global.f32 %f1, [%rd5];
    ld.global.f32 %f2, [%rd6];
    add.f32 %f3, %f1, %f2;
    st.global.f32 [%rd7], %f3;
done:
    ret;
}
"""


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def compute():
    identity_path = Path("/etc/slurm-lab-job-image.json")
    emit(
        "gpu_environment",
        hostname=socket.gethostname(),
        pid=os.getpid(),
        uid=os.getuid(),
        gid=os.getgid(),
        affinity=sorted(os.sched_getaffinity(0)),
        cgroup=Path("/proc/self/cgroup").read_text().strip(),
        image=json.loads(identity_path.read_text()) if identity_path.exists() else None,
        executable=sys.executable,
        python=sys.version.split()[0],
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        environment={
            key: value
            for key, value in sorted(os.environ.items())
            if key.startswith("SLURM_")
            or key in ("CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES")
        },
    )
    # Loading a missing driver, cuInit failing, or zero devices is a hard error.
    cuda = ct.CDLL("libcuda.so.1")

    def bind(name, *args):
        function = getattr(cuda, name)
        function.argtypes = args
        function.restype = ct.c_int
        return function

    error_name = bind("cuGetErrorName", ct.c_int, ct.POINTER(ct.c_char_p))
    error_string = bind("cuGetErrorString", ct.c_int, ct.POINTER(ct.c_char_p))

    def call(function, *args):
        result = function(*args)
        if result:
            name, description = ct.c_char_p(), ct.c_char_p()
            error_name(result, ct.byref(name))
            error_string(result, ct.byref(description))
            raise RuntimeError(
                f"{function.__name__}: CUDA error {result}: "
                f"{name.value!r}: {description.value!r}"
            )

    pointer = ct.c_void_p
    device_pointer = ct.c_uint64
    init = bind("cuInit", ct.c_uint)
    get_count = bind("cuDeviceGetCount", ct.POINTER(ct.c_int))
    get_device = bind("cuDeviceGet", ct.POINTER(ct.c_int), ct.c_int)
    get_name = bind("cuDeviceGetName", pointer, ct.c_int, ct.c_int)
    get_pci = bind("cuDeviceGetPCIBusId", pointer, ct.c_int, ct.c_int)
    get_version = bind("cuDriverGetVersion", ct.POINTER(ct.c_int))
    create_context = bind("cuCtxCreate_v2", ct.POINTER(pointer), ct.c_uint, ct.c_int)
    destroy_context = bind("cuCtxDestroy_v2", pointer)
    load_module = bind("cuModuleLoadData", ct.POINTER(pointer), pointer)
    unload_module = bind("cuModuleUnload", pointer)
    get_function = bind("cuModuleGetFunction", ct.POINTER(pointer), pointer, ct.c_char_p)
    allocate = bind("cuMemAlloc_v2", ct.POINTER(device_pointer), ct.c_size_t)
    free = bind("cuMemFree_v2", device_pointer)
    to_device = bind("cuMemcpyHtoD_v2", device_pointer, pointer, ct.c_size_t)
    to_host = bind("cuMemcpyDtoH_v2", pointer, device_pointer, ct.c_size_t)
    memset = bind("cuMemsetD8_v2", device_pointer, ct.c_ubyte, ct.c_size_t)
    launch = bind(
        "cuLaunchKernel", pointer,
        ct.c_uint, ct.c_uint, ct.c_uint,
        ct.c_uint, ct.c_uint, ct.c_uint,
        ct.c_uint, pointer, ct.POINTER(pointer), ct.POINTER(pointer),
    )
    synchronize = bind("cuCtxSynchronize")
    call(init, 0)
    count = ct.c_int()
    call(get_count, ct.byref(count))
    if count.value < 1:
        raise RuntimeError("CUDA reported no accessible GPU; CPU fallback is forbidden")
    device = ct.c_int()
    call(get_device, ct.byref(device), 0)
    name, pci = ct.create_string_buffer(256), ct.create_string_buffer(32)
    version = ct.c_int()
    call(get_name, name, len(name), device)
    call(get_pci, pci, len(pci), device)
    call(get_version, ct.byref(version))
    emit("gpu_device", name=name.value.decode(), pci_bus_id=pci.value.decode(),
         driver_version=version.value, visible_devices=count.value, ordinal=0)

    context, module, kernel = pointer(), pointer(), pointer()
    allocations = []
    call(create_context, ct.byref(context), 0, device)
    try:
        call(load_module, ct.byref(module), ct.c_char_p(PTX))
        call(get_function, ct.byref(kernel), module, b"vector_add")
        array_type = ct.c_float * ELEMENTS
        a = array_type(*(i % 1024 * 0.25 for i in range(ELEMENTS)))
        b = array_type(*((i % 127 - 63) * 0.5 for i in range(ELEMENTS)))
        result = array_type()
        byte_count = ct.sizeof(a)
        for _ in range(3):
            allocation = device_pointer()
            call(allocate, ct.byref(allocation), byte_count)
            allocations.append(allocation)
        da, db, dc = allocations
        call(to_device, da, a, byte_count)
        call(to_device, db, b, byte_count)
        # Poison output so a kernel that fails to write any element cannot pass.
        call(memset, dc, 0xFF, byte_count)
        n = ct.c_uint(ELEMENTS)
        arguments = (pointer * 4)(*(ct.cast(ct.byref(arg), pointer) for arg in (da, db, dc, n)))
        blocks, threads = (ELEMENTS + 255) // 256, 256
        call(launch, kernel, blocks, 1, 1, threads, 1, 1, 0, None, arguments, None)
        call(synchronize)
        call(to_host, result, dc, byte_count)
        for i, actual in enumerate(result):
            expected = (i % 1024) * 0.25 + (i % 127 - 63) * 0.5
            if actual != expected:
                raise RuntimeError(f"GPU mismatch at element {i}: {actual!r} != {expected!r}")
        emit("gpu_compute", status="PASS", kernel="vector_add", elements=ELEMENTS,
             verified_elements=ELEMENTS, kernel_launched=True, synchronized=True,
             blocks=blocks, threads_per_block=threads, device_buffer_bytes=3 * byte_count,
             result_sha256=hashlib.sha256(bytes(result)).hexdigest())
    finally:
        # A context teardown releases allocations even if an earlier cleanup fails.
        try:
            for allocation in reversed(allocations):
                call(free, allocation)
            if module:
                call(unload_module, module)
        finally:
            call(destroy_context, context)


if __name__ == "__main__":
    try:
        compute()
    except (OSError, RuntimeError) as error:
        emit("gpu_compute", status="FAIL", error=str(error))
        sys.exit(1)
