"""Guaranteed-working Remotion template when LLM retries are exhausted."""

from __future__ import annotations

import json
import re
from typing import Any


def _clean_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_guaranteed_remotion_code(
    topic: str,
    visual_plan: dict[str, Any] | None = None,
) -> str:
    """
    Pre-tested slide-per-beat composition: text only, clamped interpolate,
    beat durations taken from the (measured) plan so narration stays in sync.
    """
    plan = visual_plan or {}
    title = _clean_text(plan.get("title") or topic or "Overview", 80)
    beats = plan.get("beats") or []
    if not beats:
        beats = [
            {"duration_sec": 6, "visual": topic},
            {"duration_sec": 6, "visual": "Key idea"},
            {"duration_sec": 6, "visual": "Summary"},
        ]

    slides = []
    for i, beat in enumerate(beats[:8]):
        try:
            dur = float(beat.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5.0
        heading = _clean_text(beat.get("visual") or topic, 90)
        body = _clean_text(beat.get("narration") or "", 160)
        slides.append(
            {
                "frames": max(30, int(round(max(1.0, dur) * 30))),
                "heading": heading or title,
                "body": body,
                "index": i + 1,
            }
        )

    slides_json = json.dumps(slides, ensure_ascii=True)
    title_json = json.dumps(title, ensure_ascii=True)
    return f"""import React from 'react';
import {{AbsoluteFill, Easing, Series, interpolate, useCurrentFrame}} from 'remotion';

type Slide = {{frames: number; heading: string; body: string; index: number}};

const TITLE: string = {title_json};
const SLIDES: Slide[] = {slides_json};
const ACCENTS = ['#7C3AED', '#06B6D4', '#F59E0B', '#10B981'];

const SlideView: React.FC<{{slide: Slide; total: number}}> = ({{slide, total}}) => {{
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 20], [0, 1], {{
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  }});
  const bodyIn = interpolate(frame, [12, 32], [0, 1], {{
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }});
  const accent = ACCENTS[(slide.index - 1) % ACCENTS.length];
  return (
    <AbsoluteFill style={{{{justifyContent: 'center', padding: 120}}}}>
      <div style={{{{fontSize: 26, color: '#94A3B8', marginBottom: 24}}}}>
        {{TITLE}} - {{slide.index}}/{{total}}
      </div>
      <div style={{{{width: 120, height: 8, borderRadius: 4, backgroundColor: accent, marginBottom: 32, opacity: enter}}}} />
      <h1
        style={{{{
          fontSize: 64,
          lineHeight: 1.15,
          margin: 0,
          opacity: enter,
          transform: `translateY(${{(1 - enter) * 40}}px)`,
        }}}}
      >
        {{slide.heading}}
      </h1>
      {{slide.body ? (
        <p style={{{{fontSize: 34, lineHeight: 1.4, color: '#CBD5E1', marginTop: 32, opacity: bodyIn}}}}>
          {{slide.body}}
        </p>
      ) : null}}
    </AbsoluteFill>
  );
}};

export const MainComposition: React.FC<{{topic?: string}}> = () => {{
  return (
    <AbsoluteFill style={{{{backgroundColor: '#0B1020', color: 'white', fontFamily: 'Inter, system-ui, sans-serif'}}}}>
      <Series>
        {{SLIDES.map((slide) => (
          <Series.Sequence key={{slide.index}} durationInFrames={{slide.frames}}>
            <SlideView slide={{slide}} total={{SLIDES.length}} />
          </Series.Sequence>
        ))}}
      </Series>
    </AbsoluteFill>
  );
}};
"""
