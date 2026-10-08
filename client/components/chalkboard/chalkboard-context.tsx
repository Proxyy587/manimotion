"use client";

import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useOptimistic,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { useMountEffect } from "@/hooks/use-mount-effect";
import { useSession } from "@/lib/auth-client";
import {
  createLectureJob,
  DEFAULT_LECTURE_MODEL,
  fetchJobStatus,
  sleep,
} from "@/lib/chalkboard-api";
import { validatePrompt } from "@/lib/prompt";
import type {
  Thread,
  ThreadMessage,
  ThreadVideo,
  ThreadVideoStatus,
  VideoStyle,
} from "@/lib/chalkboard-types";
import { normalizeThread, STORAGE_KEY } from "@/lib/chalkboard-types";
import {
  createThreadOnApi,
  deleteThreadOnApi,
  fetchThreadsFromApi,
  patchThreadOnApi,
} from "@/lib/threads/client";

const LEGACY_STORAGE_KEY = "chalkboard-threads-v1";

function uid() {
  return crypto.randomUUID();
}

function truncateTitle(text: string, max = 42) {
  const t = text.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t || "Untitled";
  return t.slice(0, max - 1) + "…";
}

function loadLocalThreads(): Record<string, Thread> {
  if (typeof window === "undefined") return {};
  try {
    let raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object") return {};
    const out: Record<string, Thread> = {};
    for (const [, v] of Object.entries(parsed)) {
      const t = normalizeThread(v);
      if (t) out[t.id] = t;
    }
    return out;
  } catch {
    return {};
  }
}

function saveLocalThreads(map: Record<string, Thread>) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function coerceJobStatus(status: string): ThreadVideoStatus {
  if (
    status === "queued" ||
    status === "processing" ||
    status === "completed" ||
    status === "failed"
  ) {
    return status;
  }
  return "processing";
}

function shortJobTitle(jobId: string) {
  return `Job ${jobId.slice(0, 8)}`;
}

function listToMap(threads: Thread[]): Record<string, Thread> {
  const out: Record<string, Thread> = {};
  for (const t of threads) out[t.id] = t;
  return out;
}

type ChalkboardContextValue = {
  hydrated: boolean;
  synced: boolean;
  threadsById: Record<string, Thread>;
  threadIdsSorted: string[];
  getThread: (id: string) => Thread | undefined;
  createThreadFromPrompt: (
    prompt: string,
    opts?: {
      model?: string;
      duration?: number;
      tier?: "tier1" | "tier2" | "tier3";
      style?: VideoStyle;
      autoStart?: boolean;
    }
  ) => string;
  setThreadPrompt: (threadId: string, content: string) => void;
  deleteThread: (threadId: string) => void;
  setThreadModel: (threadId: string, model: string) => void;
  setThreadDuration: (threadId: string, duration: number | undefined) => void;
  startLectureRender: (
    threadId: string,
    promptOverride?: string,
    opts?: { duration?: number; tier?: "tier1" | "tier2" | "tier3"; style?: VideoStyle }
  ) => Promise<void>;
};

const ChalkboardContext = createContext<ChalkboardContextValue | null>(null);

type OptimisticAction =
  | { type: "upsert"; thread: Thread }
  | { type: "remove"; id: string }
  | {
      type: "patchVideo";
      threadId: string;
      videoId: string;
      patch: Partial<ThreadVideo>;
    };

function reduceThreads(
  state: Record<string, Thread>,
  action: OptimisticAction
): Record<string, Thread> {
  switch (action.type) {
    case "upsert":
      return { ...state, [action.thread.id]: action.thread };
    case "remove": {
      const next = { ...state };
      delete next[action.id];
      return next;
    }
    case "patchVideo": {
      const t = state[action.threadId];
      if (!t) return state;
      return {
        ...state,
        [action.threadId]: {
          ...t,
          videos: t.videos.map((v) =>
            v.id === action.videoId ? { ...v, ...action.patch } : v
          ),
          updatedAt: Date.now(),
        },
      };
    }
    default:
      return state;
  }
}

export function ChalkboardProvider({ children }: { children: ReactNode }) {
  const { data: session, isPending: sessionPending } = useSession();
  const signedIn = Boolean(session?.user);
  const userId = session?.user?.id ?? null;

  const [baseThreads, setBaseThreads] = useState<Record<string, Thread>>({});
  const [optimisticThreads, applyOptimistic] = useOptimistic(
    baseThreads,
    reduceThreads
  );
  const [hydrated, setHydrated] = useState(false);
  const [synced, setSynced] = useState(false);
  const migrating = useRef(false);

  useMountEffect(() => {
    setBaseThreads(loadLocalThreads());
    setHydrated(true);
  });

  useEffect(() => {
    if (!hydrated || sessionPending) return;

    if (!signedIn || !userId) return;

    let cancelled = false;

    async function syncFromCloud() {
      if (migrating.current) return;
      migrating.current = true;
      try {
        const remote = await fetchThreadsFromApi();
        if (cancelled || remote == null) {
          setSynced(true);
          return;
        }

        const remoteMap = listToMap(remote);
        const local = loadLocalThreads();
        const missing = Object.values(local).filter((t) => !remoteMap[t.id]);

        for (const t of missing) {
          const prompt =
            t.messages.find((m) => m.role === "user")?.content ?? t.title;
          try {
            const created = await createThreadOnApi({
              id: t.id,
              title: t.title,
              model: t.model,
              duration: t.duration,
              prompt,
            });
            if (!created) continue;
            remoteMap[created.id] = created;
            for (const v of t.videos) {
              await patchThreadOnApi(created.id, {
                video: { ...v, id: v.id },
              });
            }
          } catch {
            /* keep local copy if migrate fails */
          }
        }

        const refreshed = await fetchThreadsFromApi();
        const finalMap = listToMap(refreshed ?? Object.values(remoteMap));
        if (!cancelled) {
          setBaseThreads(finalMap);
          saveLocalThreads(finalMap);
          setSynced(true);
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(
            e instanceof Error ? e.message : "Could not sync lectures"
          );
          setSynced(true);
        }
      } finally {
        migrating.current = false;
      }
    }

    void syncFromCloud();
    return () => {
      cancelled = true;
    };
  }, [hydrated, sessionPending, signedIn, userId]);

  const threadsById = optimisticThreads;

  const threadIdsSorted = useMemo(() => {
    return Object.keys(threadsById).sort(
      (a, b) => threadsById[b].updatedAt - threadsById[a].updatedAt
    );
  }, [threadsById]);

  const getThread = useCallback(
    (id: string) => threadsById[id],
    [threadsById]
  );

  const patchVideo = useCallback(
    (threadId: string, videoId: string, patch: Partial<ThreadVideo>) => {
      startTransition(() => {
        applyOptimistic({ type: "patchVideo", threadId, videoId, patch });
      });
      setBaseThreads((prev) => {
        const t = prev[threadId];
        if (!t) return prev;
        const next = {
          ...prev,
          [threadId]: {
            ...t,
            videos: t.videos.map((v) =>
              v.id === videoId ? { ...v, ...patch } : v
            ),
            updatedAt: Date.now(),
          },
        };
        saveLocalThreads(next);
        return next;
      });
      if (signedIn) {
        void patchThreadOnApi(threadId, {
          video: { id: videoId, ...patch },
        }).catch(() => toast.error("Failed to sync video status"));
      }
    },
    [applyOptimistic, signedIn]
  );

  const createThreadFromPrompt = useCallback(
    (
      prompt: string,
      opts?: {
        model?: string;
        duration?: number;
        tier?: "tier1" | "tier2" | "tier3";
        style?: VideoStyle;
        autoStart?: boolean;
      }
    ) => {
      const id = uid();
      const now = Date.now();
      const userMsg: ThreadMessage = {
        id: uid(),
        role: "user",
        content: prompt.trim(),
        createdAt: now,
      };
      const thread: Thread = {
        id,
        title: truncateTitle(prompt),
        messages: [userMsg],
        videos: [],
        model: opts?.model?.trim() || DEFAULT_LECTURE_MODEL,
        duration: opts?.duration,
        tier: opts?.tier,
        style: opts?.style,
        autoStart: Boolean(opts?.autoStart),
        updatedAt: now,
      };

      startTransition(() => applyOptimistic({ type: "upsert", thread }));
      setBaseThreads((prev) => {
        const next = { ...prev, [id]: thread };
        saveLocalThreads(next);
        return next;
      });

      if (signedIn) {
        void createThreadOnApi({
          id,
          title: thread.title,
          model: thread.model,
          duration: thread.duration,
          prompt: userMsg.content,
        }).catch(() => toast.error("Failed to save lecture to cloud"));
      }

      return id;
    },
    [applyOptimistic, signedIn]
  );

  const setThreadPrompt = useCallback(
    (threadId: string, content: string) => {
      const text = content.trim();
      if (!text) return;
      const t = baseThreads[threadId] ?? optimisticThreads[threadId];
      if (!t) return;
      const existing = t.messages.find((m) => m.role === "user");
      const userMsg: ThreadMessage = existing
        ? { ...existing, content: text, createdAt: Date.now() }
        : { id: uid(), role: "user", content: text, createdAt: Date.now() };
      const thread: Thread = {
        ...t,
        title: truncateTitle(text),
        messages: [userMsg],
        updatedAt: Date.now(),
      };
      startTransition(() => applyOptimistic({ type: "upsert", thread }));
      setBaseThreads((prev) => {
        const next = { ...prev, [threadId]: thread };
        saveLocalThreads(next);
        return next;
      });
      if (signedIn) {
        void patchThreadOnApi(threadId, {
          title: thread.title,
          prompt: text,
        }).catch(() => toast.error("Failed to sync prompt"));
      }
    },
    [applyOptimistic, baseThreads, optimisticThreads, signedIn]
  );

  const deleteThread = useCallback(
    (threadId: string) => {
      startTransition(() => applyOptimistic({ type: "remove", id: threadId }));
      setBaseThreads((prev) => {
        const next = { ...prev };
        delete next[threadId];
        saveLocalThreads(next);
        return next;
      });
      if (signedIn) {
        void deleteThreadOnApi(threadId).catch(() =>
          toast.error("Failed to delete lecture")
        );
      }
    },
    [applyOptimistic, signedIn]
  );

  const setThreadModel = useCallback(
    (threadId: string, model: string) => {
      const m = model.trim() || DEFAULT_LECTURE_MODEL;
      const t = baseThreads[threadId] ?? optimisticThreads[threadId];
      if (!t) return;
      const thread = { ...t, model: m, updatedAt: Date.now() };
      startTransition(() => applyOptimistic({ type: "upsert", thread }));
      setBaseThreads((prev) => {
        const next = { ...prev, [threadId]: thread };
        saveLocalThreads(next);
        return next;
      });
      if (signedIn) {
        void patchThreadOnApi(threadId, { model: m }).catch(() =>
          toast.error("Failed to sync model")
        );
      }
    },
    [applyOptimistic, baseThreads, optimisticThreads, signedIn]
  );

  const setThreadDuration = useCallback(
    (threadId: string, duration: number | undefined) => {
      const t = baseThreads[threadId] ?? optimisticThreads[threadId];
      if (!t) return;
      const thread = { ...t, duration, updatedAt: Date.now() };
      startTransition(() => applyOptimistic({ type: "upsert", thread }));
      setBaseThreads((prev) => {
        const next = { ...prev, [threadId]: thread };
        saveLocalThreads(next);
        return next;
      });
      if (signedIn) {
        void patchThreadOnApi(threadId, {
          duration: duration ?? null,
        }).catch(() => toast.error("Failed to sync duration"));
      }
    },
    [applyOptimistic, baseThreads, optimisticThreads, signedIn]
  );

  const startLectureRender = useCallback(
    async (
      threadId: string,
      promptOverride?: string,
      opts?: {
        duration?: number;
        tier?: "tier1" | "tier2" | "tier3";
        style?: VideoStyle;
      }
    ) => {
      const override = promptOverride?.trim();
      if (override) {
        const check = validatePrompt(override);
        if (!check.ok) {
          toast.error(check.error ?? "Invalid topic");
          return;
        }
        setThreadPrompt(threadId, check.prompt);
      }

      const live = baseThreads[threadId] ?? getThread(threadId);
      const userContent =
        override ||
        [...(live?.messages ?? [])].reverse().find((m) => m.role === "user")
          ?.content;
      const check = validatePrompt(userContent ?? "");
      if (!live || !check.ok) {
        toast.error(check.error ?? "Add a lecture topic first");
        return;
      }

      const messages = [{ role: "user" as const, content: check.prompt }];
      const model = live.model;
      const duration =
        opts && "duration" in opts ? opts.duration : live.duration;
      const tier = opts?.tier ?? live.tier;
      const style = opts?.style ?? live.style ?? "auto";

      const videoId = uid();
      const placeholder: ThreadVideo = {
        id: videoId,
        title: "Starting…",
        createdAt: Date.now(),
        status: "queued",
        etaDisplay: tier === "tier1" ? "~1–2 min" : "~2–3 min",
        message: "Queued…",
      };

      const th = baseThreads[threadId] ?? getThread(threadId);
      if (!th) return;
      const threadWithVideo = {
        ...th,
        videos: [placeholder, ...th.videos],
        autoStart: false,
        updatedAt: Date.now(),
      };
      startTransition(() =>
        applyOptimistic({ type: "upsert", thread: threadWithVideo })
      );
      setBaseThreads((prev) => {
        const next = { ...prev, [threadId]: threadWithVideo };
        saveLocalThreads(next);
        return next;
      });

      if (signedIn) {
        void patchThreadOnApi(threadId, { video: placeholder }).catch(() => {});
      }

      try {
        const data = await createLectureJob(messages, model, {
          duration,
          tier,
          style,
        });
        patchVideo(threadId, videoId, {
          jobId: data.job_id,
          title: shortJobTitle(data.job_id),
          status: coerceJobStatus(data.status),
          videoUrl: data.video_url ?? undefined,
          cached: Boolean(data.cached),
          error: null,
          message: data.message ?? null,
          etaSeconds: data.eta_seconds ?? null,
          etaDisplay: data.eta_display ?? null,
        });

        if (data.status === "completed") {
          toast.success("Lecture ready");
          return;
        }

        for (;;) {
          await sleep(2500);
          try {
            const st = await fetchJobStatus(data.job_id);
            patchVideo(threadId, videoId, {
              status: coerceJobStatus(st.status),
              videoUrl: st.video_url ?? undefined,
              error: st.error ?? null,
              cached: Boolean(st.cached),
              message: st.message ?? null,
              etaSeconds: st.eta_seconds ?? null,
              etaDisplay: st.eta_display ?? null,
              phase: st.phase ?? null,
            });
            if (st.status === "completed") {
              toast.success("Lecture ready");
              break;
            }
            if (st.status === "failed") {
              toast.error(st.error || "Render failed");
              break;
            }
          } catch (pollErr) {
            const msg =
              pollErr instanceof Error ? pollErr.message : String(pollErr);
            patchVideo(threadId, videoId, { status: "failed", error: msg });
            toast.error(msg);
            break;
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        patchVideo(threadId, videoId, {
          status: "failed",
          error: msg,
          title: "Failed",
        });
        toast.error(msg);
      }
    },
    [
      applyOptimistic,
      baseThreads,
      getThread,
      patchVideo,
      setThreadPrompt,
      signedIn,
    ]
  );

  const value = useMemo(
    (): ChalkboardContextValue => ({
      hydrated: hydrated && (sessionPending ? false : !signedIn || synced),
      synced: !signedIn || synced,
      threadsById,
      threadIdsSorted,
      getThread,
      createThreadFromPrompt,
      setThreadPrompt,
      deleteThread,
      setThreadModel,
      setThreadDuration,
      startLectureRender,
    }),
    [
      hydrated,
      synced,
      signedIn,
      sessionPending,
      threadsById,
      threadIdsSorted,
      getThread,
      createThreadFromPrompt,
      setThreadPrompt,
      deleteThread,
      setThreadModel,
      setThreadDuration,
      startLectureRender,
    ]
  );

  return (
    <ChalkboardContext.Provider value={value}>
      {children}
    </ChalkboardContext.Provider>
  );
}

export function useChalkboard() {
  const ctx = useContext(ChalkboardContext);
  if (!ctx) {
    throw new Error("useChalkboard must be used within ChalkboardProvider");
  }
  return ctx;
}

/** Safe for SiteHeader on docs/pricing (outside chalkboard layout). */
export function useOptionalChalkboard() {
  return useContext(ChalkboardContext);
}
