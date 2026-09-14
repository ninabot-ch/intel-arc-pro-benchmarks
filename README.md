# Intel Arc Pro — inference benchmarks and failure modes

Measurements from a **4× Intel Arc Pro B60 24 GB** machine running three resident
LLMs at once, plus a catalogue of the failure modes we hit getting there.

We run this hardware in production, so the numbers are from a working setup rather
than a test bench — and the failure modes are the ones that actually cost us days.

> **Status:** B60 data only. B70 and Arc Pro B60 Dual measurements will be added to
> this repo when we have the cards.

## What's here

| File | Contents |
|---|---|
| [`benchmarks.md`](benchmarks.md) | Throughput per model, concurrency, VRAM and host RAM pressure, power |
| [`failure-modes.md`](failure-modes.md) | Exact error strings and what caused them — the part that isn't documented anywhere else |
| [`hardware-notes.md`](hardware-notes.md) | Which motherboards physically take 4 double-width cards, measured from vendor drawings |
| [`methodology.md`](methodology.md) | How the numbers were produced, so they can be compared |
| [`scripts/`](scripts/) | The benchmark script |

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

**119 tok/s aggregate** across all three under 12 concurrent requests, 211 W peak for
the four cards. Full detail and caveats in [`benchmarks.md`](benchmarks.md).

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
