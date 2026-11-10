# Tensor parallel on 4× Arc Pro B60 — Qwen3.8-27B, vLLM 0.32 XPU

Measured in one evening, from 20:00 on 2026-11-10 to shortly after midnight, on the
machine described in the [README](README.md). This is the tensor-parallel benchmark
that [`failure-modes.md`](failure-modes.md) listed as still open.

**Read [Limits](#limits) before quoting anything from this page.** Every figure is a
single run on a shared host with a synthetic load.

Short version:

- Tensor parallel works on these cards with vLLM 0.32.0 built for XPU, at TP=2 and TP=4.
- `--enforce-eager` was the reason our first runs were slow. At TP=4 the FP8 model
  decoded at 7.2–8.0 tok/s on one stream with it and 27.3 tok/s without.
- Out of the box, a vLLM worker that can see several cards made host RAM fall by about
  as much as the VRAM it allocated. Giving each worker exactly one visible card removed
  that, and is what allowed a 131k context at 80 % memory utilisation on a 64 GB host.
- INT4 weights were about twice as fast as FP8 on one stream (59 vs 27 tok/s) and
  scored the same on a small home-made quality grid. MTP speculative decoding added about
  60 % on a single stream and stopped paying somewhere between 16 and 32 concurrent
  streams.
- Prompt reading (prefill) stayed slow in every configuration: under 1 000 tok/s, and
  nearer 700 on a 110k-token prompt. We have not fixed it and do not know why.

## Hardware and software

| | |
|---|---|
| GPUs | 4× Intel Arc Pro B60 24 GB (PCI ID `8086:e211`), PCIe x8 Gen3 |
| Host | Intel i9-9980XE, MSI MEG X299 Creation, 64 GB DDR4 |
| Kernel / driver | Ubuntu 24.04, kernel 7.0.0-38-generic, `xe` driver |
| vLLM | 0.32.0, built locally from the upstream `v0.32.0` tag with `docker/Dockerfile.xpu` |
| In that image | torch 2.14.0+xpu, oneCCL 2022.1.2 |
| llama.cpp | `ghcr.io/ggml-org/llama.cpp:server-vulkan`, build 12242 (Flash-Next test only) |
| Models | `Qwen/Qwen3.8-27B-FP8`, `RedHatAI/Qwen3.8-27B-INT4`, `unsloth/Qwen3.8-Flash-Next-GGUF` (UD-IQ4_XS) |

Why a local build: the published `intel/vllm:0.21.0-xpu` image we used until now does
not register the `Qwen3_5ForConditionalGeneration` architecture, so it cannot load
this model. Upstream 0.32.0 does, and ships an XPU Dockerfile.

The host was **not idle**. It carried its usual unrelated workload (databases, workers,
web services, swap already in use), and three small GPU services stayed loaded during
the later runs: one on card 0, two on card 3. The earlier resident models from
[`benchmarks.md`](benchmarks.md) were stopped for the duration.

## Recipe

Everything needed is in [`scripts/tp27/`](scripts/tp27/).

```sh
# 1. image, from a checkout of vLLM at tag v0.32.0
docker build -f docker/Dockerfile.xpu -t vllm-xpu:0.32.0 .

# 2. patched executor: one visible card per worker (see below)
docker run --rm --entrypoint cat vllm-xpu:0.32.0 \
  /opt/venv/lib/python3.12/site-packages/vllm/v1/executor/multiproc_executor.py \
  > scripts/tp27/multiproc_executor.py
patch -p4 -d scripts/tp27 < scripts/tp27/one-device-per-worker.patch

# 3. serve (INT4, TP=4, MTP 2 by default — see the compose file for the variants)
cd scripts/tp27 && MODELS=/path/to/models docker compose up -d
```

Environment and container settings, and what each one is for:

| Setting | Why |
|---|---|
| `CCL_ZE_IPC_EXCHANGE=pidfd` | The only oneCCL IPC mode that gets workers past start-up on this stack ([failure mode 3](failure-modes.md#3-oneccl-cannot-exchange-ipc-handles-between-workers-tensor-parallel-blocker)) |
| `cap_add: SYS_PTRACE`, `seccomp:unconfined` | `pidfd_getfd` needs both inside a container; without them oneCCL falls back to `drmfd` and fails |
| `/dev/dri/by-path` mounted read-write | Carried over from the September attempts |
| `CCL_TOPO_P2P_ACCESS=0` | Carried over from the September attempts; we did not test these runs without it |
| `VLLM_WORKER_MULTIPROC_METHOD=spawn` | Same: carried over, not tested without |
| `ZE_AFFINITY_MASK=0,1,2,3` + `--device-ids 0,1,2,3` | Cards given to the server; with the patch, worker N is started with only the Nth of them visible |
| `VLLM_XPU_ONE_DEVICE_PER_WORKER=1` | Enables the patch. **Not an upstream vLLM variable** |
| `mem_limit` = `memswap_limit` = `26g`, `cpus: 12`, `shm_size: 16g` | Guardrails: a clean OOM kill rather than a host swap storm |

vLLM options: `--tensor-parallel-size 4 --max-model-len 131072 --max-num-seqs 32
--gpu-memory-utilization 0.80 --kv-cache-dtype fp8`, plus for MTP
`--speculative-config.method mtp --speculative-config.num_speculative_tokens 2`.
The dotted form matters in a compose `command: >` block: the JSON form of
`--speculative-config` did not survive it for us.

`--kv-cache-dtype fp8` works on XPU. In one comparison at TP=4, 42 % utilisation and a
32k context (before the patch), it raised the KV cache from 33 480 to 52 186 tokens.

### Why not `--enforce-eager`

[`methodology.md`](methodology.md) recommends `--enforce-eager` for vLLM 0.21 on this
hardware, because the compile pass had taken the host down for us and we saw no decode
benefit. **On vLLM 0.32.0 with this model that advice is wrong**, and we started the
evening by following it:

| FP8, 32k context | 1 stream | 8 streams, aggregate | KV cache |
|---|---|---|---|
| TP=2, 80 % util, `--enforce-eager` | 8.4–9.1 tok/s | 71 tok/s | 56 987 tokens |
| TP=2, 80 % util, compiled | 14.8 tok/s | 103 tok/s | 53 426 tokens |
| TP=4, 42 % util, `--enforce-eager` | 7.2–8.0 tok/s | 61.4 tok/s | 39 891 tokens |
| TP=4, 42 % util, compiled | **27.3 tok/s** | **177 tok/s** | 33 480 tokens |

The compile pass took 72–73 s at TP=2 and 93–94 s at TP=4 (`torch.compile took …` in the
server log), and the container's memory peaked at 14 614 MiB and 18 313 MiB respectively
with `cpus: 12`. The runaway we saw in September did not reproduce. The compiled runs give
up a little KV cache (graph memory is reserved first).

With `--enforce-eager`, TP=4 was no faster per stream than TP=2. Compiled, it was.

We also re-ran the eager TP=2 case with 4–6 GB of host RAM free rather than ~1 GB and
got the same rate, so host memory pressure was not what made the eager runs slow.

### One visible card per worker

**Symptom.** With the stock executor, every worker process sees all the cards in
`ZE_AFFINITY_MASK`. Host `MemAvailable` then drops by roughly the amount of VRAM the
server allocates, in memory that is charged neither to the container's cgroup nor to
`Shmem`. On a 64 GB host this is what limits the server, long before VRAM does: we had
to hold TP=4 at 42 % utilisation, and it still left under 0.5 GB available.

**Change.** [`one-device-per-worker.patch`](scripts/tp27/one-device-per-worker.patch)
(about 20 lines, against `vllm/v1/executor/multiproc_executor.py` at v0.32.0) sets
`ZE_AFFINITY_MASK` to a single card around each worker's `proc.start()`, then restores
it. oneCCL with `pidfd` exchange still works between single-card workers.

Mount the patched file over the copy in `site-packages`. That is the one `vllm serve`
runs. Mounted over the source checkout in `/workspace/vllm` instead, it has no effect —
and `python -c` run from that directory will still tell you the patch is in place.

**Host memory, sampled every second** by
[`sample-host-mem.sh`](scripts/tp27/sample-host-mem.sh) (MiB, from `/proc/meminfo` and
the container's `memory.current`):

| Run (FP8 unless noted) | Patch | `MemAvailable` start → minimum | `SwapFree` start → minimum | Container cgroup, max |
|---|---|---|---|---|
| TP=2, 85 % util, eager | no | 48 219 → 1 256 | 19 084 → 14 265 | 14 367 |
| TP=4, 42 % util, eager | no | 48 378 → 471 | 18 955 → 12 373 | 17 274 |
| TP=2, 80 % util, compiled | no | 45 104 → 3 165 | 21 921 → 17 024 | 14 614 |
| TP=4, 42 % util, compiled | no | 49 080 → 494 | 19 979 → 13 223 | 18 313 |
| TP=4, 80 % util, 131k context | **yes** | 40 003 → 18 150 | 23 835 → 23 568 | 26 624 |
| TP=4, 80 % util, 131k, INT4 | **yes** | 43 182 → 20 512 | 18 660 → 18 496 | 26 623 |
| TP=4, 80 % util, 131k, INT4, 64 streams | **yes** | 43 467 → 16 219 | 19 661 → 18 746 | 26 623 |

Without the patch, a server budgeted for 38–41 GB of VRAM (2 × 80 %, 2 × 85 % or
4 × 42 % of 24 GB) took 42–49 GB of available RAM plus 5–7 GB of swap, of which the
container itself accounts for 14–18 GB. With the patch, a server budgeted for about
77 GB of VRAM (4 × 80 %) took 22–27 GB, which is about what the container's own cgroup
shows. That cgroup sat at its 26 GiB limit; we did not look into what fills it. Other
workloads on the host move all of these numbers by a few GB in either direction.

Before the patch, combining this server with the rest of the host's workload once ended
in a swap storm and we had to stop the server. After it, the same host ran the 131k
configuration with memory-pressure stall at zero.

Model load also changed: `Model loading took` reports 34.8–38.0 s per worker for FP8 at
TP=4 without the patch and 13.8–14.1 s with it. The page cache was warmer by then, so we
do not attribute the whole difference to the patch.

**What we do not know.** Why. The comment in the patch names a driver code path
(DMA-buf/TTM mirroring for processes that see several devices). That is a hypothesis
taken from a community report on a similar setup, not something we established. What we
measured is narrower: the uncounted memory is there when a worker sees several cards and
is not there when it sees one; and an earlier single-card vLLM 0.21 server on the same
host never showed it. We have not run 0.32 at TP=1 to separate "multi-card" from
"version".

## Results

Client-side figures come from [`bench27.py`](scripts/tp27/bench27.py) and
[`benchn.py`](scripts/tp27/benchn.py): streamed chat completions, a short French prompt,
`temperature 0.2`, thinking disabled, token counts from the server's `usage` object.
"Per stream" is the median of `completion_tokens ÷ (end − first token)`; "aggregate" is
total completion tokens ÷ wall time of the whole batch, which is fair here because all
requests in a batch are identical. 300 `max_tokens` on one stream; 250 on the 4- and
8-stream rows of `bench27.py`; 300 everywhere in `benchn.py`.

### First series — FP8, `--enforce-eager`, 32k context

| | TP=2 (2 cards, 85 % util) | TP=4 (4 cards, 42 % util) |
|---|---|---|
| Weights per card | 14.34 GiB | 7.17 GiB |
| KV cache | 89 043 tokens (3.19 GiB per card) | 39 891 tokens (0.73 GiB per card) |
| 1 stream | 8.5 tok/s | 7.2–8.0 tok/s |
| 8 streams, aggregate | 68.5 tok/s | 61.4 tok/s |
| Time to first token, warm | 0.37 s | 0.36 s |
| 7 618-token prompt, cold | 9.3 s | 9.5 s |

TP=4 is held at 42 % because of host RAM, not VRAM (see above).

### Second series — compiled

See the table under [Why not `--enforce-eager`](#why-not---enforce-eager). Time to first
token, warm: 0.38 s (TP=2 eager), 0.18–0.32 s (TP=2 compiled), 0.35 s (TP=4 compiled).
The cold 7 618-token prompt still took about 9.3 s in every case.

### With the patch — TP=4, 80 % util, FP8 KV cache, 131k context, compiled

| | FP8 | INT4 |
|---|---|---|
| Weights per card | 7.17 GiB | 4.43 GiB |
| KV cache memory per card | 7.53 GiB | 11.77 GiB |
| KV cache | 918 993 tokens (7.01 × 131 072) | 1 435 834 tokens (10.95 × 131 072) |
| 1 stream | 27 tok/s | **59 tok/s** |
| 8 streams, aggregate | 180 tok/s | **314 tok/s** |
| Time to first token, warm | 0.13 s | not noted |
| 22-question grid | 21 / 22 | 21 / 22 (same question failed) |
| ~110k-token document, cold | 171 s for 109 600 tokens (~640 tok/s) | 154 s |
| Same document, warm | 2.2 s | 2 s |
| Lookups in that document ([`long27.py`](scripts/tp27/long27.py)) | answer correct (one question) | 5 / 5 |

The server selects `XPUFp8BlockScaledMMKernel` for the FP8 weights and
`XPUwNa16LinearKernel` for INT4 (server log).

One INT4 error outside the scored runs: on a two-part question over the 110k-token
document it answered "module 14" where the document says 10.

### MTP speculative decoding — INT4, same configuration

`--speculative-config.method mtp`, 2 speculative tokens. vLLM 0.32 supports it for this
architecture and it runs with the INT4 weights.

| | Without MTP | MTP, 2 tokens | MTP, 3 tokens |
|---|---|---|---|
| 1 stream | 59 tok/s | **93–96 tok/s** | no better than 2 |
| 4 streams, aggregate | — | 237 tok/s | — |
| 8 streams, aggregate | 314 tok/s | 316–330 tok/s | 303 tok/s |
| 22-question grid | 21 / 22 | 21 / 22 | — |
| KV cache | 1 435 834 tokens | 1 217 296, then 1 207 535 with `--max-num-seqs 32` | — |
| First token, ~7.6k-token prompt already cached | ~1.3 s | **~3.0 s** | — |

MTP leaves less KV cache and makes the first token on a long cached prompt slower. We
kept 2 tokens.

### Scaling to 64 streams — INT4, with and without MTP

[`benchn.py`](scripts/tp27/benchn.py), 300 generated tokens per stream.

| Streams | MTP 2: aggregate / per stream | No MTP: aggregate / per stream |
|---|---|---|
| 1 | 93 / 93 tok/s | 59 / 59 tok/s |
| 8 | 316–330 / 45 | 314 / 43 |
| 16 | 404 / 30 | 396 / 30 |
| 32 | 480 / 17 | 563 / 20 |
| 64 | 488 / 8.5 | **685 / 12** |

MTP helps up to about 16 streams and hurts beyond: it spends compute that batching
would otherwise use. 685 tok/s is the highest aggregate we measured, and the curve had
not flattened; we did not test beyond 64. The no-MTP run used `--max-num-seqs 64` (KV
cache 1 404 555 tokens). For that run the server's own 10-second throughput counter
peaked at 762.6 tok/s; we report the lower client-side figure, which includes time to
first token.

### Prompt reading (prefill) — the weak point

Cold reads measured late in the evening with [`prefill.py`](scripts/tp27/prefill.py)
(a fresh random document each time, so nothing is cached). Times were noted to the
nearest second or so; the rates are computed from them:

| Prompt | Time | Rate |
|---|---|---|
| ~8.7k tokens | ~9 s | ~970 tok/s |
| ~32k tokens | ~36 s | ~890 tok/s |
| ~110k tokens | ~2 min 30 | ~730 tok/s |

Earlier in the evening: 7 618 tokens in 9.3–9.5 s (FP8, ~800–820 tok/s), 109 600 tokens
in 171 s (FP8, ~640 tok/s), ~110k in 154 s (INT4). FP8 or INT4, MTP or not,
`--max-num-batched-tokens` at 16 384 or 8 192: no meaningful difference.

So a 100k-token document costs two to three minutes the first time it is read. Once it
is in the prefix cache the same prompt answers in about 2 s. We have not found the
cause. Candidates we have not tested: the prefill kernels for this model's
linear-attention layers on XPU, or simply the compute these cards have for a dense 27B.

### Qwen3.8-Flash-Next on llama.cpp Vulkan

One exploratory run, to see whether a much larger MoE would load at all: UD-IQ4_XS
GGUF (93.7 GB), llama.cpp Vulkan, layers split across the four cards (about 17 GB per
card), 16 384-token context, one slot.

| | |
|---|---|
| Vulkan devices seen | 4, 24 480 MiB each |
| Ready to serve | 2 min 04 s after start |
| Decode | 5.0–5.6 tok/s (5.34 on the 300-token run) |
| Prompt eval | 7 618 tokens in 30.1 s = 253 tok/s |
| 22-question grid | 22 / 22 |

The server logs `fused top-k mask not supported, set to disabled` at load. It loads and
answers correctly; at 5 tok/s it is not usable interactively on this machine. We did not
try SYCL for this model.

## Limits

- **Every number is one run.** No repeats, no variance, no confidence interval. Where a
  range is given it is two or three readings from the same session.
- **Synthetic load.** One short French prompt, 250–300 generated tokens, identical
  requests in each batch, `temperature 0.2`. Real traffic with mixed prompt lengths will
  look different, especially given the prefill rate.
- **Quality is barely tested.** The grid is 22 home-made questions in French
  ([`qual27.py`](scripts/tp27/qual27.py): arithmetic, logic, JSON extraction, French,
  instruction following, four tool calls), scored by string matching, run once per
  model. It can tell "broken" from "not broken". It cannot tell FP8 from INT4, and
  21 / 22 on both is not evidence that INT4 loses nothing. No standard benchmark and no
  agent benchmark has been run on these configurations.
- **Cold prompt reading is slow and unexplained**: ~700–950 tok/s, see above.
- **MTP slows the first token on a long cached prompt**: ~3 s instead of ~1.3 s on ~7.6k
  tokens. Measured once.
- **The cause of the host-RAM mirroring is not established.** The patch is a workaround
  found by experiment. It is not upstream, we have run it for one evening, and the
  explanation in its comment is a hypothesis.
- **Flash-Next runs at 5 tok/s.** That row is a "does it load" result, nothing more.
- **Shared host.** Unrelated workloads and three small GPU services were running. Card 3
  in particular was not empty.
- **Not everything was logged.** Server logs (KV cache sizes, weights per card, compile
  and load times, kernels) and host-memory samples exist for the runs in the memory
  table. The client-side rates, times to first token and grid scores for the other rows
  were written down from the terminal and the benchmark output was not saved. For the
  "time to first token, warm" rows we did not record which prompt they refer to. For the
  MTP rows at 32 and 64 streams we did not record `--max-num-seqs`; if it was 32, the
  64-stream MTP row includes queueing.
- **Not measured at all:** power draw in these configurations, TP=2 with the patch as a
  served configuration, vLLM 0.32 at TP=1, anything on B70 or B60 Dual, contexts beyond
  131k, more than 64 streams.
- **Scripts.** The files in `scripts/tp27/` are the ones we ran, with three differences:
  host paths and port bindings were removed from the compose file and the sampling
  script; and in `qual27.py` a company name used in two prompts and a first name in one
  e-mail address were replaced by placeholders. The scores above were obtained with the
  original prompts.

If you can reproduce or contradict any of this on your own hardware, please open an
issue — especially the host-memory behaviour and the prefill rate.
