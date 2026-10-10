"use client";

import { Star } from "lucide-react";
import { useEffect, useState } from "react";

import { GITHUB_URL } from "@/lib/github";
import { cn } from "@/lib/utils";

let starsRequest: Promise<number | null> | null = null;

function loadStars(): Promise<number | null> {
  starsRequest ??= fetch("/api/github/stars")
    .then((r) => (r.ok ? r.json() : { stars: null }))
    .then((d: { stars: number | null }) => d.stars)
    .catch(() => null);
  return starsRequest;
}

function formatStars(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0).replace(/\.0$/, "")}k`;
}

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={className} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/** "★ Star | 123" GitHub button, like most open-source project headers. */
export function GitHubStarButton({ className }: { className?: string }) {
  const [stars, setStars] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    void loadStars().then((n) => {
      if (alive) setStars(n);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noreferrer"
      aria-label={stars === null ? "Star on GitHub" : `Star on GitHub (${stars} stars)`}
      className={cn(
        "group inline-flex h-8 items-stretch overflow-hidden rounded-[8px] border border-[var(--chip-line)] bg-[var(--surface)] text-[12px] text-[var(--ink-soft)] transition-colors hover:text-foreground",
        className
      )}
    >
      <span className="flex items-center gap-1.5 px-2 transition-colors group-hover:bg-[var(--chip)]">
        <GitHubMark className="size-3.5" />
        <Star className="size-3 transition-colors group-hover:fill-amber-400 group-hover:text-amber-400" strokeWidth={1.75} />
        <span className="hidden sm:inline">Star</span>
      </span>
      {stars !== null && (
        <span className="flex items-center border-l border-[var(--chip-line)] px-2 font-medium tabular-nums text-foreground">
          {formatStars(stars)}
        </span>
      )}
    </a>
  );
}
