"""
Step 3–5: write each slide's build() body with the LLM, check it statically, render it,
and retry with the error (always the user's chosen model) before falling back to a
deterministic slide. A single failing slide never fails the job.
"""

from __future__ import annotations

import ast
import asyncio
import builtins
import glob
import importlib.util
import os
import re
import subprocess
import textwrap
import time
from typing import Any, Callable, Optional

from prompts.slides_prompt import (
    RETRY_GUIDANCE,
    SLIDE_RETRY_TEMPLATE,
    SLIDE_SYSTEM_PROMPT,
    SLIDE_USER_TEMPLATE,
)
from services.llm import CODE_TEMPERATURE, _client, clean_code
from services.renderer import _manim_cmd

KIT_DIR = os.path.join(os.path.dirname(__file__), "kit")
CODE_ATTEMPTS = int(os.getenv("SLIDE_CODE_ATTEMPTS", "3"))
RENDER_TIMEOUT = float(os.getenv("SLIDE_RENDER_TIMEOUT", "480"))
RESOLUTION = os.getenv("SLIDE_RESOLUTION", "720")

_FORBIDDEN = [
    (r"\bself\.play\(", "self.play() — use self.beat(i, ...)"),
    (r"\bself\.wait\(", "self.wait() — use self.beat(i) to hold"),
    (r"\bself\.add\(", "self.add() — reveal objects inside self.beat(i, FadeIn(...))"),
    (r"^\s*(import|from)\s", "import statements — everything is already imported"),
    (r"^\s*class\s", "class definitions — write only the build() body"),
    (r"get_parts?_by_tex", "get_part_by_tex — highlight whole objects instead"),
    (r"\b(ImageMobject|SVGMobject)\b", "images/SVGs — draw with shapes instead"),
    (r"\b(ShowCreation|TexMobject|TextMobject|GraphScene)\b", "old ManimGL API"),
]

_available: Optional[set[str]] = None


def _available_names() -> set[str]:
    """Everything a slide body may reference without defining it."""
    global _available
    if _available is None:
        spec = importlib.util.spec_from_file_location("slide_kit", os.path.join(KIT_DIR, "slide_kit.py"))
        kit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kit)  # type: ignore[union-attr]
        _available = set(dir(kit)) | set(dir(builtins)) | {"self", "np"}
    return _available


def normalize_body(text: str) -> str:
    """LLM output → a dedented build() body (drops fences / a stray def line)."""
    code = clean_code(text or "")
    m = re.search(r"^\s*def build\(self\)\s*:\s*\n", code, re.M)
    if m:
        code = code[m.end():]
    return textwrap.dedent(code).strip("\n")


_LATEX_CMD = re.compile(r"\\[a-zA-Z]+(\{[^{}]*\})?")


def _latex_problems(tree: ast.AST) -> list[str]:
    """MathTex drops spaces and italicizes words; an unescaped % comments out the rest."""
    problems = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
        if name in {"Text", "body_text", "bullets"}:
            strings = [
                n.value for a in call.args for n in ast.walk(a)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            for s in strings:
                if "$" in s or re.search(r"\\[a-zA-Z]", s):
                    problems.append(
                        f"{name}({s[:40]!r}) contains LaTeX, which plain text shows literally; "
                        "use words (e.g. 'means') or a separate MathTex"
                    )
            continue
        if name not in {"MathTex", "Tex"} or not isinstance(call.func, ast.Name):
            continue
        for arg in call.args:
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            s = arg.value
            if re.search(r"(?<!\\)%", s):
                problems.append(f"Escape % as \\% in {call.func.id}({s[:40]!r})")
            if call.func.id == "MathTex":
                bare = _LATEX_CMD.sub(" ", s)
                word = re.search(r"[A-Za-z]{4,}", bare)
                if word:
                    problems.append(
                        f"MathTex({s[:40]!r}) has the bare word {word.group()!r}; wrap words in "
                        "\\text{...} or use body_text for word-only labels"
                    )
    return problems


def static_check(body: str, n_beats: int) -> list[str]:
    problems = [f"Remove {why}" for pat, why in _FORBIDDEN if re.search(pat, body, re.M)]
    try:
        tree = ast.parse(body)
    except SyntaxError as exc:
        return problems + [f"SyntaxError line {exc.lineno}: {exc.msg}"]

    stored: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            stored.add(node.id)
        elif isinstance(node, ast.arg):
            stored.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stored.add(node.name)
    known = _available_names() | stored
    unknown = sorted(
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        - known
    )
    if unknown:
        problems.append(
            f"Unknown names (not in Manim CE / slide_kit): {', '.join(unknown)} — use only listed mobjects"
        )

    problems += _latex_problems(tree)

    beat_args = [
        call.args[0]
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "beat"
        and call.args
    ]
    if all(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in beat_args):
        used = sorted(a.value for a in beat_args)
        if used != list(range(n_beats)):
            problems.append(
                f"self.beat indices used {used}; need each of 0..{n_beats - 1} exactly once, in order"
            )
    return problems


def wrap_slide(body: str, title: str, beats: list[dict[str, Any]]) -> str:
    beat_list = [{"text": b["text"], "dur": b["dur"]} for b in beats]
    return (
        "from slide_kit import *\n\n\n"
        "class Scene(SlideScene):\n"
        f"    SLIDE_TITLE = {title!r}\n"
        f"    BEATS = {beat_list!r}\n\n"
        "    def build(self):\n"
        f"{textwrap.indent(body, ' ' * 8)}\n"
    )


def fallback_source(title: str, beats: list[dict[str, Any]], *, math_ok: bool = True) -> str:
    points = [b.get("on_screen") or " ".join(b["text"].split()[:6]) for b in beats]
    if not math_ok:
        points = [
            re.sub(r"\s+", " ", re.sub(r"[{}^_$]", "", re.sub(r"\\[a-zA-Z]+|\\.", " ", p))).strip()
            for p in points
        ]
    beat_list = [{"text": b["text"], "dur": b["dur"]} for b in beats]
    return (
        "from slide_kit import *\n\n\n"
        "class Scene(FallbackSlide):\n"
        f"    SLIDE_TITLE = {title!r}\n"
        f"    BEATS = {beat_list!r}\n"
        f"    POINTS = {points!r}\n"
        f"    MATH_OK = {math_ok!r}\n"
    )


def _quality_args() -> list[str]:
    if RESOLUTION == "1080":
        return ["-qh", "--frame_rate", "30"]
    return ["-qm"]


def _classify(stderr: str) -> tuple[str, str]:
    text = re.sub(r"[│╭╮╰╯─┃]", " ", stderr or "")
    for kind in ("LayoutError", "SyncError"):
        m = re.findall(rf"{kind}: (.+)", text)
        if m:
            return kind, m[-1].strip()[:900]
    errors = re.findall(r"^\s*(\w+(?:Error|Exception)): (.*)$", text, re.M)
    if errors:
        name, msg = errors[-1]
        return "ManimError", f"{name}: {msg.strip()}"[:900]
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()][-8:]
    return "ManimError", " | ".join(tail)[:900]


def render_slide(source: str, slide_dir: str, name: str) -> tuple[Optional[str], Optional[tuple[str, str]]]:
    """Render one slide file. Returns (mp4_path, None) or (None, (error_type, message))."""
    slide_dir = os.path.abspath(slide_dir)
    os.makedirs(slide_dir, exist_ok=True)
    src_path = os.path.join(slide_dir, f"{name}.py")
    with open(src_path, "w", encoding="utf-8") as f:
        f.write(source)
    media = os.path.join(slide_dir, "media")
    env = os.environ.copy()
    env["PYTHONPATH"] = KIT_DIR + os.pathsep + env.get("PYTHONPATH", "")
    cmd = _manim_cmd() + _quality_args() + [
        "--disable_caching", "--media_dir", media, "-o", name, src_path, "Scene",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=slide_dir, env=env, capture_output=True, text=True, timeout=RENDER_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return None, ("ManimError", f"Render timed out after {RENDER_TIMEOUT:.0f}s — simplify the slide")
    if proc.returncode != 0:
        with open(os.path.join(slide_dir, f"{name}_error.log"), "w", encoding="utf-8") as f:
            f.write(proc.stderr or proc.stdout or "")
        return None, _classify((proc.stderr or "") + "\n" + (proc.stdout or ""))
    found = glob.glob(os.path.join(media, "videos", name, "*", f"{name}.mp4"))
    if not found:
        return None, ("ManimError", "Render finished but no video was written")
    return found[0], None


def _beats_block(beats: list[dict[str, Any]]) -> str:
    return "\n".join(
        f'{i} ({b["dur"]:.1f}s) "{b["text"]}" | {b.get("on_screen", "")} | {b.get("action", "")}'
        for i, b in enumerate(beats)
    )


def _slide_prompt(slide: dict[str, Any], storyboard: dict[str, Any]) -> str:
    extras = []
    if slide.get("equations"):
        extras.append("EQUATIONS (LaTeX): " + " ;; ".join(slide["equations"]))
    if slide.get("graph"):
        extras.append(f"GRAPH: {slide['graph']}")
    return SLIDE_USER_TEMPLATE.format(
        lecture_title=storyboard.get("title") or "",
        slide_id=slide["id"],
        slide_total=len(storyboard["slides"]),
        slide_title=slide["title"],
        kind=slide["kind"],
        goal=slide.get("goal") or "",
        extras="\n".join(extras),
        beats=_beats_block(slide["beats"]),
    )


def _ask(model: str, messages: list[dict[str, str]]) -> str:
    response = _client.chat.send(model=model, messages=messages, temperature=CODE_TEMPERATURE)
    return normalize_body(response.choices[0].message.content or "")


async def build_slide(
    slide: dict[str, Any],
    storyboard: dict[str, Any],
    work_dir: str,
    *,
    model: str,
    render_sem: asyncio.Semaphore,
    llm_sem: asyncio.Semaphore,
    codegen: bool = True,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Produce one rendered slide video; always succeeds (fallback last)."""
    sid = slide["id"]
    slide_dir = os.path.join(work_dir, "slides", f"s{sid:02d}")
    beats = slide["beats"]
    title = slide["title"]
    report: dict[str, Any] = {"slide_id": sid, "attempts": 0, "used_fallback": False, "error_types": []}
    t0 = time.time()

    ladder = [model] * CODE_ATTEMPTS if codegen else []
    base = [
        {"role": "system", "content": SLIDE_SYSTEM_PROMPT},
        {"role": "user", "content": _slide_prompt(slide, storyboard)},
    ]
    body: Optional[str] = None
    error: Optional[tuple[str, str]] = None
    for attempt, attempt_model in enumerate(ladder, start=1):
        report["attempts"] = attempt
        messages = list(base)
        if body is not None and error is not None:
            messages.append({
                "role": "user",
                "content": SLIDE_RETRY_TEMPLATE.format(
                    error_type=error[0],
                    error_message=error[1],
                    guidance=RETRY_GUIDANCE.get(error[0], RETRY_GUIDANCE["ManimError"]),
                    code=body,
                ),
            })
        try:
            async with llm_sem:
                body = await asyncio.to_thread(_ask, attempt_model, messages)
        except Exception as exc:
            error = ("ManimError", f"Model call failed: {exc}")
            report["error_types"].append("LLMError")
            log(f"  ⚠️ Slide {sid} attempt {attempt}: model call failed ({exc})")
            continue

        problems = static_check(body, len(beats))
        if problems:
            error = ("StaticCheck", "; ".join(problems))
            report["error_types"].append("StaticCheck")
            log(f"  🔎 Slide {sid} attempt {attempt}: {problems[0]}")
            continue

        async with render_sem:
            video, error = await asyncio.to_thread(
                render_slide, wrap_slide(body, title, beats), slide_dir, f"a{attempt}"
            )
        if video:
            report["seconds"] = round(time.time() - t0, 1)
            log(f"  🎬 Slide {sid} ready (attempt {attempt})")
            return {**report, "video": video}
        report["error_types"].append(error[0])
        log(f"  🔁 Slide {sid} attempt {attempt}: {error[0]} — {error[1][:160]}")

    report["used_fallback"] = True
    for math_ok in (True, False):
        async with render_sem:
            video, err = await asyncio.to_thread(
                render_slide,
                fallback_source(title, beats, math_ok=math_ok),
                slide_dir,
                "fallback" if math_ok else "fallback_text",
            )
        if video:
            report["seconds"] = round(time.time() - t0, 1)
            log(f"  🛟 Slide {sid}: using fallback slide")
            return {**report, "video": video}
        log(f"  ⚠️ Slide {sid} fallback (math={math_ok}) failed: {err[1][:160] if err else ''}")
    raise RuntimeError(f"Slide {sid} could not be rendered, even as a fallback")
