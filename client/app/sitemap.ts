import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/seo";

/** Public indexable routes (auth/settings/api excluded). */
const ROUTES: { path: string; changeFrequency: MetadataRoute.Sitemap[0]["changeFrequency"]; priority: number }[] = [
  { path: "/", changeFrequency: "weekly", priority: 1 },
  { path: "/docs", changeFrequency: "weekly", priority: 0.95 },
  { path: "/docs/quickstart", changeFrequency: "weekly", priority: 0.9 },
  { path: "/docs/api", changeFrequency: "weekly", priority: 0.9 },
  { path: "/docs/storage", changeFrequency: "monthly", priority: 0.85 },
  { path: "/docs/styles", changeFrequency: "monthly", priority: 0.8 },
  { path: "/pricing", changeFrequency: "monthly", priority: 0.85 },
  { path: "/sign-in", changeFrequency: "yearly", priority: 0.4 },
  { path: "/sign-up", changeFrequency: "yearly", priority: 0.5 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ROUTES.map(({ path, changeFrequency, priority }) => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
    changeFrequency,
    priority,
  }));
}
