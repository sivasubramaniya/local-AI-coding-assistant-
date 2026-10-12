import pytest

from app.backend.task_classifier import TaskType, classify


@pytest.mark.parametrize("text, expected", [
    ("Create a Flask app project with login, templates and tests", TaskType.PROJECT),
    ("build a complete project for a todo list", TaskType.PROJECT),
    ("scaffold a FastAPI service", TaskType.PROJECT),
    ("I get this traceback: KeyError 'id'", TaskType.DEBUG),
    ("my loop doesn't work", TaskType.DEBUG),
    ("fix this function", TaskType.DEBUG),
    ("refactor calc.py to use classes", TaskType.REFACTOR),
    ("please clean up this script", TaskType.REFACTOR),
    ("can you review my SQL query", TaskType.REVIEW),
    ("explain how Python decorators work", TaskType.EXPLAIN),
    ("what is a closure in javascript?", TaskType.EXPLAIN),
    ("write a function that reverses a string", TaskType.GENERATE),
    ("is_prime in Python", TaskType.GENERATE),
    ("What is a good recipe for chocolate cake?", TaskType.OFF_TOPIC),
    ("tell me a joke about cats", TaskType.OFF_TOPIC),
])
def test_rules(text, expected):
    assert classify(text) is expected


def test_project_mode_toggle_wins():
    assert classify("explain this", project_mode=True) is TaskType.PROJECT


def test_attachments_make_a_question_about_code():
    assert classify("what does this do?", attachments=["C:/x/app.py"]) is TaskType.EXPLAIN
    assert classify("what does this do?") is TaskType.OFF_TOPIC
