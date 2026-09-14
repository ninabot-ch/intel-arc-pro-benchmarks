# Benchmarks — 4× Arc Pro B60 24 GB

All figures measured 2026-09-10 / 2026-09-11 on the machine described in the
[README](README.md). See [`methodology.md`](methodology.md) before comparing these to
anything else.

**Read this first:** the host is a 2018 X299 platform, the cards run at **PCIe x8
Gen3**, and the machine simultaneously carries an unrelated production workload
(PostgreSQL, ten Celery workers, several web services). These numbers are a floor, not
a ceiling. A dedicated modern host should do better on load time and on anything
crossing PCIe; steady-state single-card decode should be unchanged, since the weights
are already in VRAM by then.

## Resident configuration

Three MoE models held in VRAM at the same time — 130 B parameters combined, ~3 B active
per token in each.

| Card | Model | Format / runtime | Weights | Active params |
|---|---|---|---|---|
| 0 | gpt-oss-20b | MXFP4 · vLLM-XPU | 13 GB | ~3.6 B |
| 1 | Qwen3-Coder-30B-A3B | GGUF Q4_K_XL · llama.cpp SYCL | 17.7 GB | 3 B |
| 2 + 3 | Qwen3-Next-80B-A3B | GGUF Q3_K_XL · llama.cpp SYCL | 35.6 GB | 3 B |

Total VRAM in use, weights plus KV cache: **81.7 GB of 96 GB**.

Card 0 sits at 23.3 / 24 GB — that is tighter than we would ship.

## Single-model throughput, warm

| Model | Decode | Prefill (~4k tokens) |
|---|---|---|
| Qwen3-Coder-30B-A3B | **82.4 tok/s** | 4 098 tok in 4.2 s |
| gpt-oss-20b | **41.2 tok/s** | 3 307 tok in 2.4 s |
| Qwen3-Next-80B-A3B | **36.2 tok/s** | 4 098 tok in 10.3 s |

Cold first call is 3–4× slower — see [failure mode 6](failure-modes.md#6-first-inference-after-load-is-34-slower).

## Concurrency

### All three models at once

12 simultaneous requests, 4 per model, 300 tokens each:

- **3 600 tokens in 30.3 s = 119 tok/s aggregate**
- No errors, and no model degraded another — the cards are isolated

### Per-model scaling, and where it breaks

This is the measurement that matters most for sizing, and it is the one we got wrong
the first time.

**gpt-oss-20b on vLLM** (continuous batching):

| Concurrent requests | Per request | Aggregate |
|---|---|---|
| 1 | 35.1 tok/s | 35.1 |
| 2 | 35.0 tok/s | 70.0 |
| 4 | 33.6 tok/s | **133.9** |
| 8 | — | **241** |

Near-linear. This is what continuous batching buys.

**Qwen3-Next-80B on llama.cpp** (no continuous batching):

| Concurrent requests | Per request | Aggregate |
|---|---|---|
| 1 | 32.0 tok/s | 32.0 |
| 2 | 14.5 tok/s | 28.8 |
| 4 | 7.0 tok/s | **20.7** |

**Aggregate throughput goes down as concurrency rises.** llama.cpp has no continuous
batching, so requests contend rather than batch.

> ### Correction
>
> Our first concurrency run reported "4 simultaneous requests per model with no
> degradation". That was wrong: it divided token counts by global wall-clock time,
> which flattered the fast models and hid the 80B's regression. The table above is the
> corrected measurement. The practical consequence — **a large model on llama.cpp
> serves about two concurrent users, not four** — only became visible after the fix.

### Design rule we derived

Anything latency-sensitive (voice, interactive completion) must be served by vLLM, not
llama.cpp. Voice needs roughly 15 tok/s per speaker (speech is ~3.5 tok/s, plus a
sentence of lead for TTS). That is 2 concurrent conversations on the llama.cpp-served
80B, versus 4+ on the vLLM-served 20b.

## Host resources

| | Idle, 3 models loaded | Under 12 concurrent requests |
|---|---|---|
| Host RAM available | 43.1 GB / 62 GB | 41.5 GB (trough) |
| VRAM used | 81.7 GB / 96 GB | same |
| Power, 4 cards | 163 W | **211 W** peak |
| Temperatures | 52–62 °C | 52–62 °C |

**64 GB of host RAM is enough for this configuration**, with 41 GB still free at the
worst moment — while also carrying a full production workload. The constraint is at
**load** time, not serving time; see
[failure mode 5](failure-modes.md#5-models-must-be-loaded-sequentially).

Power was read at the wall for the four cards only, via a UPS providing per-load
telemetry. It excludes CPU and the rest of the system.

## What we have not measured

- Tensor parallel, at any size — blocked, see
  [failure mode 3](failure-modes.md#3-oneccl-cannot-exchange-ipc-handles-between-workers-tensor-parallel-blocker)
- Arc Pro B70 (BMG-G31) — no cards yet
- Arc Pro B60 Dual — no cards yet
- Long-context behaviour beyond 64k
