"""Parse Remotion bundle/render errors into actionable retry hints for the LLM."""

from __future__ import annotations

import re
from typing import Any

ERROR_FIX_MAP: dict[str, str] = {
    "ModuleNotFound": (
        "Import ONLY from 'react' and 'remotion'. Remove every other import "
        "(no framer-motion, @remotion/*, lucide, d3, CSS files, images)."
    ),
    "SyntaxError": (
        "Fix the TSX syntax at the indicated line: balance every {, (, [, and JSX tag; "
        "close template literals; no stray markdown or prose."
    ),
    "ReferenceError": (
        "A variable or component is used but never defined. Define it above its use "
        "or import it from 'remotion' (AbsoluteFill, Sequence, Series, interpolate, "
        "spring, Easing, useCurrentFrame, useVideoConfig)."
    ),
    "TypeError": (
        "A value is undefined at runtime. Guard array indexing (arr[i] may be undefined), "
        "and make sure every component you render is defined and returns JSX."
    ),
    "InterpolateRange": (
        "Every interpolate() inputRange must be strictly increasing with distinct finite "
        "numbers, and inputRange/outputRange must have the same length. "
        "Example: interpolate(frame, [d, d + 20], [0, 1], {extrapolateLeft: 'clamp', "
        "extrapolateRight: 'clamp'})."
    ),
    "Duration": (
        "Every durationInFrames must be a positive integer: "
        "durationInFrames={Math.max(1, Math.round(sec * 30))}. Sequence from must be >= 0."
    ),
    "Hooks": (
        "Call useCurrentFrame / useVideoConfig only at the top level of a React component. "
        "Never inside .map(), conditions, loops, or helper functions — extract a child "
        "component instead."
    ),
    "MissingComposition": (
        "Export a named component: export const MainComposition: React.FC<{topic?: string}> = ..."
    ),
    "timeout": (
        "Render timed out. Simplify: fewer elements per frame, no filters/blur/shadows, "
        "no large SVG paths, fewer simultaneous animations."
    ),
    "NaN": (
        "A style or interpolate value is NaN. Make sure every number is finite; "
        "avoid dividing by zero and reading missing data fields."
    ),
}


def _line_number(text: str) -> int | None:
    m = re.search(r"MainComposition\.tsx[:(](\d+)", text)
    return int(m.group(1)) if m else None


def parse_remotion_error(stderr: str) -> dict[str, Any]:
    text = stderr or ""
    low = text.lower()
    result: dict[str, Any] = {
        "type": "unknown",
        "message": "",
        "line": _line_number(text),
        "fix_hint": "",
        "full_error": text[-2000:],
    }

    def hit(err_type: str, message: str) -> dict[str, Any]:
        result.update(
            {"type": err_type, "message": message[:400], "fix_hint": ERROR_FIX_MAP[err_type]}
        )
        return result

    if "missing maincomposition" in low:
        return hit("MissingComposition", "MainComposition export missing")
    if "timed out" in low or "timeoutexpired" in low:
        return hit("timeout", "Remotion render timed out")

    m = re.search(r"(?:Module not found|Can't resolve|Could not resolve) ['\"]?([^'\"\s]+)", text)
    if m:
        return hit("ModuleNotFound", f"Cannot resolve module '{m.group(1)}'")

    if "inputrange" in low or "outputrange" in low:
        line = next((ln for ln in text.splitlines() if "nputRange" in ln or "utputRange" in ln), "")
        return hit("InterpolateRange", line.strip() or "Invalid interpolate range")

    if "invalid hook call" in low or "rendered more hooks" in low or "rendered fewer hooks" in low:
        return hit("Hooks", "React hook called outside component top level")

    if "durationinframes" in low and any(
        k in low for k in ("must be", "positive", "integer", "finite", "invalid")
    ):
        return hit("Duration", "Invalid durationInFrames / from")

    m = re.search(r"ReferenceError: (.+?)(?:\n|$)", text)
    if m:
        return hit("ReferenceError", m.group(1))

    m = re.search(r"(SyntaxError: .+?|Unexpected token.*?|ERROR: Expected .+?|Transform failed.*?)(?:\n|$)", text)
    if m:
        return hit("SyntaxError", m.group(1))

    if re.search(r"\bnan\b", low):
        return hit("NaN", "NaN value in style or interpolate")

    m = re.search(r"TypeError: (.+?)(?:\n|$)", text)
    if m:
        return hit("TypeError", m.group(1))

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        result["message"] = lines[-1][:400]
    return result


def _section(code: str, line_num: int, context: int = 6) -> str:
    lines = code.split("\n")
    start = max(0, line_num - context - 1)
    end = min(len(lines), line_num + context)
    out = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        mark = "→ " if i == line_num else "  "
        out.append(f"{mark}{i:3d}: {line}")
    return "\n".join(out)


def build_remotion_retry_prompt(
    *,
    attempt: int,
    max_attempts: int,
    broken_code: str,
    stderr: str,
    topic: str = "",
) -> str:
    info = parse_remotion_error(stderr)
    err_type = info.get("type", "unknown")
    fix = info.get("fix_hint") or "Fix the error shown below."
    tail = (stderr or "")[-1000:]
    context = ""
    if info.get("line"):
        context = f"\nERROR CONTEXT (approx line {info['line']}):\n{_section(broken_code, info['line'])}\n"
    code_trim = broken_code if len(broken_code) < 8000 else broken_code[:8000] + "\n// ..."
    return f"""REMOTION CODE FAILED. Fix attempt {attempt}/{max_attempts}.
TOPIC: {topic}

SPECIFIC ERROR ({err_type}):
{tail}

REQUIRED FIX:
{fix}
{context}
BROKEN CODE (return the COMPLETE fixed component; change only what caused the error):
{code_trim}

Rules:
- Named export MainComposition; imports only from 'react' and 'remotion'.
- Fix ONLY what caused this error; do not rewrite working sections."""
