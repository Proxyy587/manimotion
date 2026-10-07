"""Guaranteed-working Manim templates when LLM retries are exhausted."""

from __future__ import annotations

import json
import re
from typing import Any


def _py_str(s: str) -> str:
    return json.dumps(str(s)[:120])


def _safe_visual_line(beat: dict[str, Any], fallback: str) -> str:
    visual = (beat.get("visual") or beat.get("narration") or fallback).strip()
    visual = re.sub(r"\s+", " ", visual)
    if len(visual) > 90:
        visual = visual[:87] + "..."
    return visual or fallback


def build_guaranteed_manim_code(
    topic: str,
    visual_plan: dict[str, Any] | None = None,
) -> str:
    """
    Pre-tested slide-per-beat template: Text only, ReplacementTransform, positive waits.
    Uses beat durations from the plan when present.
    """
    plan = visual_plan or {}
    title = (plan.get("title") or topic or "Concept").strip()
    beats = plan.get("beats") or []
    if not beats:
        beats = [
            {"id": 1, "duration_sec": 6, "visual": topic},
            {"id": 2, "duration_sec": 6, "visual": "Key idea"},
            {"id": 3, "duration_sec": 6, "visual": "Summary"},
        ]

    beat_blocks: list[str] = []
    for i, beat in enumerate(beats[:8]):
        bid = beat.get("id", i + 1)
        try:
            dur = float(beat.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5.0
        dur = max(2.0, dur)
        line = _safe_visual_line(beat, topic)
        clear = (
            '        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.5)\n'
            if i > 0
            else ""
        )
        anim_rt = min(1.5, max(0.8, dur * 0.25))
        wait_rt = max(0.5, dur - anim_rt - (0.5 if i > 0 else 0.0))
        beat_blocks.append(
            f"        # BEAT {bid} (fallback template, {dur:.1f}s)\n"
            f"{clear}"
            f"        slide = Text({_py_str(line)}, font_size=36)\n"
            f"        slide.move_to(ORIGIN)\n"
            f"        if slide.width > 11:\n"
            f"            slide.scale_to_fit_width(11)\n"
            f"        self.play(FadeIn(slide), run_time={anim_rt:.2f})\n"
            f"        self.wait({wait_rt:.2f})\n"
        )

    body = "\n".join(beat_blocks)
    return f'''from manim import *

class Scene(Scene):
    def construct(self):
        header = Text({_py_str(title)}, font_size=44).to_edge(UP, buff=0.5)
        self.play(Write(header), run_time=0.8)
        self.wait(0.5)
{body}
        self.wait(1.0)
'''
