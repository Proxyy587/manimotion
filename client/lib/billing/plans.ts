/**
 * manimotion pricing — sell renders; differentiate with LLM quality.
 * Bootstrapped: Free API allowed; Pro = Opus-tier models, ~80 renders/mo.
 */

export type PlanId = "FREE" | "HOBBY" | "PRO";

export type PlanDefinition = {
  id: PlanId;
  name: string;
  priceLabel: string;
  priceUsd: number;
  blurb: string;
  rendersLabel: string;
  monthlyRenders: number | null;
  dailyRenders: number | null;
  maxResolution: "720p" | "1080p";
  watermark: boolean;
  apiAccess: boolean;
  /** Short description of the model tier available on this plan. */
  modelTier: string;
  /**
   * OpenRouter model IDs available on this plan (cumulative — includes all
   * models from lower tiers too).
   */
  models: string[];
  features: string[];
  dodoProductIdEnv: string;
  highlighted?: boolean;
};

const FREE_MODELS = [
  "google/gemini-2.5-flash",
  "google/gemini-2.0-flash-001",
  "deepseek/deepseek-v3.2",
];

const HOBBY_MODELS = [
  ...FREE_MODELS,
  "openai/gpt-4o",
  "anthropic/claude-3.5-sonnet",
];

const PRO_MODELS = [...HOBBY_MODELS, "anthropic/claude-opus-4"];

export const PLANS: PlanDefinition[] = [
  {
    id: "FREE",
    name: "Free",
    priceLabel: "$0",
    priceUsd: 0,
    blurb: "Try it free. API included — solid open models.",
    rendersLabel: "3 renders / day",
    monthlyRenders: null,
    dailyRenders: 3,
    maxResolution: "720p",
    watermark: true,
    apiAccess: true,
    modelTier: "Gemini 2.5 Flash · DeepSeek V3.2",
    models: FREE_MODELS,
    dodoProductIdEnv: "",
    features: [
      "3 renders / day",
      "Gemini 2.5 Flash (default)",
      "Gemini 2.0 Flash + DeepSeek V3.2",
      "API access (chalk_* keys)",
      "720p · watermark",
      "Low queue priority",
    ],
  },
  {
    id: "HOBBY",
    name: "Hobby",
    priceLabel: "$9",
    priceUsd: 9,
    blurb: "Stronger models for tutors and weekly explainers.",
    rendersLabel: "40 renders / month",
    monthlyRenders: 40,
    dailyRenders: null,
    maxResolution: "1080p",
    watermark: false,
    apiAccess: true,
    modelTier: "GPT-4o · Claude 3.5 Sonnet",
    models: HOBBY_MODELS,
    dodoProductIdEnv: "DODO_PRODUCT_HOBBY",
    highlighted: true,
    features: [
      "40 renders / month",
      "GPT-4o unlocked",
      "Claude 3.5 Sonnet unlocked (best quality)",
      "All Free models included",
      "1080p · no watermark",
      "API access · commercial use",
      "Faster queue",
    ],
  },
  {
    id: "PRO",
    name: "Pro",
    priceLabel: "$19",
    priceUsd: 19,
    blurb: "Best lecture quality. Opus-class models for shipping products.",
    rendersLabel: "80 renders / month",
    monthlyRenders: 80,
    dailyRenders: null,
    maxResolution: "1080p",
    watermark: false,
    apiAccess: true,
    modelTier: "Claude Opus 4 · all models",
    models: PRO_MODELS,
    dodoProductIdEnv: "DODO_PRODUCT_PRO",
    features: [
      "80 renders / month",
      "Claude Opus 4 unlocked (most capable)",
      "All Hobby + Free models included",
      "No watermark on all renders",
      "Priority queue",
      "Longer videos · higher concurrency",
    ],
  },
];

export function getPlan(id: string | null | undefined): PlanDefinition {
  return PLANS.find((p) => p.id === id) ?? PLANS[0];
}

export function productIdForPlan(plan: PlanId): string | null {
  const def = getPlan(plan);
  if (!def.dodoProductIdEnv) return null;
  const id = process.env[def.dodoProductIdEnv]?.trim();
  return id || null;
}

export function planFromDodoProductId(productId: string): PlanId | null {
  for (const p of PLANS) {
    if (!p.dodoProductIdEnv) continue;
    const envId = process.env[p.dodoProductIdEnv]?.trim();
    if (envId && envId === productId) return p.id;
  }
  return null;
}

/** Rank for comparing plan unlocks */
export const PLAN_RANK: Record<PlanId, number> = {
  FREE: 0,
  HOBBY: 1,
  PRO: 2,
};

export function planAtLeast(
  userPlan: string | null | undefined,
  required: PlanId,
): boolean {
  const u = (userPlan?.toUpperCase() ?? "FREE") as PlanId;
  const userRank = PLAN_RANK[u] ?? 0;
  return userRank >= PLAN_RANK[required];
}
