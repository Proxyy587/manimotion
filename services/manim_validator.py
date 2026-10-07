"""Static checks for LLM Manim code before render."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    message: str
    line: int | None = None
    fix: str | None = None


def validate_manim_code(code: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    lines = code.split("\n")

    if "from manim import *" not in code:
        issues.append(
            ValidationIssue(
                severity="error",
                message="Missing 'from manim import *'",
                fix="Add 'from manim import *' as first line",
            )
        )

    if "class Scene(" not in code:
        issues.append(
            ValidationIssue(
                severity="error",
                message="Scene class not found or wrongly named",
                fix="Ensure 'class Scene(Scene):' exists",
            )
        )

    for m in re.finditer(r"^import\s+(\w+)", code, re.MULTILINE):
        name = m.group(1)
        if name not in {"numpy", "np"}:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"External import '{name}' not allowed (only manim + numpy)",
                    fix=f"Remove 'import {name}'",
                )
            )
    for m in re.finditer(r"^from\s+([\w.]+)\s+import", code, re.MULTILINE):
        mod = m.group(1)
        if mod not in {"manim", "numpy"} and not mod.startswith("manim."):
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"External import from '{mod}' not allowed",
                    fix=f"Remove 'from {mod} import ...'",
                )
            )

    text_names = ("title", "text", "label", "header", "caption", "subtitle")
    for i, line in enumerate(lines, start=1):
        if "TransformMatchingTex" not in line:
            continue
        m = re.search(r"TransformMatchingTex\s*\(\s*(\w+)\s*,\s*(\w+)", line)
        if not m:
            continue
        src, tgt = m.group(1), m.group(2)
        if any(n in src.lower() or n in tgt.lower() for n in text_names):
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=(
                        f"Line {i}: TransformMatchingTex on likely-Text "
                        f"'{src}' / '{tgt}'"
                    ),
                    line=i,
                    fix=f"Replace with ReplacementTransform({src}, {tgt})",
                )
            )

    for i, line in enumerate(lines, start=1):
        if "get_parts_by_tex" in line or "get_part_by_tex" in line:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"Line {i}: get_part(s)_by_tex is banned (crashes)",
                    line=i,
                    fix="Highlight whole MathTex with SurroundingRectangle",
                )
            )
        # self.wait(0) or self.wait(0.0) — NOT self.wait(0.5)
        if re.search(r"self\.wait\(\s*0(?:\.0+)?\s*\)", line):
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"Line {i}: self.wait(0) is invalid in Manim",
                    line=i,
                    fix="Delete the wait line or use wait(0.1+)",
                )
            )
        # run_time=0 or run_time=0.0 — must NOT match run_time=0.5, run_time=0.1, etc.
        # Correct pattern: value is zero (integer or trailing zeros only, no non-zero digits after dot)
        if re.search(r"run_time\s*=\s*(?:[-+]\s*)?0(?:\.0+)?(?![.0-9])", line):
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"Line {i}: run_time=0 is invalid",
                    line=i,
                    fix="Use run_time=0.5 or greater",
                )
            )
        if re.search(r"(?:MathTex|Tex)\s*\(\s*f['\"]", line):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=f"Line {i}: f-string MathTex may break with backslashes",
                    line=i,
                    fix="Use concatenation: MathTex(r'\\frac{' + str(v) + '}')",
                )
            )

    if re.search(r"\bGraphScene\b|self\.setup_axes\s*\(", code):
        issues.append(
            ValidationIssue(
                severity="error",
                message="GraphScene / self.setup_axes() do not exist in Manim CE",
                fix="Use class Scene(Scene) with axes = Axes(...) and axes.plot(...)",
            )
        )
    for i, line in enumerate(lines, start=1):
        m = re.search(
            r"\.(get_graph|get_derivative_graph|get_parametric_curve|get_implicit_curve)\s*\(|"
            r"\b(ShowCreation|TextMobject|TexMobject|FadeInFrom|FadeOutAndShift)\s*\(",
            line,
        )
        if m:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"Line {i}: '{m.group(1) or m.group(2)}' is not Manim CE API",
                    line=i,
                    fix="Use axes.plot / Create / MathTex / Text / FadeIn(mob, shift=DIR)",
                )
            )

    for axes_call in re.findall(r"Axes\s*\([^)]*\)", code):
        if "x_length" not in axes_call:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message="Axes() missing x_length — may overflow",
                    fix="Add x_length=5.5, y_length=4.5",
                )
            )

    for i, line in enumerate(lines, start=1):
        if "get_riemann_rectangles" in line and "input_sample_type" not in line:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"Line {i}: get_riemann_rectangles() missing "
                        'input_sample_type="right" — may raise ValueError'
                    ),
                    line=i,
                    fix='Add input_sample_type="right" to the call',
                )
            )

    try:
        ast.parse(code)
    except SyntaxError as e:
        issues.append(
            ValidationIssue(
                severity="error",
                message=f"Python syntax error at line {e.lineno}: {e.msg}",
                line=e.lineno,
                fix="Fix Python syntax",
            )
        )

    return issues


def format_validation_errors(issues: list[ValidationIssue]) -> str:
    errors = [i for i in issues if i.severity == "error"]
    if not errors:
        return ""
    parts = []
    for e in errors:
        parts.append(f"- {e.message}")
        if e.fix:
            parts.append(f"  Fix: {e.fix}")
    return "\n".join(parts)
