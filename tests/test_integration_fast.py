"""REAL Fast mode (qwen2.5-coder-7b:latest). Run with: python -m pytest -m integration -v

Skips with the reason when Ollama or the 7B model is missing. The 14B-vs-7B speed comparison and
the 7B to-do project run are recorded by scripts (see docs/PERFORMANCE.md and docs/samples/).
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
def fast_client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fast")
    config = load_config({"LAA_DATA_DIR": str(tmp), "LAA_EXPORT_DIR": str(tmp)})
    client = OllamaClient(config, model=config.fast_model_name)
    try:
        client.ensure_ready()
    except ModelNotFoundError:
        client.close()
        pytest.skip(f"fast model {config.fast_model_name} not installed; run: "
                    f"{create_command(config, config.fast_model_name)}")
    except AppError as exc:
        client.close()
        pytest.skip(f"Ollama not available: {exc.message}")
    yield client
    client.close()


def _ask(client, question):
    messages = build_messages([], question, load_system_prompt(), client.config.num_ctx)
    return "".join(client.stream_chat(messages))


def test_fast_is_prime_is_valid_python(fast_client):
    reply = _ask(fast_client, "Write is_prime in Python")
    blocks = FENCE.findall(reply)
    tree = ast.parse(blocks[0] if blocks else reply)
    assert "is_prime" in {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert fast_client.last_stats is not None and fast_client.last_stats.eval_count > 0


def test_fast_off_topic_question_is_redirected(fast_client):
    reply = _ask(fast_client, "What is a good recipe for chocolate cake?")
    lower = reply.lower()
    mentions_coding = any(word in lower for word in CODING_WORDS)
    short_without_recipe = len(reply) < 400 and not any(w in lower for w in ("preheat", "cups of", "bake for"))
    assert mentions_coding or short_without_recipe, f"reply did not redirect: {reply[:300]!r}"
