import { formatUnits } from "ethers";
import {
  CHAT_STAT_MAX_DECIMALS,
  formatChatStatNumber,
} from "@/lib/chat-stat-format";

export const INVEST_DISPLAY_MAX_DECIMALS = CHAT_STAT_MAX_DECIMALS;

const LONG_DECIMAL_RE = /(?<![\d.])(\d+\.\d{4,})(?!\d)/g;

/** Format an ETH amount shown in the manual invest dialog (max 3 decimals). */
export function formatInvestEthAmount(
  raw: string | number | null | undefined,
  maxDecimals: number = INVEST_DISPLAY_MAX_DECIMALS,
): string {
  return formatChatStatNumber(raw, maxDecimals);
}

/** Format wei as ETH for invest dialog stats and validation messages. */
export function formatInvestEthFromWei(
  wei: bigint | string | null | undefined,
  maxDecimals: number = INVEST_DISPLAY_MAX_DECIMALS,
): string {
  try {
    const value =
      typeof wei === "bigint" ? wei : BigInt(String(wei ?? "0").trim() || "0");
    if (value < 0n) return "0";
    return formatChatStatNumber(formatUnits(value, 18), maxDecimals);
  } catch {
    return "0";
  }
}

/** Normalize invest dialog text so embedded ETH numbers never exceed 3 decimals. */
export function formatInvestDialogText(
  text: string,
  maxDecimals: number = INVEST_DISPLAY_MAX_DECIMALS,
): string {
  if (!text) return "";
  return text.replace(LONG_DECIMAL_RE, (match) =>
    formatChatStatNumber(match, maxDecimals),
  );
}
