# Failure modes

Every entry is something we hit on real hardware, with the exact symptom. Ordered
roughly by how much time it cost us.

---

## 1. vLLM-XPU only serves quantisations that have a native XPU kernel

**Symptom.** Any quantised MoE other than gpt-oss MXFP4 dies at load:

```
Marlin does not support weight_bits = uint4 ... device_capability = -1
```

**Cause.** vLLM routes expert layers to Marlin, a CUDA kernel with no XPU path. The
`moe_wna16` path has no XPU implementation either. Passing `--quantization` explicitly
changes nothing — the dispatch happens below that.

**Consequence.** On Arc Pro today, **vLLM serves gpt-oss MXFP4 and little else in the
MoE family**. Everything else has to go through llama.cpp SYCL, which means giving up
continuous batching.

**Related:** dense AWQ *does* work on XPU (`int4_gemm_w4a16`). MoE AWQ does not.

## 2. AWQ requires `--dtype float16` explicitly

Models usually declare `bfloat16` in their config. AWQ on XPU fails unless you override
with `--dtype float16`.

## 3. oneCCL cannot exchange IPC handles between workers (tensor parallel blocker)

**Symptom.** Any `--tensor-parallel-size >= 2` fails during worker startup:

```
CCL_WARN | pidfd is not supported, fallbacks to drmfd exchange mode
CCL_ERROR| ze_handle_manager.cpp:42 mem_to_ipc_handle:
           condition device_fd != ccl::utils::invalid_fd failed
           device_fd is invalid value
```

followed by `WorkerProc failed to start` and
`RuntimeError: Engine core initialization failed`.

**What we tried**, all with `CCL_TOPO_P2P_ACCESS=0` set:

| `CCL_ZE_IPC_EXCHANGE` | `/dev/dri/by-path` mount | Result |
|---|---|---|
| `sockets` | read-only | fails as above, clean exit |
| `drmfd` | read-write | fails as above, clean exit |
| `pidfd` + `SYS_PTRACE` + `seccomp:unconfined` | read-write | **gets past the IPC stage** |

**Note on `CCL_TOPO_P2P_ACCESS=0`.** This workaround is documented elsewhere for
multi-GPU Arc Pro and it did **not** fix anything for us — the failure is upstream of
peer-to-peer access, in IPC handle creation. Worth knowing before you spend a day on it.

The `pidfd` route is the only one that progresses. `pidfd_getfd` needs `CAP_SYS_PTRACE`
and a permissive seccomp profile inside a container, otherwise oneCCL silently falls
back to `drmfd` and then can't obtain a device fd.

**Unresolved.** We have not yet run a clean tensor-parallel benchmark. See §4 for why.

## 4. Two processes on the same GPU wedge the host

**Symptom.** Host becomes unreachable (SSH and ping both dead) for ~2 minutes, then
recovers on its own without a reboot, with a load average above 60.

```
oom-kill: constraint=CONSTRAINT_NONE, global_oom, task=llama-server
xe 0000:6b:00.0: [drm] Tile0: GT0: Engine memory CAT error [18]: class=bcs
xe 0000:6b:00.0: [drm] Tile0: GT0: Engine reset: engine_class=ccs, state=0x289
xe 0000:6b:00.0: [drm] Tile0: GT0: Fault response: Unsuccessful -ENOENT / -EINVAL
```

**Cause.** We started a vLLM tensor-parallel job on `ZE_AFFINITY_MASK=1,2` while two
llama.cpp servers were already holding those cards. The collision triggered a global
OOM and catastrophic memory faults on both GPUs.

**What survived.** PostgreSQL, an API backend and ten Celery workers on the same host
were untouched. The two llama.cpp servers were killed (exit 137) and had to be
restarted by hand, sequentially.

**Lesson.** Card occupancy is not visible from container names. Enumerate it:

```sh
docker ps -a --format '{{.Names}}' | while read c; do
  echo "$c: $(docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep ZE_AFFINITY_MASK)"
done
```

## 5. Models must be loaded sequentially

**Symptom.** Starting three model containers at once at boot reproducibly crashes the
host. Starting them one after another never does.

**Cause.** The host RAM peak is at **load** time, not during serving. Each server maps
its weights before handing them to the GPU. Three at once exceeds what the host has.

**Fix.** `After=` ordering in systemd, or a start script that waits for each server's
health endpoint before starting the next. Budget ~90 s per model.

## 6. First inference after load is 3–4× slower

| Model | First call | Warm |
|---|---|---|
| Qwen3-Coder-30B | 21 tok/s | 82.4 tok/s |
| Qwen3-Next-80B | 19 tok/s | 36.2 tok/s |

Send a throwaway prompt at service start. Otherwise every cold user sees the worst
number the machine can produce.

## 7. `--ipc host` silently cancels `shm_size`

With `ipc: host`, shared-memory buffers escape the container cgroup entirely, so
`mem_limit` no longer bounds the process. Use a private `shm_size` instead, or the
container can take the host down without ever being OOM-killed itself.

The corollary that saved us repeatedly: set `memswap_limit` equal to `mem_limit`. The
container then gets a clean OOM kill instead of dragging the host into a swap storm.

## 8. A card with no 8-pin connector is invisible on the PCI bus

**Symptom.** The GPU does not appear in `lspci` at all — no link trained, nothing.

It looks like a dead card or a dead slot. It is a missing power cable. This is the
canonical symptom, worth checking before you start swapping hardware.

## 9. Battlemage cards show `x1` in lspci — that's cosmetic

Each card presents an internal tree of bridges, the GPU endpoint and an audio device,
and the endpoint may report `x1`. The real link width is on the **root port**'s
`LnkSta`, not the endpoint. Check there before concluding your slot is misconfigured.

## 10. GuC firmware

Shipping firmware was 70.44.1; 70.72.1 from upstream kernel.org fixed instability. It
can be updated without a reboot: drop the uncompressed `.bin` in `/lib/firmware/xe/`
(it takes priority over the distribution's `.zst`), unbind the card's audio function
via `snd_hda_intel`, then unbind and rebind the GPU through the `xe` driver.

## 11. Vulkan is not an alternative to SYCL for decode

Community measurements put SYCL at roughly 2.2× Vulkan for token generation on this
class of hardware. Vulkan is a portability fallback, not a performance path.

---

## Still open

- A clean tensor-parallel benchmark, on cards verified idle, using the `pidfd` route.
- Whether any of this differs on BMG-G31 (B70). We have no B70 data of our own, and
  published third-party B70 numbers on comparable MoE workloads are **lower** than our
  B60 figures — which we cannot currently explain.
