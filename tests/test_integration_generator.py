"""REAL model: generate a tiny 3-file Python project. Run with: python -m pytest -m integration -v

Skips when Ollama is not running or the exact model is missing. Slow on CPU-only machines.
"""

import ast

import pytest

from app.agent.project_generator import ProjectGenerator, ProjectWriter
from app.backend.ollama_client import OllamaClient
from app.config import load_config
from app.errors import AppError
from app.prompts import load_system_prompt

pytestmark = pytest.mark.integration

REQUEST = (
    "A tiny Python command line tool with exactly 3 files: greet.py with a function greet(name) that returns "
    "'Hello, <name>!', test_greet.py with two pytest tests for it, and README.md. Standard library only."
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("integration-gen")
    config = load_config({"LAA_DATA_DIR": str(tmp), "LAA_EXPORT_DIR": str(tmp), "LAA_STREAM_READ_TIMEOUT_S": "600"})
    c = OllamaClient(config)
    try:
        c.ensure_ready()
    except AppError as exc:
        c.close()
        pytest.skip(f"real model not available: {exc.message}")
    yield c
    c.close()


def test_real_model_generates_small_python_project(client, tmp_path):
    def chat(messages):
        return "".join(client.stream_chat(messages))

    generator = ProjectGenerator(chat, load_system_prompt())
    plan = generator.make_plan(REQUEST)
    assert 1 <= len(plan.files) <= 6
    writer = ProjectWriter(tmp_path / "projects", plan.project_name)
    result = generator.generate(plan, writer)
    assert result.written, f"no files written; failures: {result.failed}"
    python_files = [p for p in result.written if p.endswith(".py")]
    assert python_files, f"no Python files in {result.written}"
    for relative in python_files:
        ast.parse((writer.root / relative).read_text(encoding="utf-8"))  # SyntaxError fails the test
