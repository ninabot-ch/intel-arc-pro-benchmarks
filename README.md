# Intel Arc Pro — inference benchmarks and failure modes

Measurements from a **4× Intel Arc Pro B60 24 GB** machine running three resident
LLMs at once, plus a catalogue of the failure modes we hit getting there.

We run this hardware in production, so the numbers are from a working setup rather
than a test bench — and the failure modes are the ones that actually cost us days.

A readable summary of these numbers, with context on the machine behind them:
[ninabot.ch/en/anchor/benchmarks](https://ninabot.ch/en/anchor/benchmarks/).

> **Status:** B60 data only. B70 and Arc Pro B60 Dual measurements will be added to
> this repo when we have the cards.
>
> **Update 2026-11-11:** tensor parallel now works on these cards. A dense 27B model
> served across all four with vLLM 0.32, the recipe, a host-RAM workaround and the
> limits of what we measured are in [`tensor-parallel-27b.md`](tensor-parallel-27b.md).

## What's here

| File | Contents |
|---|---|
| [`benchmarks.md`](benchmarks.md) | Throughput per model, concurrency, VRAM and host RAM pressure, power |
| [`tensor-parallel-27b.md`](tensor-parallel-27b.md) | 2026-11-10/11: Qwen3.8-27B in tensor parallel on vLLM 0.32 XPU — FP8 vs INT4, MTP, 1 to 64 streams, host RAM, recipe and limits |
| [`failure-modes.md`](failure-modes.md) | Exact error strings and what caused them — the part that isn't documented anywhere else |
| [`hardware-notes.md`](hardware-notes.md) | Which motherboards physically take 4 double-width cards, measured from vendor drawings |
| [`methodology.md`](methodology.md) | How the numbers were produced, so they can be compared |
| [`scripts/`](scripts/) | The benchmark scripts; [`scripts/tp27/`](scripts/tp27/) holds the tensor-parallel compose file, patch and measurement scripts |

## The machine

| | |
|---|---|
| GPUs | 4× ASRock Arc Pro B60 Creator 24 GB (BMG-G21), all at PCIe x8 Gen3 |
| Host | Intel i9-9980XE, X299, 64 GB DDR4-3200 |
| OS / driver | Ubuntu 24.04, kernel 7.0 HWE, `xe` driver, GuC 70.72.1 |
| Runtimes | `intel/vllm:0.21.0-xpu` and llama.cpp SYCL (`ghcr.io/ggml-org/llama.cpp:server-intel`) |

The host is a 2018 HEDT platform that also carries an unrelated production workload.
**The numbers here are therefore pessimistic**, particularly anything involving PCIe
or model load time. We say so explicitly wherever it matters.

## Headline numbers

Three MoE models resident simultaneously, one per card (the 80B spans two):

| Model | Format / runtime | Weights | Decode |
|---|---|---|---|
| Qwen3-Coder-30B-A3B | GGUF Q4_K_XL · llama.cpp SYCL | 17.7 GB | **82.4 tok/s** |
| gpt-oss-20b | MXFP4 · vLLM-XPU | 13 GB | **41.2 tok/s** |
| Qwen3-Next-80B-A3B | GGUF Q3_K_XL · llama.cpp SYCL | 35.6 GB | **36.2 tok/s** |

**119 tok/s aggregate** across all three (130 B parameters combined) under 12 concurrent requests, 211 W peak for
the four cards. Full detail and caveats in [`benchmarks.md`](benchmarks.md).

### Tensor parallel, November 2026

One dense model across all four cards — Qwen3.8-27B, vLLM 0.32.0 built for XPU, TP=4,
131k context. Single runs on a shared host with a synthetic load; the
[limits](tensor-parallel-27b.md#limits) are part of the result.

| Weights | 1 stream | 8 streams | Highest aggregate measured | KV cache |
|---|---|---|---|---|
| FP8 | 27 tok/s | 180 tok/s | — | 918 993 tokens |
| INT4 | 59 tok/s | 314 tok/s | 685 tok/s at 64 streams | 1 435 834 tokens |
| INT4 + MTP (2 tokens) | 93–96 tok/s | 316–330 tok/s | 488 tok/s at 64 streams | 1 207 535 tokens |

Two things made this possible and neither is the default: dropping `--enforce-eager`,
and patching vLLM so that each worker sees a single card (otherwise host RAM, not VRAM,
is the limit). Cold prompt reading remains slow, at roughly 700–950 tok/s. The machine
for these runs is the same as below, with vLLM 0.32.0 in place of the 0.21 image.

## Corrections we've published

We got one of our own benchmarks wrong and fixed it in public. The first concurrency
run divided by global wall-clock time, which flattered the fast models. The corrected
figures are in [`benchmarks.md`](benchmarks.md#concurrency) with the original numbers
shown alongside. If you find another mistake, open an issue.

## Licence

Code under [MIT](LICENSE). Documentation and measurement data under
[CC BY 4.0](LICENSE-DATA) — use the numbers, cite the repo.

---

Maintained by [Ninabot Sàrl](https://ninabot.ch), Geneva.
