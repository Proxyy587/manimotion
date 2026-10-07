"""Parse Manim stderr into actionable retry hints for the LLM."""

from __future__ import annotations

import re
from typing import Any

ERROR_FIX_MAP: dict[str, str] = {
    "TransformMatchingTex": (
        "Replace ALL TransformMatchingTex() with ReplacementTransform(). "
        "TransformMatchingTex ONLY works between two MathTex objects — never Text, VGroup, or mixed."
    ),
    "AssertionError": (
        "An object passed to TransformMatchingTex is not a MathTex. "
        "Replace TransformMatchingTex with ReplacementTransform everywhere in this script."
    ),
    "get_parts_by_tex": (
        "Remove get_part_by_tex / get_parts_by_tex. "
        "Highlight whole MathTex with SurroundingRectangle only."
    ),
    "TexPart": (
        "Remove get_part_by_tex / get_parts_by_tex. "
        "Highlight whole MathTex with SurroundingRectangle only."
    ),
    "SyntaxError": (
        "Fix the Python syntax error on the line indicated. "
        "If using f-strings inside MathTex with backslashes, use string concatenation instead."
    ),
    "AttributeError": (
        "Check the exact attribute name in the error. "
        "Common fixes: coords_to_point → c2p, point_to_coords → p2c."
    ),
    "timeout": (
        "Reduce complexity: fewer run_time values, remove 3D content, "
        "simplify updaters, reduce Riemann rectangle count."
    ),
    "DeprecatedAPI": (
        "You used an old ManimGL method. In Manim CE: axes.get_graph → axes.plot, "
        "get_derivative_graph → plot_derivative_graph, get_parametric_curve → "
        "plot_parametric_curve, ShowCreation → Create, TexMobject → MathTex, "
        "TextMobject → Text, FadeInFrom(m, DIR) → FadeIn(m, shift=DIR). No GraphScene."
    ),
    "ZeroDuration": (
        "Delete every self.wait(0). All run_time values must be > 0 (minimum 0.5)."
    ),
}


_OLD_CLASS_NAMES = {
    "ShowCreation",
    "TextMobject",
    "TexMobject",
    "GraphScene",
    "FadeInFrom",
    "FadeInFromDown",
    "FadeOutAndShift",
    "ShowCreationThenDestruction",
    "CircleIndicate",
    "WiggleOutThenIn",
    "ParametricSurface",
}


def classify_error(stderr: str) -> str:
    """Lightweight classifier for retry routing (mirrors parse_manim_error types)."""
    return parse_manim_error(stderr or "").get("type", "unknown")


def parse_manim_error(stderr: str) -> dict[str, Any]:
    text = stderr or ""
    result: dict[str, Any] = {
        "type": "unknown",
        "message": "",
        "line": None,
        "fix_hint": "",
        "full_error": text[-2000:],
        "force_safe_tmt": False,
    }

    line_match = re.search(r'File ".*?\.py", line (\d+)', text)
    if line_match:
        result["line"] = int(line_match.group(1))

    if (
        'assert hasattr(mobject, "tex_string")' in text
        or ("TransformMatchingTex" in text and "AssertionError" in text)
        or ("tex_string" in text and "AssertionError" in text)
    ):
        result.update(
            {
                "type": "TransformMatchingTex",
                "message": "TransformMatchingTex used on non-MathTex object",
                "fix_hint": (
                    "Replace EVERY TransformMatchingTex(...) with "
                    "ReplacementTransform(...). TransformMatchingTex ONLY works "
                    "between MathTex/Tex objects — never Text, VGroup, or mixed."
                ),
                "force_safe_tmt": True,
            }
        )
        return result

    if "duration of 0" in text or "run_time of 0" in text or "<= 0 seconds" in text:
        result.update(
            {
                "type": "ZeroDuration",
                "message": "wait/run_time <= 0 is invalid",
                "fix_hint": (
                    "Delete every self.wait(0)/wait(0.0). All run_time values must be > 0 "
                    "(minimum 0.5). Skip a wait instead of writing wait(0)."
                ),
            }
        )
        return result

    attr_match = re.search(
        r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
        text,
    )
    if attr_match:
        obj_type, attr = attr_match.group(1), attr_match.group(2)
        result.update(
            {
                "type": "AttributeError",
                "message": f"'{obj_type}' has no attribute '{attr}'",
                "fix_hint": _attribute_hint(obj_type, attr),
            }
        )
        return result

    name_match = re.search(r"NameError: name '(\w+)' is not defined", text)
    if name_match:
        name = name_match.group(1)
        result.update(
            {
                "type": "NameError",
                "message": f"'{name}' is not defined",
                "fix_hint": (
                    ERROR_FIX_MAP["DeprecatedAPI"]
                    if name in _OLD_CLASS_NAMES
                    else (
                        f"'{name}' is undefined. Keep `from manim import *` and fix the name. "
                        "Do not invent APIs."
                    )
                ),
            }
        )
        return result

    if "get_part_by_tex" in text or "get_parts_by_tex" in text or "NoneType" in text:
        result.update(
            {
                "type": "TexPart",
                "message": "Likely get_part_by_tex / NoneType next_to crash",
                "fix_hint": (
                    "Remove ALL get_part_by_tex / get_parts_by_tex. "
                    "Highlight whole MathTex with SurroundingRectangle only."
                ),
            }
        )
        return result

    if "__getattr__.<locals>.getter()" in text:
        old = re.search(
            r"\.(get_graph|get_derivative_graph|get_antiderivative_graph|"
            r"get_parametric_curve|get_implicit_curve|get_line_graph|get_polar_graph)\s*\(",
            text,
        )
        name = old.group(1) if old else "get_*"
        result.update(
            {
                "type": "DeprecatedAPI",
                "message": f"'{name}' is not a Manim CE method (old ManimGL API)",
                "fix_hint": ERROR_FIX_MAP["DeprecatedAPI"],
            }
        )
        return result

    type_match = re.search(r"TypeError: (.+?)(?:\n|$)", text)
    if type_match:
        result.update(
            {
                "type": "TypeError",
                "message": type_match.group(1)[:300],
                "fix_hint": "Check argument types (floats vs lists vs Mobjects).",
            }
        )
        return result

    if "Invalid input sample type" in text or (
        "get_riemann_rectangles" in text and "ValueError" in text
    ):
        result.update(
            {
                "type": "ValueError",
                "message": "Invalid input_sample_type in get_riemann_rectangles",
                "fix_hint": (
                    'Add input_sample_type="right" to EVERY get_riemann_rectangles() call. '
                    "Example: axes.get_riemann_rectangles(graph, x_range=[0, 2], dx=0.25, "
                    'input_sample_type="right"). Also verify the x_range values are within '
                    "the Axes x_range bounds."
                ),
            }
        )
        return result

    val_match = re.search(r"ValueError: (.+?)(?:\n|$)", text)
    if val_match:
        result.update(
            {
                "type": "ValueError",
                "message": val_match.group(1)[:300],
                "fix_hint": "Check numeric ranges (Axes x_range/y_range, wait/run_time > 0).",
            }
        )
        return result

    syn_match = re.search(r"SyntaxError: (.+?)(?:\n|$)", text)
    if syn_match:
        result.update(
            {
                "type": "SyntaxError",
                "message": syn_match.group(1)[:300],
                "fix_hint": ERROR_FIX_MAP["SyntaxError"],
            }
        )
        return result

    if "TimeoutExpired" in text or "timed out" in text.lower():
        result.update(
            {
                "type": "timeout",
                "message": "Render or subprocess timed out",
                "fix_hint": ERROR_FIX_MAP["timeout"],
            }
        )
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        result["message"] = lines[-1][:400]
    return result


def _attribute_hint(obj_type: str, attr: str) -> str:
    hints = {
        (
            "MathTex",
            "text",
        ): "MathTex has no .text — use .tex_string or don't read text",
        (
            "Text",
            "tex_string",
        ): "Text has no .tex_string — use ReplacementTransform for Text",
        ("Axes", "coords_to_point"): "Use axes.c2p(...) not .coords_to_point()",
        ("Axes", "point_to_coords"): "Use axes.p2c(...) not .point_to_coords()",
    }
    return hints.get(
        (obj_type, attr),
        f"'{obj_type}' has no '{attr}'. Use Manim CE APIs only.",
    )


def build_retry_prompt(
    *,
    attempt: int,
    max_attempts: int,
    broken_code: str,
    stderr: str,
    topic: str = "",
) -> str:
    """Structured retry header for the user message."""
    info = parse_manim_error(stderr)
    err_type = info.get("type", "unknown")
    fix = info.get("fix_hint") or ERROR_FIX_MAP.get(err_type, "Fix the error shown below")
    tail = (stderr or "")[-800:]
    code_trim = broken_code if len(broken_code) < 8000 else broken_code[:8000] + "\n# ..."
    return f"""MANIM CODE FAILED. Fix attempt {attempt}/{max_attempts}.
TOPIC: {topic}

SPECIFIC ERROR ({err_type}):
{tail}

REQUIRED FIX:
{fix}

BROKEN CODE (return the COMPLETE fixed script; change only what caused the error):
{code_trim}

Rules:
- Class must be: class Scene(Scene):
- Fix ONLY what caused this error; do not rewrite working sections."""


def format_error_for_llm(
    error_info: dict[str, Any], previous_code: str | None = None
) -> str:
    """Compact, actionable error block for generate_manim_code retries."""
    err_type = error_info.get("type", "unknown")
    fix = error_info.get("fix_hint") or ERROR_FIX_MAP.get(err_type, "")
    parts = [
        f"ERROR TYPE: {err_type}",
        f"ERROR: {error_info.get('message', '')}",
        f"FIX REQUIRED: {fix}",
    ]
    if error_info.get("line"):
        parts.append(f"Approx line: {error_info['line']}")
        if previous_code:
            parts.append(
                "CONTEXT:\n" + _section(previous_code, int(error_info["line"]))
            )
    # Keep traceback short
    full = (error_info.get("full_error") or "")[-1200:]
    if full:
        parts.append(f"TRACE (tail):\n{full}")
    return "\n".join(parts)


def _section(code: str, line_num: int, context: int = 8) -> str:
    lines = code.split("\n")
    start = max(0, line_num - context - 1)
    end = min(len(lines), line_num + context)
    out = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        mark = "→ " if i == line_num else "  "
        out.append(f"{mark}{i:3d}: {line}")
    return "\n".join(out)
