"""Pre-render checks for LLM Remotion TSX: static rules + optional tsc syntax gate."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid

from services.remotion_renderer import REMOTION_SRC

_ALLOWED_MODULES = {"react", "remotion"}

# TS diagnostics that will break bundling or rendering; plain type mismatches are ignored.
_BLOCKING_TS_CODES = {"2304", "2305", "2307", "2552", "2724"}


def validate_remotion_code(code: str) -> list[str]:
    """Return a list of blocking problems (empty list = OK to render)."""
    errors: list[str] = []
    if not re.search(r"export\s+const\s+MainComposition\b", code):
        errors.append(
            "Missing named export: export const MainComposition: React.FC<{topic?: string}> = ..."
        )
    for mod in re.findall(r"""(?m)^\s*import\s[^;]*?from\s+['"]([^'"]+)['"]""", code):
        if mod not in _ALLOWED_MODULES:
            errors.append(f"Disallowed import '{mod}' — only 'react' and 'remotion' are installed")
    for mod in re.findall(r"""(?m)^\s*import\s+['"]([^'"]+)['"]""", code):
        errors.append(f"Disallowed side-effect import '{mod}' (no CSS/asset imports)")
    if re.search(r"\brequire\(", code):
        errors.append("require() is not allowed — use ES imports from react/remotion only")
    if re.search(r"\bfetch\(", code):
        errors.append("fetch() is not allowed — hardcode all data")
    if re.search(r"\bstaticFile\(|<(Img|Audio|Video|OffthreadVideo|IFrame)\b", code):
        errors.append("External assets (Img/Audio/Video/staticFile) are not available — use text, divs, or inline SVG")
    if re.search(r"durationInFrames=\{\s*0+(\.0+)?\s*\}", code):
        errors.append("durationInFrames={0} — use Math.max(1, Math.round(sec * 30))")
    return errors


def _tsc_bin() -> str | None:
    path = os.path.join(REMOTION_SRC, "node_modules", ".bin", "tsc")
    return path if os.path.exists(path) else None


def typecheck_remotion_code(code: str, timeout: int = 60) -> list[str]:
    """
    Run tsc on the component and return only blocking diagnostics
    (syntax errors, undefined names, bad imports). Skips silently if tsc is unavailable.
    """
    tsc = _tsc_bin()
    if not tsc:
        return []
    check_dir = os.path.join(REMOTION_SRC, "src", "compositions", f"_check_{uuid.uuid4().hex[:8]}")
    os.makedirs(check_dir, exist_ok=True)
    path = os.path.join(check_dir, "MainComposition.tsx")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        proc = subprocess.run(
            [
                tsc,
                "--noEmit",
                "--jsx", "react-jsx",
                "--target", "ES2020",
                "--module", "ESNext",
                "--moduleResolution", "bundler",
                "--esModuleInterop",
                "--skipLibCheck",
                path,
            ],
            cwd=REMOTION_SRC,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    finally:
        shutil.rmtree(check_dir, ignore_errors=True)

    blocking: list[str] = []
    for line in (proc.stdout or "").splitlines():
        m = re.search(r"MainComposition\.tsx\((\d+),\d+\): error TS(\d+): (.+)", line)
        if not m:
            continue
        line_no, code_no, msg = m.groups()
        if code_no.startswith("1") or code_no in _BLOCKING_TS_CODES:
            blocking.append(f"MainComposition.tsx:{line_no} TS{code_no}: {msg}")
    return blocking
