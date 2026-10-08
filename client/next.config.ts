import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep Prisma out of the Turbopack/webpack bundle so model delegates
  // (thread, apiKey, …) resolve from the generated Node client at runtime.
  serverExternalPackages: ["@prisma/client", "prisma"],
  async redirects() {
    return [
      { source: "/docs/auth", destination: "/docs/api", permanent: true },
      { source: "/docs/pipeline", destination: "/docs/styles", permanent: true },
      { source: "/docs/engines", destination: "/docs/styles", permanent: true },
      { source: "/docs/contributing", destination: "/docs", permanent: true },
    ];
  },
};

export default nextConfig;
