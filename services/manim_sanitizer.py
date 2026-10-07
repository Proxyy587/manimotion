"""Deterministic fixes for LLM-generated Manim CE code (pre-render)."""

from __future__ import annotations

import re


def _strip_method_calls(code: str, method: str) -> str:
    needle = f".{method}("
    out: list[str] = []
    i = 0
    while True:
        idx = code.find(needle, i)
        if idx < 0:
            out.append(code[i:])
            break
        start = idx
        while start > 0 and (code[start - 1].isalnum() or code[start - 1] == "_"):
            start -= 1
        out.append(code[i:start])
        out.append(code[start:idx])
        pos = idx + len(needle)
        depth = 1
        while pos < len(code) and depth:
            ch = code[pos]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            pos += 1
        if code[pos : pos + 3] == "[0]":
            pos += 3
        elif code[pos : pos + 5] == "[ 0 ]":
            pos += 5
        i = pos
    return "".join(out)


# Pre-compiled patterns for timing fixes (module-level avoids recompile + closure bugs)
_WAIT_FULL_LINE = re.compile(
    r"^([ \t]*)self\.wait\(\s*([-+]?[0-9]*\.?[0-9]+)\s*\)([ \t]*#.*)?\s*$"
)
_WAIT_INLINE = re.compile(r"self\.wait\(\s*([-+]?[0-9]*\.?[0-9]+)\s*\)")
# Match run_time= followed by a number; use lookahead to reject anything followed by
# more digits or a decimal point (so run_time=0.5 is NOT matched as "0").
_RUN_TIME = re.compile(r"run_time\s*=\s*([-+]?[0-9]*\.?[0-9]+)")


def _as_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def _clamp_wait_inline(mm: re.Match[str]) -> str:
    val = _as_float(mm.group(1))
    if val is not None and val <= 0:
        return "self.wait(0.1)"
    if val is not None and 0 < val < 0.05:
        return "self.wait(0.1)"
    return mm.group(0)


def _clamp_run_time(mm: re.Match[str]) -> str:
    val = _as_float(mm.group(1))
    if val is not None and val <= 0:
        return "run_time=0.5"
    return mm.group(0)


def _fix_nonpositive_timings(code: str, fixes: list[str]) -> str:
    out_lines: list[str] = []
    dropped_waits = 0
    clamped_waits = 0
    clamped_runtimes = 0

    for line in code.splitlines(True):
        stripped = line.rstrip("\n")
        # Handle standalone self.wait(N) lines — drop if N<=0, clamp if tiny
        m = _WAIT_FULL_LINE.match(stripped)
        if m:
            val = _as_float(m.group(2))
            if val is not None and val <= 0:
                dropped_waits += 1
                continue  # drop the line entirely
            if val is not None and val < 0.05:
                comment = m.group(3) or ""
                out_lines.append(f"{m.group(1)}self.wait(0.1){comment}\n")
                clamped_waits += 1
                continue

        # Fix inline self.wait() calls within self.play(...) or similar
        new_line = _WAIT_INLINE.sub(_clamp_wait_inline, line)
        if new_line != line:
            clamped_waits += 1
        line = new_line

        # Fix run_time= — operates on the full number token so 0.5 is never mangled
        new_line = _RUN_TIME.sub(_clamp_run_time, line)
        if new_line != line:
            clamped_runtimes += 1
        line = new_line

        out_lines.append(line if line.endswith("\n") or line == "" else line + "\n")

    if dropped_waits:
        fixes.append(f"Removed {dropped_waits} self.wait(≤0) call(s)")
    if clamped_waits:
        fixes.append(f"Clamped {clamped_waits} self.wait() value(s) to 0.1+")
    if clamped_runtimes:
        fixes.append(f"Clamped {clamped_runtimes} run_time=0/negative to run_time=0.5")

    result = "".join(out_lines)
    if code and not code.endswith("\n") and result.endswith("\n"):
        result = result[:-1]
    return result


def fix_transform_matching_tex(code: str, fixes: list[str]) -> str:
    """
    TransformMatchingTex ONLY works between MathTex/Tex with .tex_string.
    Anything else → ReplacementTransform (always safe).
    """
    lines = code.split("\n")
    var_types: dict[str, str] = {}
    mathtex_re = re.compile(r"(\w+)\s*=\s*(MathTex|Tex)\s*\(")
    text_re = re.compile(r"(\w+)\s*=\s*(Text|Title|Paragraph|MarkupText)\s*\(")
    vgroup_re = re.compile(r"(\w+)\s*=\s*(VGroup|Group|HGroup)\s*\(")

    for line in lines:
        for m in mathtex_re.finditer(line):
            var_types[m.group(1)] = "mathtex"
        for m in text_re.finditer(line):
            var_types[m.group(1)] = "text"
        for m in vgroup_re.finditer(line):
            var_types[m.group(1)] = "vgroup"

    tmt_re = re.compile(r"TransformMatchingTex\s*\(\s*(\w+)\s*,\s*(\w+)")
    changed = False
    new_lines: list[str] = []

    for line in lines:
        new_line = line
        for m in list(tmt_re.finditer(line)):
            src, tgt = m.group(1), m.group(2)
            src_t = var_types.get(src, "unknown")
            tgt_t = var_types.get(tgt, "unknown")
            if src_t == "mathtex" and tgt_t == "mathtex":
                continue
            new_line = re.sub(
                rf"TransformMatchingTex\s*\(\s*{re.escape(src)}\s*,\s*{re.escape(tgt)}",
                f"ReplacementTransform({src}, {tgt}",
                new_line,
                count=1,
            )
            changed = True
        new_lines.append(new_line)

    if changed:
        fixes.append(
            "Replaced TransformMatchingTex with ReplacementTransform "
            "where operands were not both MathTex"
        )
    return "\n".join(new_lines)


def force_safe_transforms(code: str, fixes: list[str]) -> str:
    """Nuclear option after a TransformMatchingTex crash — replace ALL."""
    if "TransformMatchingTex" not in code:
        return code
    code2 = re.sub(r"\bTransformMatchingTex\b", "ReplacementTransform", code)
    if code2 != code:
        fixes.append("Replaced ALL TransformMatchingTex → ReplacementTransform")
    return code2


def fix_axes_sizing(code: str, fixes: list[str]) -> str:
    """Add x_length/y_length to Axes(...) missing them (best-effort, single-line)."""

    def repl(m: re.Match[str]) -> str:
        body = m.group(1)
        if "x_length" in body or "y_length" in body:
            return m.group(0)
        # Avoid breaking multi-line Axes with nested parens — only simple calls
        if body.count("(") != body.count(")"):
            return m.group(0)
        fixes.append("Added x_length/y_length to Axes()")
        trimmed = body.rstrip()
        if trimmed.endswith(","):
            return f"Axes({trimmed} x_length=5.5, y_length=4.5)"
        return f"Axes({trimmed}, x_length=5.5, y_length=4.5)"

    # Single-line Axes only (safer than greedy DOTALL)
    return re.sub(r"Axes\s*\(([^()\n]*)\)", repl, code)


def fix_overflow_coordinates(code: str, fixes: list[str]) -> str:
    def clamp(
        pattern: str,
        limit: float,
        axis: str,
        replacement: float,
        fixes: list[str],
    ) -> None:
        nonlocal code

        def _sub(m: re.Match[str]) -> str:
            try:
                val = float(m.group(1))
            except ValueError:
                return m.group(0)
            if val > limit:
                fixes.append(f"Clamped {axis}*{val} → {axis}*{replacement}")
                return f"{axis} * {replacement}"
            return m.group(0)

        code = re.sub(pattern, _sub, code)

    clamp(r"UP\s*\*\s*(\d+\.?\d*)", 3.2, "UP", 3.0, fixes)
    clamp(r"DOWN\s*\*\s*(\d+\.?\d*)", 3.2, "DOWN", 3.0, fixes)
    clamp(r"RIGHT\s*\*\s*(\d+\.?\d*)", 6.0, "RIGHT", 5.5, fixes)
    clamp(r"LEFT\s*\*\s*(\d+\.?\d*)", 6.0, "LEFT", 5.5, fixes)
    return code


def fix_scene_class_name(code: str, fixes: list[str]) -> str:
    before = code
    for bad in ("MainScene", "MyScene", "Animation", "ManimScene", "VideoScene"):
        code = re.sub(rf"class\s+{bad}\s*\(", "class Scene(", code)
    if "class Scene(" not in code:
        # Last resort: rename first Scene subclass
        code2, n = re.subn(
            r"class\s+\w+\s*\(\s*(Scene|ThreeDScene)\s*\)",
            "class Scene(Scene)",
            code,
            count=1,
        )
        if n:
            code = code2
            fixes.append("Renamed scene class to Scene(Scene)")
    elif before != code:
        fixes.append("Normalized scene class name to Scene")
    # Force 2D Scene base (ThreeDScene breaks most 2D content)
    if re.search(r"class\s+Scene\s*\(\s*ThreeDScene\s*\)", code):
        code = re.sub(
            r"class\s+Scene\s*\(\s*ThreeDScene\s*\)",
            "class Scene(Scene)",
            code,
        )
        fixes.append("Changed ThreeDScene base → Scene")
    return code


def fix_get_parts_indexing(code: str, fixes: list[str]) -> str:
    new = re.sub(
        r"\.get_parts_by_tex\((.*?)\)\s*\[\s*0\s*\]",
        r".get_part_by_tex(\1)",
        code,
    )
    # Still strip both APIs entirely — they crash downstream with next_to
    stripped = _strip_method_calls(new, "get_parts_by_tex")
    stripped = _strip_method_calls(stripped, "get_part_by_tex")
    if stripped != code:
        fixes.append("Removed get_part(s)_by_tex usage")
    return stripped


# Old ManimGL / pre-0.15 CE names that no longer exist. Unknown `get_*` methods hit
# Mobject.__getattr__ and fail with "getter() got an unexpected keyword argument".
_RENAMED_METHODS = {
    "get_graph": "plot",
    "get_derivative_graph": "plot_derivative_graph",
    "get_antiderivative_graph": "plot_antiderivative_graph",
    "get_parametric_curve": "plot_parametric_curve",
    "get_implicit_curve": "plot_implicit_curve",
    "get_line_graph": "plot_line_graph",
    "get_polar_graph": "plot_polar_graph",
}
_RENAMED_CLASSES = {
    "ShowCreationThenDestruction": "ShowPassingFlash",
    "ShowCreation": "Create",
    "TexMobject": "MathTex",
    "TextMobject": "Tex",
    "CircleIndicate": "Indicate",
    "WiggleOutThenIn": "Wiggle",
    "ParametricSurface": "Surface",
}


def fix_deprecated_api(code: str, fixes: list[str]) -> str:
    renamed: list[str] = []
    for old, new in _RENAMED_METHODS.items():
        code, n = re.subn(rf"\.{old}\s*\(", f".{new}(", code)
        if n:
            renamed.append(f"{old}→{new}")
    for old, new in _RENAMED_CLASSES.items():
        code, n = re.subn(rf"\b{old}\s*\(", f"{new}(", code)
        if n:
            renamed.append(f"{old}→{new}")

    # FadeInFrom(mob, DIR) / FadeOutAndShift(mob, DIR) → FadeIn/FadeOut(mob, shift=DIR)
    for old, new in (("FadeInFrom", "FadeIn"), ("FadeOutAndShift", "FadeOut")):
        code, n = re.subn(
            rf"\b{old}\(\s*([^,()]+?)\s*,\s*([^,()=]+?)\s*\)",
            rf"{new}(\1, shift=\2)",
            code,
        )
        code, n2 = re.subn(rf"\b{old}\(\s*([^,()]+?)\s*\)", rf"{new}(\1)", code)
        if n or n2:
            renamed.append(f"{old}→{new}(shift=)")
    code, n = re.subn(r"\bFadeInFromDown\(\s*([^,()]+?)\s*\)", r"FadeIn(\1, shift=UP)", code)
    if n:
        renamed.append("FadeInFromDown→FadeIn(shift=UP)")

    if renamed:
        fixes.append("Updated deprecated API: " + ", ".join(renamed))
    return code


def ensure_manim_import(code: str, fixes: list[str]) -> str:
    if "from manim import *" not in code:
        code = "from manim import *\n" + code.lstrip()
        fixes.append("Added missing 'from manim import *'")
    return code


def fix_riemann_rectangles(code: str, fixes: list[str]) -> str:
    """
    Ensure every get_riemann_rectangles() call has input_sample_type="right".
    Manim raises ValueError: Invalid input sample type when this arg is omitted
    (the default in some versions is neither 'left', 'right', nor 'center').
    """
    # Match .get_riemann_rectangles( ... ) calls that are missing input_sample_type
    pattern = re.compile(
        r"(\.get_riemann_rectangles\s*\([^)]*)",
        re.DOTALL,
    )

    def _add_sample_type(m: re.Match[str]) -> str:
        body = m.group(1)
        if "input_sample_type" in body:
            return body  # already set — don't touch
        # Append before the closing paren; strip trailing whitespace/comma first
        stripped = body.rstrip()
        if stripped.endswith(","):
            return stripped + ' input_sample_type="right"'
        return stripped + ', input_sample_type="right"'

    new_code = pattern.sub(_add_sample_type, code)
    if new_code != code:
        fixes.append('Added input_sample_type="right" to get_riemann_rectangles()')
    return new_code


def sanitize_manim_code(
    code: str,
    *,
    force_safe_tmt: bool = False,
) -> tuple[str, list[str]]:
    """
    Apply deterministic fixes before Manim render.
    Returns (fixed_code, list_of_fix_descriptions).
    """
    fixes: list[str] = []
    if not code or not code.strip():
        return code, fixes

    # Drop markdown fences if present
    fenced = re.sub(r"^```(?:python)?\s*\n?", "", code.strip(), flags=re.MULTILINE)
    fenced = re.sub(r"\n?```\s*$", "", fenced).strip()
    if fenced != code.strip():
        fixes.append("Stripped markdown fences")
        code = fenced

    code = ensure_manim_import(code, fixes)
    code = fix_scene_class_name(code, fixes)
    code = fix_deprecated_api(code, fixes)
    code = fix_get_parts_indexing(code, fixes)
    code = _fix_nonpositive_timings(code, fixes)
    if force_safe_tmt:
        code = force_safe_transforms(code, fixes)
    else:
        code = fix_transform_matching_tex(code, fixes)
    code = fix_axes_sizing(code, fixes)
    code = fix_overflow_coordinates(code, fixes)
    code = fix_riemann_rectangles(code, fixes)

    # DecimalNumber convenience
    new = re.sub(
        r"DecimalNumber\(\s*(\w+\.get_value\(\))\s*\)",
        r"DecimalNumber(\1, num_decimal_places=2)",
        code,
    )
    if new != code:
        fixes.append("Added num_decimal_places to DecimalNumber")
        code = new

    return code, fixes
