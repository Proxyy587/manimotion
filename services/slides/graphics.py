"""
Graphics lectures: each storyboard slide becomes a layout spec (bullets, timeline, bars, stats,
compare, steps, definition) rendered by the fixed Remotion template in
remotion-src/src/slides. The LLM only writes content; layout, typography and motion are
designed once, so text can never overlap and every sentence reveals or highlights something.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Optional

from prompts.graphics_prompt import (
    GRAPHICS_SLIDE_RETRY_TEMPLATE,
    GRAPHICS_SLIDE_SYSTEM_PROMPT,
    GRAPHICS_SLIDE_USER_TEMPLATE,
)
from services.llm import _client, _parse_json_object
from services.remotion_renderer import (
    REMOTION_SRC,
    _ensure_browser,
    _ensure_remotion_deps,
    _remotion_bin,
)
from services.slides.assemble import FPS, LEAD_IN, slide_length

RESOLUTION = os.getenv("SLIDE_RESOLUTION", "720")
CONCURRENCY = int(os.getenv("REMOTION_CONCURRENCY") or max(1, min(4, (os.cpu_count() or 2) // 2)))

# layout -> (min items, max items)
ITEM_COUNTS = {
    "bullets": (2, 6),
    "timeline": (2, 6),
    "bars": (2, 7),
    "stats": (1, 4),
    "compare": (2, 8),
    "steps": (2, 5),
    "definition": (1, 3),
}
# (layout, field) -> max characters
TEXT_LIMITS = {
    ("bullets", "text"): 64,
    ("bullets", "detail"): 76,
    ("timeline", "label"): 12,
    ("timeline", "text"): 48,
    ("bars", "label"): 24,
    ("bars", "display"): 10,
    ("stats", "display"): 9,
    ("stats", "text"): 48,
    ("compare", "text"): 52,
    ("steps", "text"): 38,
    ("steps", "detail"): 60,
    ("definition", "text"): 110,
}
TOP_LIMITS = {"term": 30, "left_title": 26, "right_title": 26, "unit": 32}
_ITEM_FIELDS = ("text", "detail", "label", "display")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
_LATEX = re.compile(r"\\[a-zA-Z]+|[\^{}]|\$(?![\d.])")


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", _EMOJI.sub("", str(text or ""))).strip()


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-–— ")
    return (cut or text[: limit - 1]) + "…"


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    layout = str(raw.get("layout") or "").strip().lower()
    items = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            it = {"text": it}
        item: dict[str, Any] = {k: _clean(it[k]) for k in _ITEM_FIELDS if it.get(k) not in (None, "")}
        if it.get("side") in ("left", "right"):
            item["side"] = it["side"]
        if it.get("value") is not None:
            try:
                item["value"] = float(str(it["value"]).replace(",", ""))
            except ValueError:
                pass
        if layout == "stats" and "display" not in item and "value" in item:
            item["display"] = f"{item['value']:g}"
        items.append(item)
    beats = []
    for b in raw.get("beats") or []:
        b = b if isinstance(b, dict) else {}
        show = b.get("show")
        show = [show] if isinstance(show, int) else show if isinstance(show, list) else []
        focus = b.get("focus")
        beats.append({
            "show": [s for s in show if isinstance(s, int)],
            "focus": focus if isinstance(focus, int) else None,
        })
    spec = {"layout": layout, "items": items, "beats": _settle_beats(beats, len(items))}
    for key in TOP_LIMITS:
        if raw.get(key):
            spec[key] = _clean(raw[key])
    return spec


def _settle_beats(beats: list[dict[str, Any]], n_items: int) -> list[dict[str, Any]]:
    """Fix mechanical reveal mistakes so every sentence reveals or points at something."""
    seen: set[int] = set()
    for b in beats:
        b["show"] = [s for s in dict.fromkeys(b["show"]) if 0 <= s < n_items and s not in seen]
        seen.update(b["show"])
        if b["focus"] is not None and not 0 <= b["focus"] < n_items:
            b["focus"] = None
    revealed: set[int] = set()
    for i, b in enumerate(beats):
        f = b["focus"]
        if f is not None and f not in revealed and f not in b["show"]:
            for later in beats[i + 1:]:
                if f in later["show"]:
                    later["show"].remove(f)
            b["show"] = sorted(b["show"] + [f])
        if not b["show"] and b["focus"] is None:
            if revealed:
                b["focus"] = max(revealed)
            else:
                nxt = next((later for later in beats[i + 1:] if later["show"]), None)
                if nxt:
                    b["show"] = [nxt["show"].pop(0)]
        revealed.update(b["show"])
    return beats


def validate_spec(spec: dict[str, Any], n_beats: int) -> list[str]:
    problems: list[str] = []
    layout, items = spec.get("layout"), spec.get("items") or []
    if layout not in ITEM_COUNTS:
        return [f"layout must be one of {', '.join(ITEM_COUNTS)} (got {layout!r})"]
    lo, hi = ITEM_COUNTS[layout]
    if not lo <= len(items) <= hi:
        problems.append(f"{layout} needs {lo}–{hi} items (got {len(items)})")
    for i, it in enumerate(items):
        for field in _ITEM_FIELDS:
            limit = TEXT_LIMITS.get((layout, field))
            value = it.get(field, "")
            if limit and len(value) > limit:
                problems.append(f"item {i} {field} is {len(value)} chars; max {limit}")
            if _LATEX.search(value):
                problems.append(f"item {i} {field} contains LaTeX/markup; use plain words")
        if layout in ("bullets", "timeline", "steps", "definition", "compare", "stats") and not it.get("text"):
            problems.append(f"item {i} needs text")
    if layout == "timeline" and any(not it.get("label") for it in items):
        problems.append("every timeline item needs a short label (e.g. a year)")
    if layout == "bars" and any("value" not in it or not it.get("label") for it in items):
        problems.append("every bar needs a label and a numeric value")
    if layout == "stats" and any(not it.get("display") for it in items):
        problems.append("every stat needs a display value like '70%'")
    if layout == "compare":
        sides = [it.get("side") for it in items]
        if "left" not in sides or "right" not in sides or None in sides:
            problems.append("compare items need side 'left' or 'right', with both sides used")
        if not spec.get("left_title") or not spec.get("right_title"):
            problems.append("compare needs left_title and right_title")
    if layout == "definition" and not spec.get("term"):
        problems.append("definition needs a term")
    for key, limit in TOP_LIMITS.items():
        if len(spec.get(key, "")) > limit:
            problems.append(f"{key} is too long (max {limit} chars)")
    problems += _beat_problems(spec, n_beats)
    return problems


def _beat_problems(spec: dict[str, Any], n_beats: int) -> list[str]:
    beats, n_items = spec.get("beats") or [], len(spec.get("items") or [])
    if len(beats) != n_beats:
        return [f"beats must have exactly {n_beats} entries (got {len(beats)})"]
    problems = []
    order = [s for b in beats for s in b["show"]]
    if sorted(order) != list(range(n_items)) or order != sorted(order):
        problems.append(f"show every item 0..{n_items - 1} exactly once, in order")
    revealed: set[int] = set()
    for i, b in enumerate(beats):
        revealed.update(b["show"])
        if b["focus"] is not None and b["focus"] not in revealed:
            problems.append(f"beat {i} focuses item {b['focus']} before it is shown")
        if not b["show"] and b["focus"] is None:
            problems.append(f"beat {i} shows nothing and focuses nothing")
    return problems


def repair_spec(spec: dict[str, Any], n_beats: int) -> dict[str, Any]:
    """Shorten over-long text and rebuild a sane reveal/focus plan if the LLM's is broken."""
    layout = spec["layout"]
    for it in spec["items"]:
        for field in _ITEM_FIELDS:
            limit = TEXT_LIMITS.get((layout, field))
            if limit and field in it:
                it[field] = _shorten(_LATEX.sub("", it[field]).strip(), limit)
    for key, limit in TOP_LIMITS.items():
        if key in spec:
            spec[key] = _shorten(spec[key], limit)
    if _beat_problems(spec, n_beats):
        n_items = len(spec["items"])
        reveal = [min(n_beats - 1, i * n_beats // max(1, n_items)) for i in range(n_items)]
        spec["beats"] = [
            {"show": [i for i, r in enumerate(reveal) if r == b], "focus": None} for b in range(n_beats)
        ]
        for b, beat in enumerate(spec["beats"]):
            shown = [i for i, r in enumerate(reveal) if r <= b]
            beat["focus"] = beat["show"][-1] if beat["show"] else (shown[-1] if shown else None)
    return spec


def fallback_spec(slide: dict[str, Any]) -> dict[str, Any]:
    """Always-valid bullets slide built from the storyboard's on-screen phrases."""
    items = []
    for b in slide["beats"]:
        phrase = _LATEX.sub(" ", b.get("on_screen") or "") or " ".join(b["text"].split()[:8])
        items.append({"text": _shorten(_clean(phrase), TEXT_LIMITS[("bullets", "text")])})
    beats = [{"show": [i], "focus": i} for i in range(len(items))]
    return {"layout": "bullets", "items": items, "beats": beats}


def _user_prompt(slide: dict[str, Any], storyboard: dict[str, Any]) -> str:
    beats = "\n".join(
        f'{i} | "{b["text"]}" | {b.get("on_screen", "")} | {b.get("action", "")}'
        for i, b in enumerate(slide["beats"])
    )
    return GRAPHICS_SLIDE_USER_TEMPLATE.format(
        lecture_title=storyboard.get("title") or "",
        slide_id=slide["id"],
        slide_total=len(storyboard["slides"]),
        slide_title=slide["title"],
        kind=slide.get("kind") or "",
        goal=slide.get("goal") or "",
        beats=beats,
        n_beats=len(slide["beats"]),
    )


async def design_slide(
    slide: dict[str, Any],
    storyboard: dict[str, Any],
    *,
    model: str,
    llm_sem: asyncio.Semaphore,
    retries: int = 1,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Return {"spec", "used_fallback", "attempts"}; never raises."""
    n_beats = len(slide["beats"])
    messages = [
        {"role": "system", "content": GRAPHICS_SLIDE_SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(slide, storyboard)},
    ]
    spec: Optional[dict[str, Any]] = None
    for attempt in range(1, retries + 2):
        try:
            async with llm_sem:
                response = await asyncio.to_thread(
                    _client.chat.send, model=model, messages=messages, temperature=0.4
                )
            raw = response.choices[0].message.content or ""
            spec = normalize_spec(_parse_json_object(raw))
        except Exception as exc:
            log(f"  ⚠️ Slide {slide['id']} design attempt {attempt} failed: {exc}")
            continue
        problems = validate_spec(spec, n_beats)
        if not problems:
            return {"spec": spec, "used_fallback": False, "attempts": attempt}
        log(f"  🔁 Slide {slide['id']} design attempt {attempt}: {problems[0]}")
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": GRAPHICS_SLIDE_RETRY_TEMPLATE.format(
                problems="\n".join(f"- {p}" for p in problems[:12])
            )},
        ]
    if spec and spec.get("layout") in ITEM_COUNTS:
        lo, hi = ITEM_COUNTS[spec["layout"]]
        if lo <= len(spec["items"]) <= hi:
            fixed = repair_spec(spec, n_beats)
            if not validate_spec(fixed, n_beats):
                log(f"  🩹 Slide {slide['id']}: repaired layout")
                return {"spec": fixed, "used_fallback": False, "attempts": retries + 1}
    log(f"  🛟 Slide {slide['id']}: using fallback layout")
    return {"spec": fallback_spec(slide), "used_fallback": True, "attempts": retries + 1}


def lecture_props(storyboard: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
    slides = storyboard["slides"]
    out = []
    for idx, (slide, spec) in enumerate(zip(slides, specs)):
        _, frames = slide_length(slide)
        starts, t = [], LEAD_IN
        for beat in slide["beats"]:
            starts.append(round(t * FPS))
            t += beat["dur"]
        reveal = [0] * len(spec["items"])
        for b, beat in enumerate(spec["beats"]):
            for i in beat["show"]:
                reveal[i] = b
        out.append({
            "title": slide["title"],
            "layout": spec["layout"],
            "frames": frames,
            "beatStarts": starts,
            "reveal": reveal,
            "focus": [b["focus"] if b["focus"] is not None else -1 for b in spec["beats"]],
            "items": spec["items"],
            "term": spec.get("term"),
            "leftTitle": spec.get("left_title"),
            "rightTitle": spec.get("right_title"),
            "unit": spec.get("unit"),
            "index": idx + 1,
            "total": len(slides),
            "accent": idx,
        })
    return {"title": storyboard.get("title") or "", "slides": out}


def render_lecture(props: dict[str, Any], work_dir: str, log: Callable[[str], None] = print) -> str:
    """Render the whole lecture with the fixed template; returns the silent mp4 path."""
    _ensure_remotion_deps(log=log)
    browser = _ensure_browser(log=log)
    if not browser:
        raise RuntimeError("No Chrome Headless Shell available for rendering")
    out_dir = os.path.abspath(os.path.join(work_dir, "graphics"))
    os.makedirs(out_dir, exist_ok=True)
    props_path = os.path.join(out_dir, "props.json")
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f)
    output = os.path.join(out_dir, "lecture.mp4")
    frames = sum(s["frames"] for s in props["slides"])
    scale = "1" if RESOLUTION == "1080" else str(2 / 3)
    cmd = [
        _remotion_bin(), "render", "src/slides/index.ts", "SlideLecture", output,
        f"--props={props_path}", f"--scale={scale}", f"--concurrency={CONCURRENCY}",
        "--jpeg-quality=92", "--log=error", "--browser-executable", browser,
    ]
    env = {**os.environ, "PUPPETEER_EXECUTABLE_PATH": browser, "CHROME_BIN": browser}
    t0 = time.time()
    proc = subprocess.run(
        cmd, cwd=REMOTION_SRC, env=env, capture_output=True, text=True,
        timeout=max(900, frames // 4),
    )
    if proc.returncode != 0 or not os.path.exists(output):
        err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        with open(os.path.join(out_dir, "render_error.log"), "w", encoding="utf-8") as f:
            f.write(err)
        raise RuntimeError(f"Graphics render failed: {err[-600:]}")
    log(f"  🎞️ Rendered {frames} frames in {time.time() - t0:.0f}s")
    return output
