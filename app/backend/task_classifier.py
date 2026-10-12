"""Rule-based task classification (no model call).

The result picks the flow: PROJECT goes to the project generator; everything else
goes to normal chat (DEBUG/REFACTOR/REVIEW/EXPLAIN add project or attachment context).
OFF_TOPIC is informational only: the request still goes to the model, whose system
prompt redirects it politely.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum


class TaskType(Enum):
    GENERATE = "generate"
    DEBUG = "debug"
    EXPLAIN = "explain"
    REFACTOR = "refactor"
    REVIEW = "review"
    PROJECT = "project"
    OFF_TOPIC = "off_topic"


_PROJECT = [
    r"\b(create|build|generate|make|scaffold|set ?up|start)\b.{0,40}\b(project|app|application|website|"
    r"web ?site|service|api|cli tool|game|program)\b.{0,60}\b(with|including|files?|structure|folders?)\b",
    r"\b(multi[- ]file|full|complete|whole|new)\s+(project|app|application|codebase|repo(sitory)?)\b",
    r"\bscaffold\b",
    r"\bproject (structure|skeleton|template)\b",
]
_DEBUG = [
    r"\btraceback\b", r"\bstack ?trace\b", r"\bexception\b", r"\berror\b", r"\bbug\b", r"\bcrash(es|ed|ing)?\b",
    r"\bfix\b", r"\bdebug\b", r"\b(doesn'?t|does not|won'?t|isn'?t|not) (work|working|compile|run)\b",
    r"\bfail(s|ed|ing)?\b", r"\bbroken\b", r"\bunexpected\b",
]
_REFACTOR = [r"\brefactor", r"\bclean ?up\b", r"\bsimplify\b", r"\brestructure\b", r"\bimprove (the )?(code|readability|performance)\b",
             r"\brename\b", r"\bmake (it|this|the code) (cleaner|faster|more readable)\b", r"\boptimi[sz]e\b"]
_REVIEW = [r"\breview\b", r"\bcode review\b", r"\bfeedback on\b", r"\bany (issues|problems)\b", r"\bis this (code )?(good|correct|ok)\b"]
_EXPLAIN = [r"^\s*(what|why|how|when)\b", r"\bexplain\b", r"\bwhat does\b", r"\bhow does\b", r"\bdifference between\b",
            r"\bmeaning of\b", r"\bwalk me through\b", r"\bunderstand\b"]
_CODING = [
    r"\bcode\b", r"\bfunction\b", r"\bclass\b", r"\bmethod\b", r"\bscript\b", r"\bprogram\b", r"\bapi\b", r"\bsql\b",
    r"\bquery\b", r"\bdatabase\b", r"\balgorithm\b", r"\bcompile", r"\btest", r"\bgit\b", r"\bdocker\b", r"\bregex\b",
    r"\bpython\b", r"\bjava(script)?\b", r"\btypescript\b", r"\bc\+\+|\bc#|\brust\b|\bgolang\b|\bgo\b", r"\bhtml\b",
    r"\bcss\b", r"\breact\b", r"\bnode\b", r"\bpowershell\b", r"\bbash\b", r"\bshell\b", r"\blinux\b", r"\bjson\b",
    r"\bvariable\b", r"\bloop\b", r"\barray\b", r"\blist\b", r"\bdict", r"\bstring\b", r"\bpointer\b", r"\bthread",
    r"\basync\b", r"\bframework\b", r"\blibrary\b", r"\bpackage\b", r"\bpip\b", r"\bnpm\b", r"\bollama\b", r"\bllm\b",
    r"\bimplement", r"\bwrite (a|an|the|me)\b", r"\bendpoint\b", r"\bserver\b", r"\bfrontend\b", r"\bbackend\b",
    r"\bdebug", r"\brefactor", r"\bunit test", r"\bpytest\b", r"\bjunit\b", r"\bmaven\b", r"\bgradle\b",
    r"\.(py|js|ts|java|cs|cpp|go|rs|html|css|sql|json|yaml|yml|toml|md|ps1|sh)\b", r"```", r"\bdef |\bimport |=>|\{|\};",
]


def _matches(patterns: Sequence[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in patterns)


def classify(text: str, project_mode: bool = False, attachments: Sequence[str] = ()) -> TaskType:
    """Classify a request using the Project mode toggle, attachments and keywords."""
    if project_mode:
        return TaskType.PROJECT
    lower = text.lower()
    if _matches(_PROJECT, lower):
        return TaskType.PROJECT
    if _matches(_DEBUG, lower):
        return TaskType.DEBUG
    if _matches(_REFACTOR, lower):
        return TaskType.REFACTOR
    if _matches(_REVIEW, lower):
        return TaskType.REVIEW
    coding = bool(attachments) or _matches(_CODING, lower)
    if _matches(_EXPLAIN, lower):
        return TaskType.EXPLAIN if coding else TaskType.OFF_TOPIC
    return TaskType.GENERATE if coding else TaskType.OFF_TOPIC
