"""REAL performance benchmark: the is_prime prompt N times through the app's own client.

Usage:
    .\\venv\\Scripts\\python.exe scripts\\benchmark.py --label baseline [--runs 3] [--num-ctx 8192] [--cold]

--cold unloads the model first (`ollama stop`) so run 1 includes the load time.
Appends one JSON line per run to docs/perf/benchmark.jsonl and prints a summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.backend.chat_service import build_messages  # noqa: E402
from app.backend.ollama_client import OllamaClient  # noqa: E402
from app.config import load_config  # noqa: E402
from app.prompts import load_system_prompt  # noqa: E402

PROMPT = "Write is_prime in Python"


def ollama_ps() -> str:
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30).stdout
    except OSError:
        return "ollama ps unavailable"
    lines = [line for line in out.splitlines() if line.strip()]
    return lines[-1] if len(lines) > 1 else "(no model loaded)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--cold", action="store_true")
    parser.add_argument("--model", choices=("quality", "fast"), default="quality",
                        help="quality = qwen2.5-coder-14b (default), fast = qwen2.5-coder-7b")
    args = parser.parse_args()

    config = load_config()
    if args.num_ctx:
        config = replace(config, num_ctx=args.num_ctx)
    config = replace(config, stream_read_timeout_s=900)
    model = config.fast_model_name if args.model == "fast" else config.model_name
    if args.cold:
        for name in (config.model_name, config.fast_model_name):  # nothing else loaded: fair comparison
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=60)
        for _ in range(60):  # wait until the model is really unloaded
            if ollama_ps() == "(no model loaded)":
                break
            time.sleep(2)
    out_file = ROOT / "docs" / "perf" / "benchmark.jsonl"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    messages = build_messages([], PROMPT, load_system_prompt(), config.num_ctx)
    rows = []
    with OllamaClient(config, model=model) as client:
        client.ensure_ready()
        for run in range(1, args.runs + 1):
            started = time.monotonic()
            text = "".join(client.stream_chat(messages))
            wall = time.monotonic() - started
            s = client.last_stats
            row = {
                "label": args.label, "model": model, "run": run, "num_ctx": config.num_ctx,
                "load_s": round(s.load_duration_ns / 1e9, 2), "prompt_tokens": s.prompt_eval_count,
                "eval_tokens": s.eval_count, "tok_s": round(s.tokens_per_second, 2),
                "prompt_s": round((s.total_duration_ns - s.load_duration_ns - s.eval_duration_ns) / 1e9, 2),
                "total_s": round(s.total_duration_ns / 1e9, 2), "wall_s": round(wall, 2),
                "answer_chars": len(text), "ollama_ps": ollama_ps(),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    avg = sum(r["tok_s"] for r in rows) / len(rows)
    print(f"SUMMARY {args.label}: avg {avg:.2f} tok/s, first-run load {rows[0]['load_s']} s, "
          f"avg wall {sum(r['wall_s'] for r in rows) / len(rows):.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
