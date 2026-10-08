/**
 * Pre-validated homepage / chalkboard starter templates.
 * These are Tier-1 (fast, crash-safe) prompts — keep them short and concrete.
 */

import type { VideoStyle } from "@/lib/chalkboard-types";

export type QualityTier = "tier1" | "tier2" | "tier3";

export type DemoPrompt = {
  n: string;
  label: string;
  prompt: string;
  tier: QualityTier;
  style: VideoStyle;
  /** Target narration/video length hint (seconds). */
  duration: number;
  etaDisplay: string;
};

/** Starters shown on the landing page — must succeed for first-time users. */
export const DEMO_PROMPTS: DemoPrompt[] = [
  {
    n: "01",
    label: "Derivatives",
    prompt:
      "Show how derivatives work with a moving tangent line on y=x^2. Draw axes with x_range=[−3,3] and y_range=[0,9], plot the parabola, add a dot that slides along it, draw its tangent line updating in real time, show the slope value changing. End with d/dx[x^2]=2x boxed.",
    tier: "tier1",
    style: "math",
    duration: 30,
    etaDisplay: "~1–2 min",
  },
  {
    n: "02",
    label: "Integrals",
    prompt:
      "Explain the integral as area under a curve. Draw axes with x_range=[0,3] and y_range=[0,9], plot y=x^2. Show 6 Riemann rectangles filling the area under the curve from x=0 to x=2, then shade the exact area in yellow. Show the formula ∫₀² x² dx = 8/3. Keep it simple — use only FadeIn, Create, Write animations.",
    tier: "tier1",
    style: "math",
    duration: 32,
    etaDisplay: "~1–2 min",
  },
  {
    n: "03",
    label: "F = ma",
    prompt:
      "Explain Newton's Second Law F=ma. Show a block on screen, display Force arrow in blue, mass label in yellow, acceleration arrow in green. Animate the block sliding right when force is applied. End with the boxed formula F=ma in the center.",
    tier: "tier1",
    style: "math",
    duration: 28,
    etaDisplay: "~1–2 min",
  },
  {
    n: "04",
    label: "Euler's identity",
    prompt:
      "Show Euler's identity e^(iπ)+1=0 on the complex plane. Draw a unit circle, show a point rotating by π radians landing on −1, then reveal the full identity. Keep visuals minimal — 4 beats max.",
    tier: "tier1",
    style: "math",
    duration: 35,
    etaDisplay: "~1–2 min",
  },
];

export function etaForTier(tier: QualityTier = "tier2"): string {
  if (tier === "tier1") return "~1–2 min";
  if (tier === "tier3") return "~4–5 min";
  return "~2–3 min";
}
