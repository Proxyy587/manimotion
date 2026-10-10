import { NextResponse } from "next/server";

import { GITHUB_REPO } from "@/lib/github";

const HOUR = 3600_000;
const RETRY_AFTER_FAILURE = 300_000;

let cached: { stars: number | null; expires: number } | null = null;

async function fetchStars(): Promise<number | null> {
  try {
    const token = process.env.GITHUB_TOKEN;
    const res = await fetch(`https://api.github.com/repos/${GITHUB_REPO}`, {
      headers: {
        Accept: "application/vnd.github+json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { stargazers_count?: number };
    return typeof data.stargazers_count === "number" ? data.stargazers_count : null;
  } catch {
    return null;
  }
}

/** Star count for the header badge; cached so visitors never hit GitHub's rate limit. */
export async function GET() {
  if (!cached || cached.expires < Date.now()) {
    const stars = await fetchStars();
    cached = { stars, expires: Date.now() + (stars === null ? RETRY_AFTER_FAILURE : HOUR) };
  }
  return NextResponse.json(
    { stars: cached.stars },
    {
      headers: {
        "Cache-Control":
          cached.stars === null
            ? "public, s-maxage=300"
            : "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    }
  );
}
