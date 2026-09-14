# Methodology

## Serving

Each model runs in its own container, pinned to specific cards with
`ZE_AFFINITY_MASK`, and exposes an OpenAI-compatible endpoint.

- **gpt-oss-20b** — `intel/vllm:0.21.0-xpu`, `--tensor-parallel-size 1`,
  `--max-model-len 65536`, `--gpu-memory-utilization 0.80`, `--enforce-eager`.
  Tool calling needs `--enable-auto-tool-choice --tool-call-parser openai`; without the
  parser you get zero tool calls and empty content.
- **Qwen3-Coder-30B-A3B, Qwen3-Next-80B-A3B** — `ghcr.io/ggml-org/llama.cpp:server-intel`,
  SYCL backend, F16 accumulation.

`--enforce-eager` matters: without it, the Inductor compile pass spawns a worker per
device and has taken the host down for us. There is no measurable decode benefit on
this hardware to justify the risk.

Container guardrails, which we recommend reproducing:

```yaml
mem_limit: 32g
memswap_limit: 32g   # equal to mem_limit -> clean OOM instead of a host swap storm
cpus: 12
shm_size: 8g         # NOT ipc: host, which cancels the cgroup limit entirely
restart: "no"
```

## Measurement

[`scripts/bench_config_e.py`](scripts/bench_config_e.py) drives the endpoints over
HTTP and reports token counts from each response's `usage` object rather than counting
client-side, so tokenisation differences between models don't distort the comparison.

- **Decode rate** = `completion_tokens / wall_time` for a single request, measured
  **warm** (a throwaway request is sent first — cold is 3–4× slower and we report that
  separately).
- **Prefill** = `prompt_tokens` and the time to first token on a ~4 000-token prompt.
- **Concurrency** = N requests dispatched simultaneously via a thread pool, 300
  `max_tokens` each, `temperature 0.7`.

### The concurrency mistake to avoid

Our first run computed aggregate throughput as *total tokens ÷ global wall time*. That
is wrong when requests have different durations: the fast models finish early and their
idle time gets counted as productive, inflating their apparent rate and hiding
regression in the slow one.

**Measure each request's own wall time**, then report per-request rate and the sum
separately. Doing it correctly is what revealed that a large model on llama.cpp
*loses* aggregate throughput as concurrency rises — the opposite of what the first
run suggested.

## Host and device telemetry

- Host RAM from `/proc/meminfo` `MemAvailable`, sampled at idle and at the trough
  during load.
- VRAM per card from the `xe` driver's `fdinfo` entries.
- Power, temperature and fan from the `xe` sysfs energy counters, sampled on a 15 s
  timer; the four-card figure quoted in [`benchmarks.md`](benchmarks.md) was also
  cross-checked at the wall against UPS load telemetry, and excludes CPU and the rest
  of the system.

## Reproducing

The script assumes three endpoints on localhost. Adjust the `EP` list at the top for
your ports and model names. It writes a Markdown report to stdout.

```sh
python3 scripts/bench_config_e.py
```

Nothing in it is specific to our hardware beyond those endpoints — it will work against
any OpenAI-compatible server.
