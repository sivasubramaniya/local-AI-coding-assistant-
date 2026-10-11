"""Tests against the REAL local model. Run with: python -m pytest -m integration -v

They skip (with the reason) when Ollama is not running or the exact model is missing.
"""

import ast
import re

import pytest

from app.backend.chat_service import build_messages
from app.backend.ollama_client import OllamaClient, create_command
from app.config import load_config
from app.errors import AppError, ModelNotFoundError
from app.prompts import load_system_prompt

pytestmark = pytest.mark.integration

FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)
CODING_WORDS = ("coding", "code", "programming", "software", "developer", "development")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("integration")
    config = load_config({"LAA_DATA_DIR": str(tmp), "LAA_EXPORT_DIR": str(tmp)})
    c = OllamaClient(config)
    try:
        c.ensure_ready()
    except ModelNotFoundError:
        c.close()
        pytest.skip(f"model {config.model_name} not installed; run from the project folder: {create_command(config)}")
    except AppError as exc:
        c.close()
        pytest.skip(f"Ollama not available: {exc.message}")
    yield c
    c.close()


def _ask(client, question: str) -> str:
    messages = build_messages([], question, load_system_prompt(), client.config.num_ctx)
    return "".join(client.stream_chat(messages))


def test_ensure_ready(client):
    assert client.ensure_ready()
    assert client.has_model()


def test_is_prime_is_valid_python(client):
    reply = _ask(client, "Write is_prime in Python")
    blocks = FENCE.findall(reply)
    code = blocks[0] if blocks else reply
    tree = ast.parse(code)  # raises SyntaxError if the code is not valid Python
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "is_prime" in names
    assert client.last_stats is not None and client.last_stats.eval_count > 0


def test_off_topic_question_is_redirected(client):
    reply = _ask(client, "What is a good recipe for chocolate cake?")
    lower = reply.lower()
    mentions_coding = any(word in lower for word in CODING_WORDS)
    short_without_recipe = len(reply) < 400 and not any(w in lower for w in ("preheat", "cups of", "bake for"))
    assert mentions_coding or short_without_recipe, f"reply did not redirect: {reply[:300]!r}"
