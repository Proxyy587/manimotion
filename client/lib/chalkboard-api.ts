import type { PlanId } from "@/lib/billing/plans";
import { PLAN_RANK } from "@/lib/billing/plans";
import type { VideoStyle } from "@/lib/chalkboard-types";

/** Matches `worker.DEFAULT_MODEL` / `schema.chat.ChatRequest`. */
export const DEFAULT_LECTURE_MODEL = "google/gemini-2.5-flash";

export type LectureModelOption = {
  id: string;
  label: string;
  hint: string;
  /** Minimum plan required to select this model. */
  minPlan: PlanId;
  /** Short badge text shown in the selector, e.g. "Fastest". */
  badge?: string;
};

/** OpenRouter-style ids with human labels for the selector. */
export const LECTURE_MODELS: LectureModelOption[] = [
  {
    id: "google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    hint: "Fast · Free+",
    minPlan: "FREE",
    badge: "Fastest",
  },
  {
    id: "deepseek/deepseek-v3.2",
    label: "DeepSeek V3.2",
    hint: "Fast · Free+",
    minPlan: "FREE",
    badge: "Fast",
  },
  {
    id: "openai/gpt-4o",
    label: "GPT-4o",
    hint: "Balanced · Hobby+",
    minPlan: "HOBBY",
    badge: "Balanced",
  },
  {
    id: "anthropic/claude-sonnet-4.5",
    label: "Claude Sonnet 4.5",
    hint: "Highest quality · Hobby+",
    minPlan: "HOBBY",
    badge: "Best quality",
  },
  {
    id: "anthropic/claude-opus-4.1",
    label: "Claude Opus 4.1",
    hint: "Most capable · Pro",
    minPlan: "PRO",
    badge: "Most capable",
  },
];

/** Retired OpenRouter ids that may still sit in saved preferences or API clients. */
const MODEL_ALIASES: Record<string, string> = {
  "anthropic/claude-3.5-sonnet": "anthropic/claude-sonnet-4.5",
  "anthropic/claude-opus-4": "anthropic/claude-opus-4.1",
  "google/gemini-2.0-flash-001": "google/gemini-2.5-flash",
};

export function normalizeModelId(id: string): string {
  const trimmed = id.trim();
  return MODEL_ALIASES[trimmed] ?? trimmed;
}

export const LECTURE_MODEL_OPTIONS = LECTURE_MODELS.map((m) => m.id);

export function allModels(): LectureModelOption[] {
  return LECTURE_MODELS;
}

export function modelsForPlan(
  plan: string | null | undefined,
): LectureModelOption[] {
  const p = (plan?.toUpperCase() ?? "FREE") as PlanId;
  const rank = PLAN_RANK[p] ?? 0;
  return LECTURE_MODELS.filter((m) => PLAN_RANK[m.minPlan] <= rank);
}

export function isModelAllowedForPlan(
  modelId: string,
  plan: string | null | undefined,
): boolean {
  const id = normalizeModelId(modelId);
  const m = LECTURE_MODELS.find((x) => x.id === id);
  if (!m) return false;
  const p = (plan?.toUpperCase() ?? "FREE") as PlanId;
  return (PLAN_RANK[p] ?? 0) >= PLAN_RANK[m.minPlan];
}

export const DURATION_OPTIONS = [
  { value: undefined as number | undefined, label: "Auto length" },
  { value: 30, label: "≈ 30s" },
  { value: 60, label: "≈ 1 min" },
  { value: 90, label: "≈ 90s" },
  { value: 120, label: "≈ 2 min" },
] as const;

const PREF_MODEL_KEY = "manimotion_pref_model";

export function getPreferredModel(): string {
  if (typeof window === "undefined") return DEFAULT_LECTURE_MODEL;
  const raw = localStorage.getItem(PREF_MODEL_KEY)?.trim();
  const id = raw ? normalizeModelId(raw) : "";
  if (id && LECTURE_MODELS.some((m) => m.id === id)) return id;
  return DEFAULT_LECTURE_MODEL;
}

export function setPreferredModel(model: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(PREF_MODEL_KEY, model);
}

export function getModelLabel(id: string): string {
  const normalized = normalizeModelId(id);
  return LECTURE_MODELS.find((m) => m.id === normalized)?.label ?? id;
}

export function getChalkboardApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_CHALKBOARD_API_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  return "http://127.0.0.1:8000";
}

/** User API key from Settings (browser localStorage). */
export function getStoredApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("chalk_api_key");
}

export function setStoredApiKey(key: string | null) {
  if (typeof window === "undefined") return;
  if (key) localStorage.setItem("chalk_api_key", key);
  else localStorage.removeItem("chalk_api_key");
}

function apiHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const key = getStoredApiKey();
  if (key) headers["x-api-key"] = key;
  return headers;
}

export type ApiMessage = { role: string; content: string };

export type JobCreateResponse = {
  job_id: string;
  status: string;
  cached?: boolean;
  video_url?: string | null;
  eta_seconds?: number | null;
  eta_display?: string | null;
  message?: string | null;
  tier?: string | null;
};

export type JobStatusResponse = {
  job_id: string;
  status: string;
  video_url?: string | null;
  error?: string | null;
  cached?: boolean;
  style?: string | null;
  duration?: number | null;
  phase?: string | null;
  message?: string | null;
  eta_seconds?: number | null;
  eta_display?: string | null;
  tier?: string | null;
};

async function readApiError(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as {
      detail?: unknown;
      error?: unknown;
    };
    if (typeof j.error === "string") return j.error;
    const d = j.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d))
      return d
        .map((x) =>
          typeof x === "object" && x && "msg" in x
            ? String((x as { msg: string }).msg)
            : String(x),
        )
        .join("; ");
    return res.statusText || `HTTP ${res.status}`;
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function createLectureJob(
  messages: ApiMessage[],
  model: string,
  opts?: {
    style?: VideoStyle;
    duration?: number;
    tier?: "tier1" | "tier2" | "tier3";
    storage?: { integration_id?: string; inline?: Record<string, unknown> };
  },
): Promise<JobCreateResponse> {
  const prompt =
    [...messages]
      .reverse()
      .find((m) => m.role === "user")
      ?.content?.trim() ||
    messages
      .map((m) => m.content)
      .join("\n")
      .trim();
  if (!prompt) throw new Error("prompt is required");

  const body: Record<string, unknown> = {
    prompt,
    model: normalizeModelId(model) || DEFAULT_LECTURE_MODEL,
    style: opts?.style ?? "auto",
  };
  if (opts?.duration != null) body.duration = opts.duration;
  if (opts?.tier) body.tier = opts.tier;
  if (opts?.storage) body.storage = opts.storage;

  const headers = apiHeaders();
  // Open demo: Next proxy injects CLARITY_API_KEY when the browser has no key.
  const res = await fetch("/api/video/request", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readApiError(res));
  const text = await res.text();
  if (!text.trim()) throw new Error("Empty response from video service");
  try {
    return JSON.parse(text) as JobCreateResponse;
  } catch {
    throw new Error("Invalid JSON from video service");
  }
}

export async function fetchJobStatus(
  jobId: string,
): Promise<JobStatusResponse> {
  const headers = apiHeaders();
  const res = await fetch(`/api/video/status/${encodeURIComponent(jobId)}`, {
    headers,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await readApiError(res));
  const text = await res.text();
  if (!text.trim()) throw new Error("Empty job status response");
  try {
    return JSON.parse(text) as JobStatusResponse;
  } catch {
    throw new Error("Invalid JSON from job status");
  }
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
