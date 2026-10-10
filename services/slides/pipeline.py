"""
Slide lecture pipeline:

  storyboard (style: math | graphics) → one TTS clip per sentence →
    math:     one Manim build() body per slide, rendered with layout/sync guards
    graphics: one layout spec per slide, rendered by the fixed Remotion template
  → padded per-slide audio → frame-exact video → A/V assertion.

Length is whatever the storyboard needs; there are no duration caps. Every LLM call uses
the model the user picked.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable

from services.slides.assemble import assemble, assemble_continuous, slide_length
from services.slides.build import build_slide
from services.slides.graphics import design_slide, lecture_props, render_lecture
from services.slides.narration import record_beats
from services.slides.storyboard import generate_storyboard

RENDER_WORKERS = int(os.getenv("SLIDE_RENDER_WORKERS", "2"))
LLM_WORKERS = int(os.getenv("SLIDE_LLM_WORKERS", "4"))

StatusFn = Callable[..., None]


def slides_enabled() -> bool:
    return os.getenv("PIPELINE_V2", "1").strip().lower() not in {"0", "false", "no", "off"}


def _eta_display(seconds: int) -> str:
    if seconds < 90:
        return "~1 min"
    return f"~{round(seconds / 60)} min"


def style_for(engine: str | None) -> str:
    return {"manim": "math", "remotion": "graphics"}.get((engine or "auto").lower(), "auto")


def engine_for(style: str) -> str:
    return "remotion" if style == "graphics" else "manim"


def _codegen_enabled() -> bool:
    return os.getenv("SLIDE_CODEGEN", "1").strip().lower() not in {"0", "false", "no"}


async def run_slide_lecture(
    topic: str,
    *,
    model: str,
    work_dir: str,
    style: str = "auto",
    duration_hint: int | None = None,
    set_status: StatusFn = lambda *a, **k: None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    t0 = time.time()
    timings: dict[str, float] = {}
    log(f"  🧠 Model: {model}")

    set_status("planning", message="Planning the lesson…")
    storyboard = await asyncio.to_thread(
        generate_storyboard, topic, model, duration_hint=duration_hint, style=style, log=log
    )
    slides = storyboard["slides"]
    timings["storyboard"] = time.time() - t0
    engine = engine_for(storyboard["style"])
    outer_status = set_status

    def set_status(status: str, **extra: Any) -> None:
        outer_status(status, engine=engine, **extra)

    t = time.time()
    total_beats = sum(len(s["beats"]) for s in slides)
    set_status("generating_audio", message=f"Recording narration · 0 of {total_beats}")
    await record_beats(
        storyboard,
        work_dir,
        on_progress=lambda done, total: set_status(
            "generating_audio", message=f"Recording narration · {done} of {total}"
        ),
    )
    timings["narration"] = time.time() - t
    with open(os.path.join(work_dir, "storyboard.json"), "w", encoding="utf-8") as f:
        json.dump(storyboard, f, indent=2)
    lecture_sec = sum(slide_length(s)[0] for s in slides)
    log(f"  🎙️ Narration: {total_beats} sentences, lecture length {lecture_sec:.0f}s")

    t = time.time()
    if storyboard["style"] == "graphics":
        results, final, vtt = await _graphics(storyboard, model, work_dir, lecture_sec, set_status, log)
    else:
        results, final, vtt = await _math(storyboard, model, work_dir, lecture_sec, set_status, log)
    timings["visuals_and_assembly"] = time.time() - t
    timings["total"] = time.time() - t0

    degraded = [r["slide_id"] for r in results if r["used_fallback"]]
    report = {
        "topic": topic,
        "model": model,
        "style": storyboard["style"],
        "engine": engine,
        "slides": [{k: v for k, v in r.items() if k not in ("video", "spec")} for r in results],
        "degraded_slides": degraded,
        "lecture_seconds": round(lecture_sec, 2),
        "timings": {k: round(v, 1) for k, v in timings.items()},
    }
    with open(os.path.join(work_dir, "slides_report.json"), "w", encoding="utf-8") as f:
        json.dump({**report, "storyboard": storyboard}, f, indent=2, default=str)
    log(
        f"  ✅ Lecture ready: {storyboard['style']}, {len(slides)} slides, {lecture_sec:.0f}s, "
        f"fallback slides {degraded or 'none'}, timings {report['timings']}"
    )
    return {"video": final, "captions": vtt, "duration": lecture_sec, **report}


async def _math(storyboard, model, work_dir, lecture_sec, set_status, log):
    slides = storyboard["slides"]
    render_sem = asyncio.Semaphore(RENDER_WORKERS)
    llm_sem = asyncio.Semaphore(LLM_WORKERS)
    t = time.time()
    done = 0

    def slide_status() -> None:
        per_slide = (time.time() - t) / done if done else 50.0
        eta = int(per_slide * (len(slides) - done) / max(1, RENDER_WORKERS) + lecture_sec * 0.2 + 15)
        set_status(
            "generating_code",
            message=f"Animating slides · {done} of {len(slides)}",
            eta_seconds=eta,
            eta_display=_eta_display(eta),
        )

    async def one(slide: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        result = await build_slide(
            slide,
            storyboard,
            work_dir,
            model=model,
            render_sem=render_sem,
            llm_sem=llm_sem,
            codegen=_codegen_enabled(),
            log=log,
        )
        done += 1
        slide_status()
        return result

    slide_status()
    results = await asyncio.gather(*(one(s) for s in slides))
    set_status("merging", message="Finishing touches…")
    final, vtt = await asyncio.to_thread(assemble, slides, [r["video"] for r in results], work_dir, log)
    return results, final, vtt


async def _graphics(storyboard, model, work_dir, lecture_sec, set_status, log):
    slides = storyboard["slides"]
    llm_sem = asyncio.Semaphore(LLM_WORKERS)
    done = 0

    async def one(slide: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        result = await design_slide(slide, storyboard, model=model, llm_sem=llm_sem, log=log)
        done += 1
        set_status("generating_code", message=f"Designing slides · {done} of {len(slides)}")
        return {"slide_id": slide["id"], **result}

    set_status("generating_code", message=f"Designing slides · 0 of {len(slides)}")
    results = await asyncio.gather(*(one(s) for s in slides))

    props = lecture_props(storyboard, [r["spec"] for r in results])
    with open(os.path.join(work_dir, "graphics_props.json"), "w", encoding="utf-8") as f:
        json.dump(props, f, indent=2)
    eta = int(lecture_sec * 0.6 + 30)
    set_status(
        "generating_code",
        message="Animating the lecture…",
        eta_seconds=eta,
        eta_display=_eta_display(eta),
    )
    try:
        video = await asyncio.to_thread(render_lecture, props, work_dir, log)
    except Exception as exc:
        log(f"  🔁 Render failed once, retrying: {str(exc)[:200]}")
        video = await asyncio.to_thread(render_lecture, props, work_dir, log)
    set_status("merging", message="Finishing touches…")
    final, vtt = await asyncio.to_thread(assemble_continuous, slides, video, work_dir, log)
    return results, final, vtt
