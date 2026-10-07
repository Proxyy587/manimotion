"use client";

import {
  AlertTriangle,
  Check,
  Download,
  ExternalLink,
  Link2,
  RotateCcw,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import type { ThreadVideo } from "@/lib/chalkboard-types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Phase pipeline
// ---------------------------------------------------------------------------

type PipelineStep = {
  key: string;
  label: string;
};

const PIPELINE: PipelineStep[] = [
  { key: "planning", label: "Planning animation" },
  { key: "generating_audio", label: "Generating narration" },
  { key: "generating_code", label: "Writing animation code" },
  { key: "merging", label: "Rendering & combining" },
  { key: "uploading", label: "Uploading" },
];

// Map every raw phase → pipeline step index (-1 = not started / unknown)
function phaseIndex(phase: string | null | undefined): number {
  switch (phase) {
    case "routing":
    case "planning":
      return 0;
    case "generating_audio":
      return 1;
    case "generating_code":
      return 2;
    case "processing":
    case "merging":
      return 3;
    case "uploading":
      return 4;
    default:
      return -1;
  }
}

// ---------------------------------------------------------------------------
// Elapsed timer hook
// ---------------------------------------------------------------------------

function useElapsedSeconds(startMs: number | undefined, active: boolean): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active || startMs == null) return;
    function tick() {
      setElapsed(Math.max(0, Math.floor((Date.now() - startMs!) / 1000)));
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      clearInterval(id);
      setElapsed(0);
    };
  }, [active, startMs]);

  return active ? elapsed : 0;
}

function formatClock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function timeAgo(ms: number): string {
  const s = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "manimotion-video"
  );
}

// ---------------------------------------------------------------------------
// Overall progress bar (time-based with phase floor; never claims 100% early)
// ---------------------------------------------------------------------------

function RenderProgress({
  elapsed,
  etaSeconds,
  phase,
}: {
  elapsed: number;
  etaSeconds?: number | null;
  phase: string | null | undefined;
}) {
  const step = phaseIndex(phase);
  const byTime = etaSeconds && etaSeconds > 0 ? elapsed / etaSeconds : 0;
  const byPhase = step >= 0 ? (step + 0.5) / PIPELINE.length : 0.03;
  const pct = Math.min(0.95, Math.max(byTime, byPhase, 0.03));
  const slow = Boolean(etaSeconds && elapsed > etaSeconds * 1.25);

  return (
    <div className="w-full max-w-[260px]">
      <div className="mb-1.5 flex items-center justify-between text-[10px] text-[var(--muted-2)]">
        <span>
          {step >= 0 ? `Step ${step + 1} of ${PIPELINE.length}` : "Queued"}
        </span>
        <span className="tabular-nums">{Math.round(pct * 100)}%</span>
      </div>
      <div
        className="h-[3px] overflow-hidden rounded-full bg-[var(--chip-line)]"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct * 100)}
      >
        <div
          className="h-full rounded-full bg-[var(--mm-accent)] transition-[width] duration-700 ease-out"
          style={{ width: `${pct * 100}%` }}
        />
      </div>
      {slow && (
        <p className="mt-2 text-center text-[10px] text-[var(--muted-2)]">
          Taking longer than usual — retries and fallbacks keep it going.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Completed video actions
// ---------------------------------------------------------------------------

function VideoActions({ url, title }: { url: string; title: string }) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  async function download() {
    if (downloading) return;
    setDownloading(true);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(String(res.status));
      const href = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = href;
      a.download = `${slugify(title)}.mp4`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
    } catch {
      window.open(url, "_blank", "noopener,noreferrer");
    } finally {
      setDownloading(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Couldn't copy the link");
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => void download()}
        disabled={downloading}
        className="mm-ghost-btn flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
      >
        <Download className="size-3.5" strokeWidth={1.75} />
        {downloading ? "Downloading…" : "Download MP4"}
      </button>
      <button
        type="button"
        onClick={() => void copyLink()}
        className="mm-ghost-btn flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
      >
        {copied ? (
          <Check className="size-3.5" strokeWidth={1.75} />
        ) : (
          <Link2 className="size-3.5" strokeWidth={1.75} />
        )}
        {copied ? "Copied" : "Copy link"}
      </button>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="mm-ghost-btn flex items-center gap-1.5 px-3 py-1.5 text-[11px]"
      >
        <ExternalLink className="size-3.5" strokeWidth={1.75} />
        Open
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Failed state
// ---------------------------------------------------------------------------

function FailedState({
  error,
  onRetry,
  retryDisabled,
}: {
  error?: string | null;
  onRetry: () => void;
  retryDisabled?: boolean;
}) {
  const full = (error ?? "").trim();
  const firstLine = full.split("\n").find((l) => l.trim()) ?? "";
  const summary =
    firstLine.length > 160 ? `${firstLine.slice(0, 157)}…` : firstLine;
  const hasDetails = full.length > summary.length;

  return (
    <div className="flex size-full items-center justify-center overflow-y-auto p-6">
      <div className="flex w-full max-w-md flex-col items-center gap-3 text-center">
        <span className="flex size-9 items-center justify-center rounded-[10px] border border-red-400/30 bg-red-400/10">
          <AlertTriangle className="size-4 text-red-300" strokeWidth={1.75} />
        </span>
        <p className="text-[13px] font-semibold text-foreground">
          This render didn&apos;t make it
        </p>
        <p className="text-[12px] leading-relaxed text-[var(--muted-text)]">
          {summary || "Generation failed."}
        </p>
        <button
          type="button"
          onClick={onRetry}
          disabled={retryDisabled}
          className="mm-pixel-btn mt-1 flex items-center gap-2 px-4 py-2"
        >
          <RotateCcw className="size-3.5" strokeWidth={1.75} />
          Try again
        </button>
        {hasDetails && (
          <details className="mt-2 w-full text-left">
            <summary className="cursor-pointer text-[11px] text-[var(--muted-2)] hover:text-[var(--ink-soft)]">
              Error details
            </summary>
            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-[8px] border border-[var(--line)] bg-[var(--chip)] p-3 text-[10.5px] leading-relaxed text-[var(--muted-text)]">
              {full}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waveform animation
// ---------------------------------------------------------------------------

const WAVE_BARS = 12;
const WAVE_KEYFRAMES = `
@keyframes wave-bar {
  0%, 100% { transform: scaleY(0.15); opacity: 0.35; }
  50%       { transform: scaleY(1);    opacity: 1;    }
}
@keyframes dot-pulse {
  0%, 100% { opacity: 0.25; transform: scale(0.7); }
  50%       { opacity: 1;   transform: scale(1);   }
}
@keyframes spin-slow {
  to { transform: rotate(360deg); }
}
`;

function WaveformLoader({ active }: { active: boolean }) {
  return (
    <div
      className="flex items-end gap-[3px]"
      style={{ height: 36 }}
      aria-hidden
    >
      {Array.from({ length: WAVE_BARS }).map((_, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full bg-[var(--mm-accent)]"
          style={
            active
              ? {
                  height: "100%",
                  animation: `wave-bar 1.1s ease-in-out infinite`,
                  animationDelay: `${(i * 1.1) / WAVE_BARS}s`,
                  transformOrigin: "bottom",
                }
              : {
                  height: "15%",
                  opacity: 0.2,
                  backgroundColor: "var(--mm-accent)",
                }
          }
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase progress indicator
// ---------------------------------------------------------------------------

function PhaseProgress({
  phase,
  status,
}: {
  phase: string | null | undefined;
  status: "queued" | "processing" | "completed" | "failed";
}) {
  const current = phaseIndex(phase);
  const isRendering = status === "queued" || status === "processing";

  return (
    <ol className="flex flex-col gap-[6px]">
      {PIPELINE.map((step, idx) => {
        const done = isRendering ? idx < current : status === "completed";
        const active = isRendering && idx === current;
        const future = isRendering && idx > current;

        return (
          <li
            key={step.key}
            className={cn(
              "flex items-center gap-2 text-[11px] transition-colors duration-300",
              done && "text-[var(--mm-accent)]",
              active && "text-foreground",
              future && "text-[var(--muted-2)]",
              !isRendering && !done && "text-[var(--muted-2)]",
            )}
          >
            <span className="flex size-[14px] shrink-0 items-center justify-center text-[10px]">
              {done ? (
                "✓"
              ) : active ? (
                <span
                  style={{
                    display: "inline-block",
                    animation: "dot-pulse 1.2s ease-in-out infinite",
                  }}
                >
                  ●
                </span>
              ) : (
                <span className="block size-[5px] rounded-full bg-current opacity-40" />
              )}
            </span>
            <span className={cn(active && "font-medium")}>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Spinner icon
// ---------------------------------------------------------------------------

function SpinnerIcon() {
  return (
    <svg
      aria-hidden
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      style={{ animation: "spin-slow 0.9s linear infinite" }}
      className="shrink-0"
    >
      <circle
        cx="6"
        cy="6"
        r="4.5"
        stroke="currentColor"
        strokeOpacity="0.3"
        strokeWidth="1.5"
      />
      <path
        d="M6 1.5A4.5 4.5 0 0 1 10.5 6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Status label for sidebar
// ---------------------------------------------------------------------------

function StatusBadge({ v }: { v: ThreadVideo }) {
  switch (v.status) {
    case "completed":
      return (
        <span className="text-[var(--mm-accent)]" title="Done">
          ✓
        </span>
      );
    case "failed":
      return (
        <span className="text-red-400" title="Failed">
          ✗
        </span>
      );
    case "processing":
      return (
        <span
          title="Processing"
          style={{ animation: "dot-pulse 1.4s ease-in-out infinite" }}
          className="text-[var(--mm-accent)]"
        >
          ●
        </span>
      );
    case "queued":
    default:
      return (
        <span className="text-[var(--muted-2)]" title="Queued">
          …
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ChalkCanvas({
  videos,
  onRender,
  renderDisabled,
}: {
  videos: ThreadVideo[];
  onRender: () => void | Promise<void>;
  renderDisabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [pickedId, setPickedId] = useState<string | null>(null);

  const resolvedId = useMemo(() => {
    if (pickedId != null && videos.some((v) => v.id === pickedId))
      return pickedId;
    return videos[0]?.id ?? null;
  }, [pickedId, videos]);

  const activeVideo = useMemo(
    () =>
      videos.find((v) => v.id === resolvedId) ??
      videos.find((v) => v.status !== "failed") ??
      videos[0],
    [videos, resolvedId],
  );

  const rendering =
    activeVideo?.status === "queued" || activeVideo?.status === "processing";

  const elapsed = useElapsedSeconds(activeVideo?.createdAt, rendering);
  const elapsedStr = rendering ? `${formatClock(elapsed)} elapsed` : "";

  async function handleRender() {
    if (busy || renderDisabled) return;
    setBusy(true);
    try {
      await onRender();
    } finally {
      setBusy(false);
    }
  }

  const progressCopy = rendering
    ? [
        activeVideo?.message || "Building lecture…",
        activeVideo?.etaDisplay ? `Usually ${activeVideo.etaDisplay}` : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : activeVideo?.status === "completed"
      ? "Video ready"
      : "Waiting to generate";

  const isWorking = busy || rendering;

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      {/* Inject keyframes once */}
      <style>{WAVE_KEYFRAMES}</style>

      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <p className="mm-label">Output</p>
          <p className="mt-0.5 text-[12px] text-[var(--muted-text)]">
            {progressCopy}
          </p>
        </div>
        <button
          type="button"
          onClick={handleRender}
          disabled={isWorking || renderDisabled}
          className="mm-pixel-btn flex items-center gap-2 px-4 py-2"
        >
          {isWorking && <SpinnerIcon />}
          {isWorking ? "Working…" : "Generate"}
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {videos.length > 0 && (
          <aside className="flex w-full shrink-0 gap-1 overflow-x-auto border-b border-[var(--chip-line)] p-2 md:w-[140px] md:flex-col md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r">
            {videos.map((v) => {
              const active = activeVideo?.id === v.id;
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setPickedId(v.id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 px-2 py-2 text-left text-[10px] transition-colors md:w-full",
                    active
                      ? "rounded-[9px] bg-[var(--chip)] text-foreground"
                      : "rounded-[9px] text-[var(--muted-text)] hover:bg-[var(--chip)] hover:text-[var(--ink-soft)]",
                  )}
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="line-clamp-1">{v.title}</span>
                    <span className="text-[9.5px] text-[var(--muted-2)]">
                      {timeAgo(v.createdAt)}
                    </span>
                  </span>
                  <span className="shrink-0 text-[10px]">
                    <StatusBadge v={v} />
                  </span>
                </button>
              );
            })}
          </aside>
        )}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col p-3">
          <div className="mm-panel mm-scan relative flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="dark relative z-[1] min-h-0 flex-1 bg-[#0a0a09] text-foreground">
              {activeVideo?.status === "completed" &&
              activeVideo.videoUrl &&
              activeVideo.videoUrl.length > 0 ? (
                <video
                  key={activeVideo.videoUrl}
                  className="size-full max-h-full object-contain"
                  controls
                  playsInline
                  preload="metadata"
                  src={activeVideo.videoUrl}
                />
              ) : activeVideo?.status === "failed" ? (
                <FailedState
                  error={activeVideo.error}
                  onRetry={() => void handleRender()}
                  retryDisabled={isWorking || renderDisabled}
                />
              ) : (
                // Loading / idle state
                <div className="flex size-full flex-col items-center justify-center gap-5 p-6">
                  {/* Waveform */}
                  <WaveformLoader active={rendering} />

                  {/* Status message */}
                  <p className="max-w-[260px] text-center text-[12px] leading-relaxed text-[var(--muted-text)]">
                    {rendering
                      ? activeVideo?.message ||
                        "Narration → code → render → merge in progress"
                      : "Hit Generate to render this lecture"}
                  </p>

                  {/* Elapsed + ETA row */}
                  {rendering && (
                    <div className="flex items-center gap-3 text-[11px] text-[var(--muted-2)]">
                      {elapsedStr && <span>{elapsedStr}</span>}
                      {elapsedStr && activeVideo?.etaDisplay && (
                        <span className="opacity-40">·</span>
                      )}
                      {activeVideo?.etaDisplay && (
                        <span>Usually {activeVideo.etaDisplay}</span>
                      )}
                    </div>
                  )}

                  {rendering && (
                    <RenderProgress
                      elapsed={elapsed}
                      etaSeconds={activeVideo?.etaSeconds}
                      phase={activeVideo?.phase}
                    />
                  )}

                  {/* Phase progress */}
                  {rendering && (
                    <div className="mt-1 w-full max-w-[200px]">
                      <PhaseProgress
                        phase={activeVideo?.phase}
                        status={activeVideo?.status ?? "queued"}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          {activeVideo?.status === "completed" && activeVideo.videoUrl ? (
            <VideoActions url={activeVideo.videoUrl} title={activeVideo.title} />
          ) : null}
        </div>
      </div>
    </section>
  );
}
