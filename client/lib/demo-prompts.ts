/**
 * Pre-validated homepage / chalkboard starter templates.
 * Length is always automatic — the lesson plan decides how long each topic needs.
 */

import type { VideoStyle } from "@/lib/chalkboard-types";

export type QualityTier = "tier1" | "tier2" | "tier3";

export type DemoPrompt = {
  n: string;
  label: string;
  prompt: string;
  tier: QualityTier;
  style: VideoStyle;
  etaDisplay: string;
};

/** Starters shown on the landing page — must succeed for first-time users. */
export const DEMO_PROMPTS: DemoPrompt[] = [
  {
    n: "01",
    label: "Derivatives",
    prompt:
      "What a derivative really is: the slope of the tangent line on y = x², watching it change as the point moves, ending with d/dx x² = 2x.",
    tier: "tier1",
    style: "math",
    etaDisplay: "~2–4 min",
  },
  {
    n: "02",
    label: "Integrals",
    prompt:
      "The integral as area under a curve: Riemann rectangles under y = x² from 0 to 2 getting thinner until they match the exact area, 8/3.",
    tier: "tier1",
    style: "math",
    etaDisplay: "~2–4 min",
  },
  {
    n: "03",
    label: "Euler's identity",
    prompt:
      "Why e^(iπ) + 1 = 0: a point rotating around the unit circle in the complex plane, landing on −1 after π radians.",
    tier: "tier1",
    style: "math",
    etaDisplay: "~2–4 min",
  },
  {
    n: "04",
    label: "History of the internet",
    prompt:
      "How the internet grew from ARPANET in 1969 to today: the key milestones, how many people are online, and what changed along the way.",
    tier: "tier1",
    style: "auto",
    etaDisplay: "~2–4 min",
  },
];

export function etaForTier(tier: QualityTier = "tier2"): string {
  if (tier === "tier1") return "~2–4 min";
  if (tier === "tier3") return "~4–6 min";
  return "~3–5 min";
}
