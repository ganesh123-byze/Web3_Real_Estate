/**
 * Resolve API/runtime settings from env + optional generated build artifacts.
 * No hardcoded production backend URL — use Vercel/Render env or generate-runtime-config.
 */
import {
  GENERATED_API_BASE_URL,
  GENERATED_CHAIN_ID,
  GENERATED_EXPLORER_TX_BASE,
} from "@/lib/generated-runtime-env";

export type EstatechainWindowConfig = {
  API_BASE_URL?: string;
  CHAIN_ID?: number;
  EXPLORER_TX_BASE?: string;
};

declare global {
  interface Window {
    __ESTATECHAIN_CONFIG__?: EstatechainWindowConfig;
  }
}

export function stripTrailingSlash(url: string): string {
  return url.trim().replace(/\/$/, "");
}

/** Prefer https for public API URL when env uses http (avoids mixed content on Vercel). */
export function coerceApiBaseUrlForBuild(url: string): string {
  const u = stripTrailingSlash(url);
  if (!u) return u;
  const isLocal = /^(https?:\/\/)(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(u);
  if (!isLocal && process.env.NODE_ENV === "production" && u.startsWith("http://")) {
    return "https://" + u.slice("http://".length);
  }
  return u;
}

export function normalizeApiBaseUrl(base: string): string {
  let b = stripTrailingSlash(base);
  if (!b) return b;
  const isLocal = /^(https?:\/\/)(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(b);
  if (
    !isLocal &&
    typeof window !== "undefined" &&
    window.location.protocol === "https:" &&
    b.startsWith("http://")
  ) {
    b = "https://" + b.slice("http://".length);
  }
  return b;
}

const LOCAL_DEV_API_BASE = "http://127.0.0.1:8000";

function firstNonEmpty(...values: Array<string | undefined | null>): string {
  for (const value of values) {
    const trimmed = stripTrailingSlash(String(value ?? ""));
    if (trimmed) return trimmed;
  }
  return "";
}

/** Build-time API base from Next/Vercel/Render env and optional generated artifact. */
export function resolveBuildTimeApiBaseUrl(): string {
  const fromEnv = firstNonEmpty(
    process.env.NEXT_PUBLIC_API_BASE_URL,
    process.env.API_BASE_URL,
    process.env.BACKEND_URL,
    GENERATED_API_BASE_URL,
  );
  if (fromEnv) return coerceApiBaseUrlForBuild(fromEnv);
  if (process.env.NODE_ENV !== "production") {
    return LOCAL_DEV_API_BASE;
  }
  return "";
}

/** Client override from legacy `runtime-config.js` (`window.__ESTATECHAIN_CONFIG__`). */
export function readWindowInjectedApiBaseUrl(): string {
  if (typeof window === "undefined") return "";
  return stripTrailingSlash(window.__ESTATECHAIN_CONFIG__?.API_BASE_URL ?? "");
}

/**
 * Effective API base for fetch calls.
 * Build-time env (Vercel `NEXT_PUBLIC_*` / generated artifact) wins; legacy
 * `runtime-config.js` is fallback for same-origin Render static hosting.
 */
export function resolveClientApiBaseUrl(buildTimeApiBaseUrl: string): string {
  if (buildTimeApiBaseUrl) return normalizeApiBaseUrl(buildTimeApiBaseUrl);
  const injected = readWindowInjectedApiBaseUrl();
  if (injected) return normalizeApiBaseUrl(injected);
  if (typeof window !== "undefined" && window.location.origin) {
    return stripTrailingSlash(window.location.origin);
  }
  return "";
}

export function resolveBuildTimeChainId(): number {
  const raw =
    process.env.NEXT_PUBLIC_CHAIN_ID ||
    (GENERATED_CHAIN_ID > 0 ? String(GENERATED_CHAIN_ID) : "") ||
    "11155111";
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 11155111;
}

export function resolveExplorerTxBase(): string {
  return (
    process.env.NEXT_PUBLIC_EXPLORER_TX_BASE ||
    GENERATED_EXPLORER_TX_BASE ||
    "https://sepolia.etherscan.io/tx/"
  );
}
