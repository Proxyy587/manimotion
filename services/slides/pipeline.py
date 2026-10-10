"""
Slide lecture pipeline (PIPELINE_V2):

  storyboard → one TTS clip per sentence → one build() body per slide (parallel) →
  render with layout/sync guards (2 at a time) → padded per-slide audio → concat →
  A/V assertion.

Length is whatever the storyboard needs; there are no duration caps.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable

from services.slides.assemble import assemble, slide_length
from services.slides.build import build_slide
from services.slides.narration import record_beats
from services.slides.storyboard import generate_storyboard

RENDER_WORKERS = int(os.getenv("SLIDE_RENDER_WORKERS", "2"))
LLM_WORKERS = int(os.getenv("SLIDE_LLM_WORKERS", "4"))

StatusFn = Callable[..., None]


def slides_enabled() -> bool:
    return os.getenv("PIPELINE_V2", "0").strip().lower() in {"1", "true", "yes", "on"}


def _eta_display(seconds: int) -> str:
    if seconds < 90:
        return "~1 min"
    return f"~{round(seconds / 60)} min"


def _codegen_enabled() -> bool:
    return os.getenv("SLIDE_CODEGEN", "1").strip().lower() not in {"0", "false", "no"}


async def run_slide_lecture(
    topic: str,
    *,
    model: str,
    work_dir: str,
    duration_hint: int | None = None,
    set_status: StatusFn = lambda *a, **k: None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    t0 = time.time()
    timings: dict[str, float] = {}

    set_status("planning", message="Planning the lesson…")
    storyboard = await asyncio.to_thread(
        generate_storyboard, topic, model, duration_hint=duration_hint, log=log
    )
    slides = storyboard["slides"]
    timings["storyboard"] = time.time() - t0

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
    render_sem = asyncio.Semaphore(RENDER_WORKERS)
    llm_sem = asyncio.Semaphore(LLM_WORKERS)
    done = 0

    def slide_status() -> None:
        elapsed = time.time() - t
        per_slide = elapsed / done if done else 50.0
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
    timings["slides"] = time.time() - t

    t = time.time()
    set_status("merging", message="Finishing touches…")
    final, vtt = await asyncio.to_thread(
        assemble, slides, [r["video"] for r in results], work_dir, log
    )
    timings["assemble"] = time.time() - t
    timings["total"] = time.time() - t0

    degraded = [r["slide_id"] for r in results if r["used_fallback"]]
    report = {
        "topic": topic,
        "model": model,
        "slides": [{k: v for k, v in r.items() if k != "video"} for r in results],
        "degraded_slides": degraded,
        "lecture_seconds": round(lecture_sec, 2),
        "timings": {k: round(v, 1) for k, v in timings.items()},
    }
    with open(os.path.join(work_dir, "slides_report.json"), "w", encoding="utf-8") as f:
        json.dump({**report, "storyboard": storyboard}, f, indent=2, default=str)
    log(
        f"  ✅ Lecture ready: {len(slides)} slides, {lecture_sec:.0f}s, "
        f"fallback slides {degraded or 'none'}, timings {report['timings']}"
    )
    return {"video": final, "captions": vtt, "duration": lecture_sec, **report}
