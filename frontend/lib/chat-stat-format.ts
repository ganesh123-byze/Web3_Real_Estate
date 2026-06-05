import { formatEthText } from "@/lib/utils";

export const CHAT_STAT_MAX_DECIMALS = 3;

/** Format a numeric chat stat with at most three decimal places. */
export function formatChatStatNumber(
  value: number | string | null | undefined,
  maxDecimals: number = CHAT_STAT_MAX_DECIMALS,
): string {
  const raw = String(value ?? "0").trim().replace(/%/g, "").replace(/,/g, "");
  if (!raw) return "0";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  if (parsed === Math.trunc(parsed)) return String(Math.trunc(parsed));
  const fixed = parsed.toFixed(Math.max(0, maxDecimals));
  return fixed.replace(/\.?0+$/, "") || "0";
}

const LONG_DECIMAL_RE = /(?<![\d.])(\d+\.\d{4,})(?![\d])/g;

/** Normalize copilot chat text — trim clumsy long decimals in stats lines. */
export function formatChatStatText(
  text: string,
  maxDecimals: number = CHAT_STAT_MAX_DECIMALS,
): string {
  if (!text) return "";
  const withEth = formatEthText(text);
  return withEth.replace(LONG_DECIMAL_RE, (match) => formatChatStatNumber(match, maxDecimals));
}
