"""Step 1: the storyboard — slides → beats (one spoken sentence each), validated."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from prompts.slides_prompt import (
    STORYBOARD_RETRY_TEMPLATE,
    STORYBOARD_SYSTEM_PROMPT,
    STORYBOARD_USER_TEMPLATE,
    STYLE_HINTS,
)
from services.llm import _client, _parse_json_object

MIN_SLIDES, MAX_SLIDES = 3, 20
MIN_BEATS, MAX_BEATS = 3, 6
MIN_WORDS, MAX_WORDS = 6, 28
KINDS = {
    "bullets", "equation_steps", "graph", "compare", "custom",
    "timeline", "chart", "stats", "steps", "definition",
}
STYLES = {"math", "graphics"}
_SPOKEN_FORBIDDEN = re.compile(r"[\\^_$]")


def _balanced(latex: str) -> bool:
    depth = 0
    for ch in latex:
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


def validate_storyboard(sb: dict[str, Any]) -> list[str]:
    """Return human-readable problems; empty list means the storyboard is usable."""
    problems: list[str] = []
    slides = sb.get("slides")
    if not isinstance(slides, list):
        return ["'slides' must be a list"]
    if not MIN_SLIDES <= len(slides) <= MAX_SLIDES:
        problems.append(f"Use {MIN_SLIDES}–{MAX_SLIDES} slides (got {len(slides)}).")
    for si, slide in enumerate(slides, start=1):
        beats = slide.get("beats") if isinstance(slide, dict) else None
        if not isinstance(beats, list):
            problems.append(f"Slide {si}: 'beats' must be a list.")
            continue
        if not MIN_BEATS <= len(beats) <= MAX_BEATS:
            problems.append(f"Slide {si}: use {MIN_BEATS}–{MAX_BEATS} beats (got {len(beats)}).")
        for bi, beat in enumerate(beats):
            text = str(beat.get("text") or "")
            words = len(text.split())
            if not MIN_WORDS <= words <= MAX_WORDS:
                problems.append(
                    f"Slide {si} beat {bi}: sentence must be {MIN_WORDS}–{MAX_WORDS} words (got {words})."
                )
            if _SPOKEN_FORBIDDEN.search(text):
                problems.append(
                    f"Slide {si} beat {bi}: spoken text contains math symbols; say it in words."
                )
            if not str(beat.get("on_screen") or "").strip():
                problems.append(f"Slide {si} beat {bi}: on_screen is empty.")
            if not str(beat.get("action") or "").strip():
                problems.append(f"Slide {si} beat {bi}: action is empty.")
            if not _balanced(str(beat.get("on_screen") or "")):
                problems.append(f"Slide {si} beat {bi}: on_screen LaTeX braces are unbalanced.")
        for eq in slide.get("equations") or []:
            if not _balanced(str(eq)):
                problems.append(f"Slide {si}: equation {eq!r} has unbalanced braces.")
    return problems


def _normalize(sb: dict[str, Any]) -> dict[str, Any]:
    """Mechanical clean-up the LLM shouldn't have to be re-asked about."""
    slides = []
    for slide in sb.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        beats = []
        for beat in slide.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            text = re.sub(r"\s+", " ", str(beat.get("text") or "")).strip()
            beats.append(
                {
                    "text": text,
                    "on_screen": str(beat.get("on_screen") or "").strip(),
                    "action": str(beat.get("action") or "").strip(),
                }
            )
        kind = str(slide.get("kind") or "custom").strip().lower()
        slides.append(
            {
                "title": str(slide.get("title") or "").strip()[:60],
                "kind": kind if kind in KINDS else "custom",
                "goal": str(slide.get("goal") or "").strip(),
                "beats": beats,
                "equations": [str(e) for e in slide.get("equations") or []],
                "graph": slide.get("graph") if isinstance(slide.get("graph"), dict) else None,
            }
        )
    for i, slide in enumerate(slides, start=1):
        slide["id"] = i
    style = str(sb.get("style") or "").strip().lower()
    if style not in STYLES:
        mathy = any(s["kind"] in {"graph", "equation_steps"} or s["equations"] for s in slides)
        style = "math" if mathy else "graphics"
    return {"title": str(sb.get("title") or "").strip(), "style": style, "slides": slides}


def _salvage(sb: dict[str, Any]) -> dict[str, Any]:
    """Last resort after re-asks: make the storyboard renderable without the LLM."""
    slides = []
    for slide in sb["slides"]:
        beats = [b for b in slide["beats"] if b["text"]]
        for b in beats:
            b["text"] = _SPOKEN_FORBIDDEN.sub(" ", b["text"]).strip()
            b["on_screen"] = b["on_screen"] or " ".join(b["text"].split()[:6])
            b["action"] = b["action"] or "Show the key phrase"
            if not _balanced(b["on_screen"]):
                b["on_screen"] = re.sub(r"[{}\\]", "", b["on_screen"])
        while len(beats) > MAX_BEATS:
            slides.append({**slide, "beats": beats[:MAX_BEATS]})
            beats = beats[MAX_BEATS:]
        if beats:
            slides.append({**slide, "beats": beats})
    slides = slides[:MAX_SLIDES]
    for i, slide in enumerate(slides, start=1):
        slide["id"] = i
    return {**sb, "slides": slides}


def generate_storyboard(
    topic: str,
    model: str,
    *,
    duration_hint: Optional[int] = None,
    style: str = "auto",
    max_retries: int = 2,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Ask for a storyboard, re-ask with the validator's problems, then salvage."""
    style = style if style in STYLE_HINTS else "auto"
    sb = _generate(topic, model, duration_hint, style, max_retries, log)
    if style != "auto":
        sb["style"] = style
    log(f"  🎨 Lecture style: {sb['style']}")
    return sb


def _generate(
    topic: str,
    model: str,
    duration_hint: Optional[int],
    style: str,
    max_retries: int,
    log: Callable[[str], None],
) -> dict[str, Any]:
    length_hint = (
        f"The user would like roughly {duration_hint} seconds — a soft hint; teach properly first."
        if duration_hint
        else (
            "Choose the length the topic needs. Each slide is about half a minute of speech: "
            "a focused question fits in 4–6 slides, a typical topic in 6–8, and only a broad "
            "survey or an explicit request for depth needs more."
        )
    )
    messages = [
        {"role": "system", "content": STORYBOARD_SYSTEM_PROMPT},
        {"role": "user", "content": STORYBOARD_USER_TEMPLATE.format(
            topic=topic, length_hint=length_hint, style_hint=STYLE_HINTS[style]
        )},
    ]
    last: Optional[dict[str, Any]] = None
    for attempt in range(1, max_retries + 2):
        response = _client.chat.send(model=model, messages=messages, temperature=0.4)
        raw = response.choices[0].message.content or ""
        try:
            sb = _normalize(_parse_json_object(raw))
        except Exception as exc:  # malformed JSON
            problems = [f"Output was not valid JSON ({exc}). Return JSON only."]
            sb = None
        else:
            problems = validate_storyboard(sb)
            last = sb
        if sb is not None and not problems:
            beats = sum(len(s["beats"]) for s in sb["slides"])
            log(f"  ✔️ Storyboard: {len(sb['slides'])} slides, {beats} sentences")
            return sb
        log(f"  🔁 Storyboard attempt {attempt}: {len(problems)} problem(s) — {problems[0]}")
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": STORYBOARD_RETRY_TEMPLATE.format(
                problems="\n".join(f"- {p}" for p in problems[:25])
            )},
        ]
    if last and last.get("slides"):
        fixed = _salvage(last)
        if fixed["slides"] and len(fixed["slides"]) >= 1:
            log(f"  🩹 Storyboard salvaged: {len(fixed['slides'])} slides")
            return fixed
    raise RuntimeError("Could not produce a lesson plan for this topic. Try rephrasing it.")
