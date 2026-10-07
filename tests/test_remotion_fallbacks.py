from services.example_store import get_relevant_examples, save_successful_example
from services.manim_attempt_models import get_model_for_remotion_attempt
from services.remotion_error_parser import (
    ERROR_FIX_MAP,
    build_remotion_retry_prompt,
    parse_remotion_error,
)
from services.remotion_templates import build_guaranteed_remotion_code
from services.remotion_validator import validate_remotion_code


def test_guaranteed_template_passes_static_validation():
    plan = {
        "title": 'Quote " and backslash \\ test',
        "beats": [
            {"duration_sec": 4, "visual": "Why it's {growing}", "narration": "`tick` ${x}"},
            {"duration_sec": 0, "visual": "Zero beat"},
        ],
    }
    code = build_guaranteed_remotion_code("Market share", plan)
    assert validate_remotion_code(code) == []
    assert "durationInFrames={0}" not in code
    assert '"frames": 120' in code
    assert '"frames": 150' in code


def test_validator_flags_disallowed_imports_and_assets():
    code = (
        "import React from 'react';\n"
        "import {motion} from 'framer-motion';\n"
        "import './style.css';\n"
        "import {Img, staticFile} from 'remotion';\n"
        "export const MainComposition = () => <Img src={staticFile('a.png')} />;\n"
    )
    errors = validate_remotion_code(code)
    assert any("framer-motion" in e for e in errors)
    assert any("style.css" in e for e in errors)
    assert any("External assets" in e for e in errors)
    assert validate_remotion_code("export default () => null;")


def test_parse_remotion_errors():
    cases = {
        "Module not found: Error: Can't resolve 'framer-motion'": "ModuleNotFound",
        "Error: inputRange must be strictly monotonically increasing but got [10,10]": "InterpolateRange",
        "Error: Invalid hook call. Hooks can only be called inside": "Hooks",
        "ReferenceError: Chart is not defined\n at MainComposition.tsx:42": "ReferenceError",
        "TypeError: Cannot read properties of undefined (reading 'value')": "TypeError",
        "Remotion render timed out after 900s": "timeout",
        "The durationInFrames prop must be positive, but got 0": "Duration",
    }
    for stderr, expected in cases.items():
        assert parse_remotion_error(stderr)["type"] == expected, stderr
    assert parse_remotion_error("ReferenceError: x\n MainComposition.tsx:42:7")["line"] == 42


def test_build_remotion_retry_prompt():
    code = "\n".join(f"// line {i}" for i in range(1, 30))
    prompt = build_remotion_retry_prompt(
        attempt=1,
        max_attempts=3,
        broken_code=code,
        stderr="ReferenceError: foo is not defined at MainComposition.tsx:10:3",
        topic="growth",
    )
    assert "Fix attempt 1/3" in prompt
    assert "BROKEN CODE" in prompt
    assert ERROR_FIX_MAP["ReferenceError"] in prompt
    assert "→  10: // line 10" in prompt


def test_remotion_model_rotation(monkeypatch):
    monkeypatch.setenv("MANIM_ATTEMPT_MODELS", "1:manim/model")
    monkeypatch.setenv("REMOTION_ATTEMPT_MODELS", "1:a/one,2:b/two")
    assert get_model_for_remotion_attempt(1, "base") == "a/one"
    assert get_model_for_remotion_attempt(3, "base") == "b/two"
    monkeypatch.delenv("REMOTION_ATTEMPT_MODELS")
    assert get_model_for_remotion_attempt(1, "base") == "base"


def test_remotion_example_store_is_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIM_EXAMPLES_PATH", str(tmp_path / "m.jsonl"))
    monkeypatch.setenv("REMOTION_EXAMPLES_PATH", str(tmp_path / "r.jsonl"))
    monkeypatch.setenv("REMOTION_SAVE_EXAMPLES", "1")
    monkeypatch.delenv("MANIM_SAVE_EXAMPLES", raising=False)
    save_successful_example("revenue chart", "TSX_CODE", attempt=1, engine="remotion")
    save_successful_example("revenue chart", "PY_CODE", attempt=1, engine="manim")
    assert "TSX_CODE" in get_relevant_examples("market data", engine="remotion")
    assert get_relevant_examples("market data", engine="manim") == ""
