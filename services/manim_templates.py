"""Guaranteed-working Manim templates when LLM retries are exhausted."""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_BULLETS = 4
REVEAL_SEC = 0.6
CLEAR_SEC = 0.4


def _py_str(s: str) -> str:
    return json.dumps(str(s), ensure_ascii=False)


def _wrap(text: str, width: int = 44, max_len: int = 88) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rsplit(" ", 1)[0] + "…"
    if len(text) <= width:
        return text
    cut = text.rfind(" ", 0, width)
    cut = cut if cut > 0 else width
    return text[:cut] + "\n" + text[cut:].strip()


def _beat_points(beat: dict[str, Any], dur: float) -> list[tuple[float, str]]:
    """
    (offset_sec, text) bullet points for a beat: spoken cues when available
    (so bullets appear as they are said), else narration chunks spread evenly.
    """
    cues = [c for c in (beat.get("cues") or []) if str(c.get("text", "")).strip()]
    if cues:
        size = math.ceil(len(cues) / MAX_BULLETS)
        groups = [cues[i : i + size] for i in range(0, len(cues), size)]
        return [
            (float(g[0].get("t", 0.0)), " ".join(str(c["text"]) for c in g))
            for g in groups
        ]

    text = str(beat.get("narration") or beat.get("visual") or "").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?;])\s+", text) if s.strip()]
    chunks: list[str] = []
    for s in sentences:
        words = s.split()
        for i in range(0, len(words), 12):
            chunks.append(" ".join(words[i : i + 12]))
    chunks = chunks[:MAX_BULLETS] or ["Key idea"]
    step = max(0.8, (dur - CLEAR_SEC) / len(chunks))
    return [(CLEAR_SEC + i * step, c) for i, c in enumerate(chunks)]


def build_guaranteed_manim_code(
    topic: str,
    visual_plan: dict[str, Any] | None = None,
) -> str:
    """
    Pre-tested presentation template: per beat, bullets appear on the spoken cues,
    a pointer moves to the current point and earlier points dim — like a teacher
    clicking through a slide. Text only, positive waits, no LaTeX.
    """
    plan = visual_plan or {}
    title = _wrap((plan.get("title") or topic or "Concept").strip(), width=40, max_len=60)
    beats = plan.get("beats") or []
    if not beats:
        beats = [
            {"id": 1, "duration_sec": 6, "narration": topic},
            {"id": 2, "duration_sec": 6, "narration": "Key idea"},
            {"id": 3, "duration_sec": 6, "narration": "Summary"},
        ]

    blocks: list[str] = []
    for i, beat in enumerate(beats[:8]):
        bid = beat.get("id", i + 1)
        try:
            dur = float(beat.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5.0
        dur = max(2.0, dur)
        lines = [f"        # BEAT {bid} (fallback template, {dur:.1f}s)"]
        cursor = 0.0
        if i > 0:
            lines.append(
                "        self.play(*[FadeOut(m) for m in self.mobjects if m is not header], "
                f"run_time={CLEAR_SEC})"
            )
            cursor = CLEAR_SEC
        lines.append("        prev = None")
        for k, (t, text) in enumerate(_beat_points(beat, dur)):
            y = 1.7 - k * 1.2
            gap = t - cursor
            if gap > 0.05:
                lines.append(f"        self.wait({gap:.2f})")
                cursor = t
            lines += [
                f"        b = Text({_py_str('• ' + _wrap(text))}, font_size=30, line_spacing=0.9)",
                "        if b.width > 11.5:",
                "            b.scale_to_fit_width(11.5)",
                f"        b.to_edge(LEFT, buff=1.1).set_y({y:.2f})",
                "        anims = [FadeIn(b, shift=RIGHT * 0.25)]",
                "        if prev is not None:",
                "            anims.append(prev.animate.set_color(GREY_B))",
            ]
            if k == 0:
                lines += [
                    "        pointer.next_to(b, LEFT, buff=0.25)",
                    "        anims.append(FadeIn(pointer))",
                ]
            else:
                lines.append("        anims.append(pointer.animate.next_to(b, LEFT, buff=0.25))")
            lines += [
                f"        self.play(*anims, run_time={REVEAL_SEC})",
                "        prev = b",
            ]
            cursor += REVEAL_SEC
        rest = dur - cursor
        if rest > 1.2:
            lines += [
                "        self.play(Indicate(prev, color=YELLOW, scale_factor=1.04), run_time=0.8)",
            ]
            rest -= 0.8
        lines.append(f"        self.wait({max(0.1, rest):.2f})")
        blocks.append("\n".join(lines) + "\n")

    body = "\n".join(blocks)
    return f'''from manim import *

class Scene(Scene):
    def construct(self):
        header = Text({_py_str(title)}, font_size=40, weight=BOLD).to_edge(UP, buff=0.5)
        if header.width > 12:
            header.scale_to_fit_width(12)
        pointer = Triangle(color=YELLOW, fill_opacity=1).scale(0.12).rotate(-PI / 2)
        self.add(header)
{body}
        self.wait(0.5)
'''
