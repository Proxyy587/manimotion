import type { Metadata } from "next";

export const SITE_URL =
  process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, "") ||
  "https://manimotion.dev";

export const SITE_NAME = "manimotion";

export const SITE_DESCRIPTION =
  "Generate videos from a single prompt. Simple API for developers to create animations, explainers, and educational videos";

export const SITE_TAGLINE =
  "Narrated STEM lecture videos from a single prompt, as an API.";

/** High-intent keywords for search + social discovery */
export const SITE_KEYWORDS = [
  "manimotion",
  "video generation API",
  "generate video from prompt",
  "AI video API",
  "text to video API",
  "educational video API",
  "explainer video generator",
  "STEM video generator",
  "lecture video API",
  "animation API for developers",
  "math animation API",
  "science explainer video",
  "prompt to MP4",
  "async video jobs API",
  "BYO storage R2 S3",
  "Cloudflare R2 video upload",
  "developer video API",
  "narrated lecture video",
  "Bayes theorem video",
  "Fourier series animation",
  "gradient descent visualization",
  "educational content API",
  "tutoring video automation",
  "manimotion.dev",
  "api.manimotion.dev",
];

export const OG_IMAGE_PATH = "/image.png";
export const OG_IMAGE_ALT =
  "manimotion — Generate videos from a single prompt";

export function absoluteUrl(path = "/"): string {
  if (path.startsWith("http")) return path;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${SITE_URL}${p}`;
}

export function pageMetadata({
  title,
  description,
  path = "/",
  keywords = [],
  noIndex = false,
}: {
  title: string;
  description: string;
  path?: string;
  keywords?: string[];
  noIndex?: boolean;
}): Metadata {
  const url = absoluteUrl(path);
  const fullTitle =
    title === SITE_NAME ? SITE_NAME : `${title} · ${SITE_NAME}`;

  return {
    title,
    description,
    keywords: [...SITE_KEYWORDS, ...keywords],
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      locale: "en_US",
      url,
      siteName: SITE_NAME,
      title: fullTitle,
      description,
      images: [
        {
          url: absoluteUrl(OG_IMAGE_PATH),
          width: 1200,
          height: 630,
          alt: OG_IMAGE_ALT,
          type: "image/png",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description,
      images: [absoluteUrl(OG_IMAGE_PATH)],
    },
    robots: noIndex
      ? { index: false, follow: false }
      : { index: true, follow: true },
  };
}

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        logo: {
          "@type": "ImageObject",
          url: absoluteUrl(OG_IMAGE_PATH),
        },
        sameAs: [],
        description: SITE_DESCRIPTION,
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        publisher: { "@id": `${SITE_URL}/#organization` },
        inLanguage: "en-US",
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${SITE_URL}/#app`,
        name: SITE_NAME,
        applicationCategory: "DeveloperApplication",
        operatingSystem: "Web",
        url: SITE_URL,
        description: SITE_DESCRIPTION,
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "USD",
          description: "Free tier with daily limits; API keys in Settings",
        },
        featureList: [
          "Generate narrated STEM lecture videos from a single prompt",
          "Async job API with status polling",
          "Math animations and motion-graphics explainers",
          "Bring-your-own R2 / S3 storage",
          "Simple x-api-key authentication",
        ],
      },
      {
        "@type": "WebAPI",
        name: "manimotion Video API",
        url: "https://api.manimotion.dev",
        documentation: absoluteUrl("/docs"),
        description:
          "HTTP API to create educational animation and explainer videos from text prompts.",
        provider: { "@id": `${SITE_URL}/#organization` },
      },
    ],
  };
}
