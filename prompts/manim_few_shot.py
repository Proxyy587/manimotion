"""Verified Manim CE patterns injected into the system prompt (few-shot)."""

VERIFIED_MANIM_EXAMPLES = """
═══════════════════════════════════════
VERIFIED WORKING EXAMPLES — COPY THESE PATTERNS
═══════════════════════════════════════

EXAMPLE: Moving tangent line (ValueTracker + always_redraw)
─────────────────────────────────────────────────────
from manim import *
import numpy as np

class Scene(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-3, 3, 1], y_range=[-1, 5, 1],
            x_length=10, y_length=6,
            axis_config={"include_tip": True},
        ).move_to(ORIGIN)
        curve = axes.plot(lambda x: x**2, color=BLUE)
        x_tracker = ValueTracker(-2.0)
        dot = always_redraw(lambda: Dot(
            axes.c2p(x_tracker.get_value(), x_tracker.get_value()**2),
            color=YELLOW,
        ))
        tangent = always_redraw(lambda: axes.plot(
            lambda x: 2 * x_tracker.get_value() * x - x_tracker.get_value() ** 2,
            x_range=[x_tracker.get_value() - 1.5, x_tracker.get_value() + 1.5],
            color=TEAL,
        ))
        slope_label = always_redraw(lambda: MathTex(
            r"m = " + f"{2 * x_tracker.get_value():.1f}",
            font_size=28,
            color=TEAL,
        ).to_corner(DR, buff=0.5))
        self.play(FadeIn(axes), Create(curve), run_time=1.5)
        self.play(FadeIn(dot), Create(tangent), Write(slope_label))
        self.play(x_tracker.animate.set_value(2.0), run_time=4, rate_func=linear)
        self.wait(2)

EXAMPLE: Multi-step equation (ReplacementTransform default; TMT only MathTex↔MathTex)
─────────────────────────────────────────────────────────
        steps = [
            MathTex(r"x^2 - 4x + 4"),
            MathTex(r"x^2 - 4x + 4 = 0"),
            MathTex(r"(x - 2)^2 = 0"),
            MathTex(r"x = 2"),
        ]
        for eq in steps:
            eq.move_to(ORIGIN)
            if eq.width > 10:
                eq.scale_to_fit_width(10)
        current = steps[0]
        self.play(Write(current), run_time=1.5)
        self.wait(1.5)
        for next_eq in steps[1:]:
            self.play(ReplacementTransform(current, next_eq), run_time=1.5)
            self.wait(1.5)
            current = next_eq

EXAMPLE: Safe dynamic label (concatenate raw string + value, not f-string inside MathTex)
─────────────────────────────────────────────────────────────────────────
        t = ValueTracker(0)
        label = always_redraw(lambda: MathTex(
            r"f(x) = " + f"{t.get_value():.2f}",
            font_size=32,
            color=YELLOW,
        ).to_corner(UR, buff=0.5))
"""
