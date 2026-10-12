# Performance — Local AI Assistant (REAL measurements, 2026-10-12)

## Machine

| Item | Value |
|---|---|
| CPU | AMD Ryzen 5 7235HS |
| RAM | 23.7 GB |
| GPU | NVIDIA GeForce RTX 3050 A Laptop GPU, **4 GB VRAM** (driver 610.62) |
| Ollama | 0.40.2 |
| Model | `qwen2.5-coder-14b:latest` (9 GB, Q4) — about 10 GB loaded |
| Split (`ollama ps`) | **79% CPU / 21% GPU** at num_ctx 8192 (77/23 at 4096) |

The 14B model does not fit in 4 GB of VRAM, so most layers run on the CPU. That sets the
speed ceiling at roughly 3–4 tokens per second on this laptop.

## Method

`scripts/benchmark.py` sends the app's real request (system prompt + "Write is_prime in Python",
506 prompt tokens, ~220 answer tokens) through the app's own `OllamaClient`, 3 runs per setting.
`--cold` unloads the model first, so run 1 includes the model load. Raw rows: `docs/perf/benchmark.jsonl`.
num_ctx was varied with the per-request `num_ctx` option, which the app sends on every request and
which overrides the Modelfile, so the Modelfile was not edited for the trial.
Ollama restarts used `scripts/restart_ollama.ps1`, which also stops `llama-server` runners.

## Results (tokens/s = generation speed; wall = full answer)

| Setting | Runs (tok/s) | Avg tok/s | Cold load | Avg wall | CPU/GPU | Notes |
|---|---|---|---|---|---|---|
| Baseline, num_ctx 8192 | 3.36, 3.44, 3.48 | 3.43 | 11.7 s | 120.1 s | 79/21 | one run had a 123 s prompt-eval stall |
| num_ctx 4096 | 3.80, 3.53, 3.38 | 3.57 | 14.1 s | 69.1 s | 77/23 | |
| Flash attention + q8_0 KV, 8192 | 3.63, 3.03, 2.74 | 3.13 | 36.7 s | 86.1 s | 82/18 | **invalid**: an orphaned runner held VRAM |
| Flash attention + q8_0 KV, 4096 | 2.71, 2.62, 2.61 | 2.65 | 18.3 s | 106.3 s | 77/23 | invalid (same orphan) |
| *orphans removed:* baseline 8192 | 2.95, 2.81, 2.97 | 2.91 | 16.1 s | 83.3 s | 79/21 | machine busier than at the start |
| num_ctx 4096 | 0.70, 3.13, 3.53 | 2.45 | 12.2 s | 167.0 s | 77/23 | run 1 hit heavy contention |
| Flash attention + q8_0 KV, 8192 | 3.71, 3.71, 3.62 | 3.68 | 13.6 s | 66.5 s | 77/23 | clean restart |
| Baseline 8192 (right after, interleaved) | 3.67, 3.47, 3.55 | 3.56 | 16.3 s | 69.4 s | 79/21 | clean restart, no flash attention |

## Decision

| Setting | Kept? | Why |
|---|---|---|
| num_ctx 4096 | **No (stay at 8192)** | No reliable gain (3.57 vs 3.43, then 2.45 vs 2.91 — within run-to-run noise), and 4096 tokens is too small for project generation: file prompts include up to ~12,000 characters of earlier files plus a 1,024-token reply reserve. |
| `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` | **No (variables removed)** | Interleaved clean runs: 3.68 vs 3.56 tok/s (+3%), inside the noise of other runs on this machine; not "faster" by a margin we can trust. |

**Before / after:** about 3.4–3.6 tok/s before and after; no configuration change was kept. The
Modelfile and config are unchanged (temperature 0.2, top_p 0.8, num_ctx 8192), so no test changes
were needed. One real improvement came out of this work: `scripts/restart_ollama.ps1` restarts Ollama
without leaving orphaned `llama-server` processes. Those orphans held VRAM, which pushed the model to
99% CPU and caused a "unable to allocate CUDA_Host buffer" load failure.

## What would actually help on this machine

- Close GPU/RAM-heavy apps while generating (browsers, other AI apps). Measurements varied by more than
  any setting did, mostly from background load (another `ollama launch` session was running at one point).
- A smaller model would fit more of the GPU, but the project requires `qwen2.5-coder-14b:latest`, so this
  was not tried.
- Keep answers and projects small; generation time scales with output length (~0.3 s per token).
