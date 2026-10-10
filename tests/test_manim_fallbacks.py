import ast

from services.example_store import get_relevant_examples, save_successful_example
from services.manim_error_parser import ERROR_FIX_MAP, build_retry_prompt, classify_error
from services.manim_templates import build_guaranteed_manim_code
from services.manim_validator import validate_manim_code


def test_guaranteed_template_is_valid_python_and_passes_validator():
    plan = {
        "title": 'Quotes "and" backslashes \\ test',
        "beats": [
            {"id": 1, "duration_sec": 6.0, "visual": "Intro to derivatives"},
            {"id": 2, "duration_sec": 0, "visual": "Zero-duration beat"},
            {"id": 3, "duration_sec": 8.5, "narration": "x" * 300},
        ],
    }
    code = build_guaranteed_manim_code("Derivatives", plan)
    ast.parse(code)
    errors = [i for i in validate_manim_code(code) if i.severity == "error"]
    assert errors == []
    assert "wait(0)" not in code
    assert "TransformMatchingTex" not in code


def test_guaranteed_template_without_plan():
    code = build_guaranteed_manim_code("Pythagoras")
    ast.parse(code)
    assert "class Scene(Scene)" in code


def test_classify_error_and_fix_map():
    tmt = 'AssertionError\n  assert hasattr(mobject, "tex_string")'
    assert classify_error(tmt) == "TransformMatchingTex"
    assert classify_error("subprocess.TimeoutExpired: timed out") == "timeout"
    assert classify_error("SyntaxError: invalid syntax") == "SyntaxError"
    assert "timeout" in ERROR_FIX_MAP


def test_build_retry_prompt_contains_code_and_fix():
    prompt = build_retry_prompt(
        attempt=2,
        max_attempts=3,
        broken_code="from manim import *\nclass Scene(Scene): pass",
        stderr="SyntaxError: invalid syntax",
        topic="limits",
    )
    assert "Fix attempt 2/3" in prompt
    assert "BROKEN CODE" in prompt
    assert ERROR_FIX_MAP["SyntaxError"] in prompt


def test_example_store_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "examples.jsonl"
    monkeypatch.setenv("MANIM_EXAMPLES_PATH", str(path))
    monkeypatch.delenv("MANIM_SAVE_EXAMPLES", raising=False)
    save_successful_example("derivative of x^2", "CODE_A", attempt=1)
    assert not path.exists()

    monkeypatch.setenv("MANIM_SAVE_EXAMPLES", "1")
    save_successful_example("derivative of x^2", "CODE_A", attempt=1)
    save_successful_example("integral of sin", "CODE_B", attempt=2)
    out = get_relevant_examples("limit of a derivative")
    assert "CODE_A" in out
    assert "CODE_B" not in out
