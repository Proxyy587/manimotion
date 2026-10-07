"use client";

import { ArrowUpRight, BookOpen } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { AccountMenu, HistoryMenu } from "@/components/account/account-menu";
import { useChalkboard } from "@/components/chalkboard/chalkboard-context";
import { ModelSelector } from "@/components/chalkboard/model-selector";
import { LandingMark } from "@/components/landing/landing-mark";
import { SiteHeader } from "@/components/layout/site-header";
import { ThemeToggle } from "@/components/theme/theme-provider";
import { useSession } from "@/lib/auth-client";
import { useMountEffect } from "@/hooks/use-mount-effect";
import {
  DEFAULT_LECTURE_MODEL,
  getPreferredDuration,
  getPreferredModel,
  setPreferredDuration,
  setPreferredModel,
} from "@/lib/chalkboard-api";
import { DEMO_PROMPTS, type DemoPrompt } from "@/lib/demo-prompts";
import {
  PROMPT_MAX_LENGTH,
  PROMPT_MIN_LENGTH,
  validatePrompt,
} from "@/lib/prompt";
import "@/app/landing.css";

const FEATURES = [
  {
    n: "01",
    title: "Beat-sheet sync",
    body: "Visuals, narration, and timing share one plan — audio before render.",
  },
  {
    n: "02",
    title: "Manim + Remotion",
    body: "Math engines and motion graphics, routed automatically or forced.",
  },
  {
    n: "03",
    title: "Public API",
    body: "x-api-key auth, async jobs, BYO R2/S3 storage when you need it.",
  },
];

export default function LandingPage() {
  const router = useRouter();
  const { createThreadFromPrompt } = useChalkboard();
  const { data: session } = useSession();
  const [value, setValue] = useState("");
  const [model, setModel] = useState(DEFAULT_LECTURE_MODEL);
  const [duration, setDuration] = useState<number | undefined>(undefined);
  const [engine, setEngine] = useState<"auto" | "manim" | "remotion">("auto");
  const [busy, setBusy] = useState(false);
  const [prefsReady, setPrefsReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [rootEl, setRootEl] = useState<HTMLDivElement | null>(null);

  useMountEffect(() => {
    setModel(getPreferredModel());
    setDuration(getPreferredDuration());
    setPrefsReady(true);
  });

  useEffect(() => {
    if (!rootEl) return;
    const el = rootEl;
    function onScroll() {
      setScrolled(el.scrollTop > 48);
    }
    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [rootEl]);

  const submit = useCallback(
    (text: string, demo?: DemoPrompt) => {
      const check = validatePrompt(text);
      if (!check.ok) {
        toast.error(check.error ?? "Invalid topic");
        return;
      }
      if (busy) return;
      setBusy(true);
      setPreferredModel(model);
      setPreferredDuration(duration);
      const id = createThreadFromPrompt(check.prompt, {
        model,
        duration: demo?.duration ?? duration,
        tier: demo?.tier ?? "tier2",
        engine: demo?.engine ?? engine,
        autoStart: Boolean(demo),
      });
      setValue("");
      router.push(`/thread/${id}`);
    },
    [busy, createThreadFromPrompt, duration, model, router],
  );

  async function copyCmd() {
    await navigator.clipboard.writeText(
      'curl -X POST "$MANIMOTION_API/video/request" -H "x-api-key: $KEY"',
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div ref={setRootEl} className="lp-root">
      {!scrolled && (
        <div className="lp-corner">
          <span>v0.1</span>
          {!session?.user && <HistoryMenu />}
          {session?.user ? <AccountMenu /> : null}
          <ThemeToggle />
        </div>
      )}

      <SiteHeader section="home" reveal revealed={scrolled} />

      <section className="lp-hero">
        <h1 className="lp-wordmark">manimotion</h1>
        <LandingMark />
        <p className="lp-subtitle">
          STEM lectures as motion graphics — for talks, tutors, and products.
        </p>
        <p className="lp-position">
          Describe a topic. We plan beats, narrate, animate with <b>Manim</b> or{" "}
          <b>Remotion</b>, and sync audio to the cut. Open demo — no account
          required.
        </p>

        <div className="lp-cmd">
          <code>
            curl -X POST https://api.manimotion.dev/video/request -H
            &quot;x-api-key: $KEY&quot;
          </code>
          <button type="button" className="copy" onClick={() => void copyCmd()}>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <div className="lp-cta-row">
          <button
            type="button"
            className="lp-btn primary"
            onClick={() => document.getElementById("landing-input")?.focus()}
          >
            Try the demo
            <ArrowUpRight className="size-3.5" strokeWidth={1.75} />
          </button>
          <Link href="/docs" className="lp-btn">
            <BookOpen className="size-3.5" strokeWidth={1.5} />
            Read the docs
          </Link>
        </div>

        <p className="lp-linkrow">
          <Link href="/docs/quickstart">Quickstart</Link>
          <span className="dot">·</span>
          <Link href="/docs/api">API</Link>
          <span className="dot">·</span>
          <Link href="/settings/api-keys">Get an API key</Link>
        </p>
      </section>

      <hr className="lp-rule" />

      <div className="lp-wrap">
        <article className="lp-article">
          <section id="generate">
            <h2>Generate a lecture</h2>
            <p>
              Type a STEM topic below. Pick a model and length if you want —
              then generate. Threads stay in your browser until you sign in.
            </p>

            <div className="lp-composer">
              <textarea
                id="landing-input"
                value={value}
                maxLength={PROMPT_MAX_LENGTH}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit(value);
                  }
                }}
                placeholder="What should we teach?"
                rows={4}
                aria-label="Lecture topic"
              />
              <div className="lp-composer-bar">
                {prefsReady ? (
                  <ModelSelector
                    model={model}
                    onModelChange={(m) => {
                      setModel(m);
                      setPreferredModel(m);
                    }}
                    duration={duration}
                    onDurationChange={(d) => {
                      setDuration(d);
                      setPreferredDuration(d);
                    }}
                  />
                ) : (
                  <div
                    className="flex h-8 items-center text-[12px] text-[var(--lp-muted-2)]"
                    aria-busy="true"
                  >
                    Loading models…
                  </div>
                )}
                <div className="flex items-center gap-1">
                  {(["auto", "manim", "remotion"] as const).map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setEngine(opt)}
                      className={[
                        "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors",
                        engine === opt
                          ? "border-[var(--chip-line)] bg-[var(--chip)] text-foreground"
                          : "border-transparent text-[var(--lp-muted-2)] hover:text-foreground",
                      ].join(" ")}
                    >
                      {opt === "auto"
                        ? "Auto"
                        : opt.charAt(0).toUpperCase() + opt.slice(1)}
                    </button>
                  ))}
                </div>
                <div className="flex flex-1 items-center justify-end gap-3">
                  <span className="text-[11px] tabular-nums text-[var(--lp-muted-2)]">
                    {value.trim().length}/{PROMPT_MAX_LENGTH}
                  </span>
                  <button
                    type="button"
                    className="lp-btn primary"
                    disabled={
                      !prefsReady ||
                      value.trim().length < PROMPT_MIN_LENGTH ||
                      busy
                    }
                    onClick={() => submit(value)}
                    style={{
                      opacity:
                        !prefsReady ||
                        value.trim().length < PROMPT_MIN_LENGTH ||
                        busy
                          ? 0.4
                          : 1,
                    }}
                  >
                    Generate
                    <ArrowUpRight className="size-3.5" strokeWidth={1.75} />
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section id="starters">
            <h2>Try a starter</h2>
            <p>
              Pre-validated Tier‑1 topics — usually ready in about 1–2 minutes.
            </p>
            <div className="lp-starters">
              {DEMO_PROMPTS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  className="lp-starter"
                  disabled={busy}
                  onClick={() => submit(item.prompt, item)}
                >
                  <div className="n">{item.n}</div>
                  <div className="t">
                    {item.label}
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: 11,
                        opacity: 0.65,
                        fontWeight: 500,
                      }}
                    >
                      {item.etaDisplay}
                    </span>
                  </div>
                  <div className="b">{item.prompt}</div>
                </button>
              ))}
            </div>
          </section>

          <section id="why">
            <h2>Why it works</h2>
            <p>
              Quality comes from planning first — not patching sync after the
              fact.
            </p>
            <div className="lp-features">
              {FEATURES.map((f) => (
                <div key={f.n} className="lp-feature">
                  <div className="n">{f.n}</div>
                  <div className="t">{f.title}</div>
                  <div className="b">{f.body}</div>
                </div>
              ))}
            </div>
          </section>

          <section id="api">
            <h2>Ship with the API</h2>
            <p>
              The demo is for exploring. Production apps call{" "}
              <code
                style={{
                  fontSize: "0.9em",
                  background: "var(--lp-chip)",
                  border: "1px solid var(--lp-line-soft)",
                  borderRadius: 5,
                  padding: "1px 6px",
                }}
              >
                POST /video/request
              </code>{" "}
              with an API key, then poll status until the MP4 URL lands.
            </p>
            <ul>
              <li>Create a key in Settings</li>
              <li>Follow the Quickstart in Docs</li>
              <li>Optional: point storage at your own bucket</li>
            </ul>
            <div
              className="lp-cta-row"
              style={{ justifyContent: "flex-start" }}
            >
              <Link href="/docs/quickstart" className="lp-btn primary">
                Open Quickstart
              </Link>
              <Link href="/docs/api" className="lp-btn">
                API reference
              </Link>
            </div>
          </section>
        </article>

        <footer className="lp-foot">
          <div>
            <Link href="/docs">Docs</Link>
            {" · "}
            <Link href="/pricing">Pricing</Link>
            {" · "}
            <Link href="/settings">Settings</Link>
            {" · "}
            <Link href="/sign-in">Sign in</Link>
          </div>
          <div>
            <span>manimotion</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
