/** @type {import('next').NextConfig} */

function stripTrailingSlash(url) {
  return String(url || "").trim().replace(/\/$/, "");
}

/** Vercel often sets BACKEND_URL; Next inlines only NEXT_PUBLIC_* at build time. */
const resolvedApiBaseUrl = stripTrailingSlash(
  process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.API_BASE_URL ||
    process.env.BACKEND_URL ||
    "",
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  env: {
    ...(resolvedApiBaseUrl ? { NEXT_PUBLIC_API_BASE_URL: resolvedApiBaseUrl } : {}),
  },
  async rewrites() {
    return [{ source: "/favicon.ico", destination: "/icon.svg" }];
  },
  async redirects() {
    return [
      { source: "/investor/yield", destination: "/investor", permanent: false },
      { source: "/admin", destination: "/property_owner", permanent: true },
      { source: "/admin/:path*", destination: "/property_owner/:path*", permanent: true },
    ];
  },
};

export default nextConfig;
