"""
slide_kit — the runtime every generated slide imports (`from slide_kit import *`).

A slide is a `SlideScene`. The pipeline writes the class header (title + BEATS with
measured durations); the LLM writes only `build(self)`. Time can only pass through
`self.beat(i, ...)`, so slide length == LEAD_IN + sum(beat durations) + END_HOLD +
LEAD_OUT by construction, and every narration sentence gets exactly one beat.

A guard runs after every beat and raises LayoutError on overflow / overlapping text,
which the pipeline feeds back to the LLM as a targeted retry.
"""

import os
import re
import textwrap

import numpy as np
from manim import *  # noqa: F401,F403 — re-exported for generated slides
from manim import (
    BOLD,
    DOWN,
    LEFT,
    RIGHT,
    UP,
    YELLOW,
    DecimalNumber,
    Dot,
    FadeIn,
    FadeOut,
    MarkupText,
    MathTex,
    Paragraph,
    ReplacementTransform,
    Scene,
    Tex,
    Text,
    TransformMatchingTex,
    VGroup,
)

BG = "#0E1117"
FONT = os.getenv("SLIDE_FONT", "DejaVu Sans")
FONT_TITLE, FONT_BODY, FONT_MATH = 42, 34, 50
MIN_TEXT, MIN_MATH = 24, 32  # below this a 720p viewer can't read it
STILL_MAX = float(os.getenv("SLIDE_STILL_MAX", "4.0"))  # longest sentence allowed with no motion

# zone -> (center_x, center_y, width, height); everything stays above the caption band
ZONES = {
    "full": (0.0, -0.25, 12.4, 5.4),
    "left": (-3.2, -0.25, 5.9, 5.4),
    "right": (3.2, -0.25, 5.9, 5.4),
}
CAPTION_BAND_Y = -3.2
TEXT_TYPES = (Text, MarkupText, Tex, MathTex, Paragraph, DecimalNumber)


class LayoutError(Exception):
    pass


class SyncError(Exception):
    pass


def wrap(text, width=34):
    return "\n".join(textwrap.wrap(str(text), width)) or str(text)


def body_text(text, width=34, font_size=FONT_BODY, **kwargs):
    """Readable body text in the slide font, wrapped to `width` characters."""
    return Text(wrap(text, width), font=FONT, font_size=font_size, line_spacing=0.9, **kwargs)


def _box(m):  # (left, right, bottom, top)
    return (m.get_left()[0], m.get_right()[0], m.get_bottom()[1], m.get_top()[1])


def _overlap(a, b, pad=0.06):
    return not (
        a[1] + pad <= b[0] or b[1] + pad <= a[0] or a[3] + pad <= b[2] or b[3] + pad <= a[2]
    )


def _label(m):
    return str(
        getattr(m, "text", None) or getattr(m, "tex_string", None) or m.__class__.__name__
    )


def _is_text(m):
    return isinstance(m, TEXT_TYPES) or getattr(m, "is_text_block", False)


def _font_size(m):
    """Rendered font size of a top-level Text/MathTex (after any scaling), else None."""
    if not isinstance(m, (Text, MarkupText, Tex, MathTex)) or m.width < 1e-3:
        return None
    try:
        return float(m.font_size)
    except Exception:
        return None


class SlideScene(Scene):
    SLIDE_TITLE = ""
    BEATS = []  # [{"text": str, "dur": float}] — injected by the pipeline
    LEAD_IN, END_HOLD, LEAD_OUT = 0.5, 1.2, 0.4

    # ---------- time may only pass through beat() ----------
    def play(self, *args, **kwargs):
        if getattr(self, "_locked", False):
            raise SyncError("Do not call self.play() in build(); use self.beat(i, ...)")
        return super().play(*args, **kwargs)

    def wait(self, *args, **kwargs):
        if getattr(self, "_locked", False):
            raise SyncError("Do not call self.wait() in build(); use self.beat(i) to hold")
        return super().wait(*args, **kwargs)

    def add(self, *mobjects):
        if getattr(self, "_locked", False):
            raise SyncError("Do not call self.add() in build(); reveal objects inside self.beat(i, ...)")
        return super().add(*mobjects)

    # ---------- lifecycle ----------
    def construct(self):
        self.camera.background_color = BG
        self._locked = False
        self._next = 0
        self._prev_text_ids = set()
        self._top_limit = 3.8
        self._title = None
        if self.SLIDE_TITLE:
            title = self._title = Text(self.SLIDE_TITLE, font=FONT, font_size=FONT_TITLE, weight=BOLD)
            if title.width > 12.4:
                title.scale_to_fit_width(12.4)
            title.to_edge(UP, buff=0.35)
            title.allow_overlap = True
            self._top_limit = title.get_bottom()[1] - 0.1
            self.play(FadeIn(title, shift=DOWN * 0.2), run_time=self.LEAD_IN)
        else:
            self.wait(self.LEAD_IN)

        self._locked = True
        try:
            self.build()
        finally:
            self._locked = False

        if self._next != len(self.BEATS):
            raise SyncError(
                f"build() used {self._next} of {len(self.BEATS)} beats. Every narration "
                f"sentence needs exactly one self.beat(i, ...) call, in order 0..{len(self.BEATS) - 1}."
            )
        self.wait(self.END_HOLD)
        if self.mobjects:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=self.LEAD_OUT)
        else:
            self.wait(self.LEAD_OUT)

    def build(self):
        raise NotImplementedError

    # ---------- the ONLY way time passes ----------
    def beat(self, i, *animations, fill=False, anim_time=None, rate_func=None):
        if i != self._next:
            raise SyncError(f"Beats must be used in order: expected {self._next}, got {i}")
        if i >= len(self.BEATS):
            raise SyncError(f"Beat {i} does not exist (only {len(self.BEATS)} beats)")
        dur = float(self.BEATS[i]["dur"])
        self._next += 1
        self._locked = False
        try:
            rest = dur
            animations = [a for a in animations if a is not None]
            if animations:
                if fill:
                    t = dur
                else:
                    # Appear calmly (<= 60% of the beat), then let it sit >= 0.8s.
                    t = min(anim_time or 1.2, 2.5, max(dur * 0.6, 0.4), max(dur - 0.8, 0.4))
                kw = {"run_time": t}
                if rate_func is not None:
                    kw["rate_func"] = rate_func
                self.play(*animations, **kw)
                rest = dur - t
            if rest > 0.02:
                self.wait(rest)
        finally:
            self._locked = True
        if not animations and dur > STILL_MAX:
            raise LayoutError(
                f"beat {i} animates nothing for {dur:.1f}s; reveal or highlight what this "
                f"sentence talks about (Indicate, Circumscribe, set_color, FadeIn of a label)"
            )
        self._guard(i)

    # ---------- layout helpers ----------
    def place(self, mob, zone="full", slot=None, max_scale=1.0):
        if zone not in ZONES:
            raise LayoutError(f"Unknown zone {zone!r}; use 'full', 'left' or 'right'")
        cx, cy, w, h = ZONES[zone]
        if slot is not None:
            idx, n = slot
            hs = h / n
            cy = cy + h / 2 - hs * (idx + 0.5)
            h = hs - 0.15
        s = min(w / max(mob.width, 1e-6), h / max(mob.height, 1e-6), max_scale)
        if _is_text(mob) and s < 0.65:
            raise LayoutError(
                f"Too much text for zone '{zone}' ({_label(mob)[:40]!r}); shorten it or use fewer rows"
            )
        mob.scale(s)
        mob.move_to([cx, cy, 0])
        return mob

    def slot_center(self, zone, idx, n):
        cx, cy, w, h = ZONES[zone]
        hs = h / n
        return np.array([cx, cy + h / 2 - hs * (idx + 0.5), 0])

    def bullets(self, items, zone="right", font_size=FONT_BODY, width=None):
        if width is None:
            width = 44 if zone == "full" else 24
        rows = VGroup(
            *[
                VGroup(
                    Dot(radius=0.07, color=YELLOW),
                    body_text(t, width=width, font_size=font_size),
                ).arrange(RIGHT, buff=0.25, aligned_edge=UP)
                for t in items
            ]
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.45)
        for r in rows:
            r.is_text_block = True  # the guard treats each row as one text block
        return self.place(rows, zone)

    def morph(self, a, b, **kw):
        """Safe transform: TransformMatchingTex only between two MathTex/Tex."""
        if isinstance(a, MathTex) and isinstance(b, MathTex):
            return TransformMatchingTex(a, b, **kw)
        return ReplacementTransform(a, b, **kw)

    def freeze(self, *mobs):
        """Stop updaters (always_redraw) so long holds render as cheap static frames."""
        for m in mobs:
            m.clear_updaters()
        return self

    # ---------- guard ----------
    def _guard(self, i):
        errs = []
        mobs = [m for m in self.mobjects if not getattr(m, "allow_overlap", False)]
        for m in mobs:
            if m.width < 1e-3 and m.height < 1e-3:
                continue
            left, right, bottom, top = _box(m)
            if left < -6.8 or right > 6.8 or top > 3.8 or bottom < CAPTION_BAND_Y:
                errs.append(
                    f"beat {i}: {_label(m)[:30]!r} leaves the safe frame "
                    f"(x[{left:.1f},{right:.1f}] y[{bottom:.1f},{top:.1f}])"
                )
            elif top > self._top_limit:
                errs.append(f"beat {i}: {_label(m)[:30]!r} covers the title area (top {top:.1f})")
            size = _font_size(m)
            if size is not None and size < (MIN_MATH if isinstance(m, (MathTex, Tex)) else MIN_TEXT):
                errs.append(f"beat {i}: {_label(m)[:30]!r} is too small to read (font {size:.0f})")
        texty = [m for m in mobs if _is_text(m)]
        for a in range(len(texty)):
            for b in range(a + 1, len(texty)):
                if _overlap(_box(texty[a]), _box(texty[b])):
                    errs.append(
                        f"beat {i}: text overlaps text: {_label(texty[a])[:30]!r} "
                        f"vs {_label(texty[b])[:30]!r}"
                    )
        ids = {id(m) for m in texty}
        new = ids - self._prev_text_ids
        if len(new) > 2:
            errs.append(f"beat {i}: {len(new)} new text objects at once (max 2; one idea per sentence)")
        self._prev_text_ids = ids
        content = [m for m in self.mobjects if m is not self._title and (m.width > 1e-3 or m.height > 1e-3)]
        if not content:
            errs.append(f"beat {i}: the slide is empty below the title; reveal this sentence's on_screen")
        if errs:
            raise LayoutError("; ".join(errs[:5]))


def _looks_like_math(s):
    if any(ch in s for ch in "\\^_"):
        return True
    return "=" in s and not re.search(r"[A-Za-z]{3,}", s)


class FallbackSlide(SlideScene):
    """Deterministic slide built from the storyboard's on_screen phrases; always renders."""

    POINTS = []  # injected: one on-screen phrase (or LaTeX equation) per beat
    MATH_OK = True

    def _row(self, point, width):
        if self.MATH_OK and _looks_like_math(point):
            item = MathTex(re.sub(r"(?<!\\)%", r"\\%", point), font_size=FONT_MATH - 6)
        else:
            item = body_text(point, width=width)
        row = VGroup(Dot(radius=0.07, color=YELLOW), item).arrange(RIGHT, buff=0.3)
        row.is_text_block = True
        return row

    def build(self):
        n = max(1, len(self.BEATS))
        points = (list(self.POINTS) + [""] * n)[:n]
        cx, cy, w, h = ZONES["full"]
        rows = VGroup(*[self._row(p or " ", 44) for p in points])
        for row in rows:
            if row.width > w:  # one long equation must not shrink every other row
                row.scale_to_fit_width(w)
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.42)
        if rows.height > h:
            rows.scale(h / rows.height)
        rows.move_to([cx, cy, 0])
        for row in rows:
            row.is_text_block = True
        for i in range(n):
            dims = [r.animate.set_opacity(0.45) for r in rows[:i]]
            self.beat(i, FadeIn(rows[i], shift=RIGHT * 0.3), *dims, anim_time=1.0)
