"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ChalkCanvas } from "@/components/chalkboard/chalk-canvas";
import { useChalkboard } from "@/components/chalkboard/chalkboard-context";
import { ModelSelector } from "@/components/chalkboard/model-selector";
import { NavigateHome } from "@/components/chalkboard/navigate-home";
import { getModelLabel, setPreferredModel } from "@/lib/chalkboard-api";
import {
  PROMPT_MAX_LENGTH,
  PROMPT_MIN_LENGTH,
  validatePrompt,
} from "@/lib/prompt";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Engine = "auto" | "manim" | "remotion";

const ENGINE_OPTIONS: { value: Engine; label: string; note: string }[] = [
  { value: "auto", label: "Auto", note: "Routed automatically" },
  { value: "manim", label: "Manim", note: "Math, equations, LaTeX" },
  {
    value: "remotion",
    label: "Remotion",
    note: "Charts, timelines, infographics",
  },
];

export default function ThreadPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const {
    hydrated,
    getThread,
    setThreadPrompt,
    setThreadModel,
    setThreadDuration,
    startLectureRender,
  } = useChalkboard();
  const thread = id ? getThread(id) : undefined;
  const autoStarted = useRef(false);

  const prompt = thread?.messages.find((m) => m.role === "user")?.content ?? "";
  const [draft, setDraft] = useState(prompt);
  const [engine, setEngine] = useState<Engine>(thread?.engine ?? "auto");

  useEffect(() => {
    setDraft(prompt);
    setEngine(thread?.engine ?? "auto");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, hydrated]); // threads load from storage after mount, so re-sync once hydrated

  // Starter templates auto-kick the pipeline so the first click always renders.
  useEffect(() => {
    if (!hydrated || !thread || !id || autoStarted.current) return;
    if (!thread.autoStart) return;
    if (
      thread.videos.some(
        (v) =>
          v.status === "queued" ||
          v.status === "processing" ||
          v.status === "completed",
      )
    ) {
      autoStarted.current = true;
      return;
    }
    autoStarted.current = true;
    void startLectureRender(id, undefined, {
      duration: thread.duration,
      tier: thread.tier,
      engine: thread.engine,
    });
  }, [hydrated, id, startLectureRender, thread]);

  if (!hydrated) {
    return (
      <div className="flex h-full items-center justify-center text-[11px] text-[var(--muted-2)]">
        Loading…
      </div>
    );
  }

  if (!thread) {
    return hydrated && id ? <NavigateHome /> : null;
  }

  const dirty = draft.trim() !== prompt.trim();
  const canGenerate = draft.trim().length >= PROMPT_MIN_LENGTH;
  const rendering = thread.videos.some(
    (v) => v.status === "queued" || v.status === "processing",
  );

  function generateFromShortcut() {
    if (!canGenerate || rendering) return;
    void startLectureRender(id, draft, {
      duration: thread!.duration,
      tier: thread!.tier,
      engine,
    });
  }

  const selectedEngine = ENGINE_OPTIONS.find((o) => o.value === engine)!;

  return (
    <div className="flex h-full min-h-0 w-full flex-col lg:flex-row">
      <div
        className={cn(
          "flex min-h-0 shrink-0 flex-col border-[var(--chip-line)]",
          "min-h-[38vh] flex-1 lg:h-full lg:w-[min(380px,40vw)] lg:flex-none lg:border-r",
        )}
      >
        <div className="shrink-0 border-b border-[var(--chip-line)] px-4 py-3">
          <p className="mm-label">Prompt</p>
          <h1 className="mt-1 truncate text-[15px] font-semibold tracking-tight text-foreground">
            {thread.title}
          </h1>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
          <div className="flex flex-1 flex-col">
            <label htmlFor="thread-prompt" className="mm-label mb-2 block">
              Topic
            </label>
            <textarea
              id="thread-prompt"
              value={draft}
              maxLength={PROMPT_MAX_LENGTH}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  generateFromShortcut();
                }
              }}
              rows={8}
              className="lime-focus min-h-[140px] flex-1 resize-none rounded-[10px] border border-[var(--chip-line)] bg-[var(--surface)] px-3 py-3 text-[13px] leading-relaxed text-foreground placeholder:text-[var(--muted-2)]"
              placeholder="Describe the lecture…"
            />
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-[var(--muted-2)]">
              <span className="tabular-nums">
                {draft.trim().length}/{PROMPT_MAX_LENGTH}
                {draft.trim().length > 0 &&
                  draft.trim().length < PROMPT_MIN_LENGTH &&
                  ` · min ${PROMPT_MIN_LENGTH}`}
              </span>
              <span className="hidden sm:inline">⌘/Ctrl + ↵ to generate</span>
            </div>
            {dirty && (
              <button
                type="button"
                className="mm-ghost-btn mt-2 self-start px-3 py-1.5 text-[10px]"
                disabled={!validatePrompt(draft).ok}
                onClick={() => {
                  const check = validatePrompt(draft);
                  if (!check.ok) {
                    toast.error(check.error);
                    return;
                  }
                  setThreadPrompt(id, check.prompt);
                }}
              >
                Save prompt
              </button>
            )}
          </div>

          <div className="space-y-2">
            <p className="mm-label">Generation</p>
            <ModelSelector
              model={thread.model}
              duration={thread.duration}
              onModelChange={(m) => {
                setThreadModel(id, m);
                setPreferredModel(m);
              }}
              onDurationChange={(d) => setThreadDuration(id, d)}
            />

            {/* Engine selector */}
            <div className="flex items-center gap-2">
              <Select
                value={engine}
                onValueChange={(v) => setEngine(v as Engine)}
              >
                <SelectTrigger size="sm" className="h-8 min-w-[110px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ENGINE_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-[11px] leading-relaxed text-[var(--muted-2)]">
                {selectedEngine.note}
              </span>
            </div>

            <p className="text-[11px] leading-relaxed text-[var(--muted-2)]">
              {getModelLabel(thread.model)}
              {thread.tier === "tier1"
                ? " · Fast template (~1–2 min)"
                : " · Narration → code → render → merge"}
            </p>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ChalkCanvas
          videos={thread.videos}
          renderDisabled={!canGenerate}
          onRender={async () => {
            await startLectureRender(id, draft, {
              duration: thread.duration,
              tier: thread.tier,
              engine,
            });
          }}
        />
      </div>
    </div>
  );
}
