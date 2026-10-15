import type { NextConfig } from "next";

// The backend's address (public, not a secret). Empty = demo mode.
const backend = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // The browser only talks to this site. Calls to /api/v1/* are forwarded to the
  // backend, so the sign-in cookie belongs to this site (works on any deployment).
  async rewrites() {
    return backend ? [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }] : [];
  },
};

export default nextConfig;
