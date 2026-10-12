"""REAL end-to-end sample: generate a Java Swing calculator with the app's own generator,
compile and run its plain test class with the allowlisted tool runner, and repair failures
with the model (at most 3 rounds). Writes a report labelled REAL.

Usage (from the project folder, with Ollama running and the model installed):
    .\\venv\\Scripts\\python.exe scripts\\run_java_sample.py [--out DIR]
    .\\venv\\Scripts\\python.exe scripts\\run_java_sample.py --repair-demo
        (copies docs/samples/java-calculator, injects a bug into Calculator.add and lets the
         REAL model repair it through the same test -> fix -> re-run loop)

Commands are the same allowlisted ones the app runs; running this script is the approval.
Model output is never executed as a command.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.coding_agent import (  # noqa: E402
    apply_changes,
    build_context,
    list_project_files,
    parse_changes,
    prepare_changes,
    read_project_files,
)
from app.agent.project_generator import ProjectGenerator, ProjectWriter  # noqa: E402
from app.agent.tool_runner import (  # noqa: E402
    ToolRunner,
    ToolUnavailableError,
    default_test_commands,
    results_markdown,
    trimmed_failure_output,
)
from app.backend.chat_service import build_messages  # noqa: E402
from app.backend.ollama_client import OllamaClient  # noqa: E402
from app.config import load_config  # noqa: E402
from app.prompts import load_system_prompt  # noqa: E402
from app.validation.project_validator import validate_project  # noqa: E402

REQUEST = (
    "A small Java desktop calculator. Exactly 4 files: "
    "src/calculator/Calculator.java (package calculator; methods add, subtract, multiply, divide on doubles; "
    "divide throws ArithmeticException on division by zero), "
    "src/calculator/CalculatorApp.java (package calculator; a Swing GUI with two input fields, four operation "
    "buttons and a result label, using Calculator), "
    "src/calculator/CalculatorTest.java (package calculator; a plain test class WITHOUT JUnit: a public static "
    "void main that checks each operation and the division-by-zero exception, prints PASS/FAIL per check and "
    "calls System.exit(1) if any check fails; it must not open any window), "
    "and README.md with build, run and test commands using javac and java. Standard library only."
)
MAX_ROUNDS = 3


def portable(text: str) -> str:
    """Replace the user's own folders with %LOCALAPPDATA% / ~ so reports carry no personal paths."""
    for env, label in (("LOCALAPPDATA", "%LOCALAPPDATA%"), ("USERPROFILE", "~")):
        value = os.environ.get(env)
        if value:
            text = text.replace(value, label)
    return text


def log(lines: list[str], text: str) -> None:
    text = portable(text)
    print(text, flush=True)
    lines.append(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None, help="projects folder (default: config.projects_dir)")
    parser.add_argument("--copy-to", type=Path, default=ROOT / "docs" / "samples" / "java-calculator")
    parser.add_argument("--repair-demo", action="store_true", help="repair an injected bug instead of generating")
    args = parser.parse_args()

    config = load_config()
    system_prompt = load_system_prompt()
    title = "Java repair demo" if args.repair_demo else "Java calculator sample"
    report: list[str] = [f"# {title} — REAL model run", ""]
    started = time.monotonic()
    with OllamaClient(config) as client:
        version = client.ensure_ready()
        log(report, f"- Ollama {version}, model `{config.model_name}` (REAL)")

        def chat(messages: list[dict]) -> str:
            t0 = time.monotonic()
            text = "".join(client.stream_chat(messages))
            stats = client.last_stats
            speed = f"{stats.eval_count} tokens, {stats.tokens_per_second:.1f} tok/s" if stats else "no stats"
            print(f"  model call: {time.monotonic() - t0:.0f} s ({speed})", flush=True)
            return text

        if args.repair_demo:
            source = ROOT / "docs" / "samples" / "java-calculator"
            writer = ProjectWriter(args.out or config.projects_dir, "java-calculator-repair-demo")
            shutil.copytree(source, writer.root, dirs_exist_ok=True)
            target = writer.root / "src" / "calculator" / "Calculator.java"
            original = target.read_text(encoding="utf-8")
            if "a + b" not in original:
                log(report, "- BLOCKED: could not find 'a + b' in Calculator.java to inject the bug.")
                return 1
            target.write_text(original.replace("a + b", "a - b", 1), encoding="utf-8")
            project_name = "java-calculator-repair-demo"
            log(report, f"- Copied the generated sample to `{writer.root}` and injected a bug: "
                        "`a + b` -> `a - b` in Calculator.add (MOCK bug, REAL repair)")
        else:
            generator = ProjectGenerator(chat, system_prompt)
            plan = generator.make_plan(REQUEST)
            log(report, f"- Plan: `{plan.project_name}`, {len(plan.files)} files: "
                        + ", ".join(f"`{f.path}`" for f in plan.files))
            writer = ProjectWriter(args.out or config.projects_dir, plan.project_name)
            result = generator.generate(plan, writer, lambda i, n, p: print(f"[{i}/{n}] {p}", flush=True))
            log(report, f"- Generated into `{writer.root}`: {len(result.written)} written, "
                        f"failed: {result.failed or 'none'}")
            log(report, f"- {validate_project(writer.root, result.written).summary()}")
            project_name = plan.project_name

        runner = ToolRunner(writer.root, timeout_s=120)
        commands = default_test_commands(writer.root)
        if commands is None:
            log(report, "- BLOCKED: no Java sources were generated, nothing to compile.")
            return 1
        log(report, "- Test commands (allowlisted): " + "; ".join(f"`{' '.join(c)}`" for c in commands))
        for round_no in range(MAX_ROUNDS + 1):
            try:
                results = runner.run_sequence(commands)
            except ToolUnavailableError as exc:
                log(report, f"- SKIPPED compile/run: {exc.message} (install Microsoft.OpenJDK.21)")
                break
            ok = all(r.ok for r in results) and len(results) == len(commands)
            label = "initial run" if round_no == 0 else f"after repair round {round_no}"
            log(report, f"\n## Checks {label}: {'PASSED' if ok else 'FAILED'} (REAL javac/java)\n")
            report.append(portable(results_markdown(results, len(commands))))
            if ok or round_no == MAX_ROUNDS:
                break
            budget = 9000
            failure = trimmed_failure_output(results, budget // 3)
            files = read_project_files(writer.root, budget * 2)
            context = f"{failure}\n\n" + build_context(failure, project_name, files, [], budget)
            messages = build_messages([], f"Repair round {round_no + 1}/{MAX_ROUNDS}: the checks failed. "
                                          "Please fix the code.", system_prompt, config.num_ctx)
            messages[-1]["content"] += f"\n\n{context}"
            answer = chat(messages)
            pending, problems = prepare_changes(writer.root, parse_changes(answer, list_project_files(writer.root)))
            log(report, f"- Repair round {round_no + 1}: model proposed {len(pending)} file change(s)"
                        + (f"; unusable: {problems}" if problems else ""))
            if not pending:
                log(report, "- Repair stopped: no usable fix was proposed.")
                break
            for change in pending:
                report.append(f"\n```diff\n{change.diff_text()}```")
            written = apply_changes(writer.root, pending)
            log(report, f"- Applied (with .bak backups): {', '.join(written)}")

    log(report, f"\nTotal time: {(time.monotonic() - started) / 60:.1f} min")
    if args.repair_demo:
        (ROOT / "docs" / "samples" / "java-repair-REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        return 0
    if args.copy_to:
        if args.copy_to.exists():
            shutil.rmtree(args.copy_to)
        shutil.copytree(writer.root, args.copy_to, ignore=shutil.ignore_patterns("out", "*.class", "*.bak-*"))
        (args.copy_to.parent / "java-calculator-REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"Copied the project to {args.copy_to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
