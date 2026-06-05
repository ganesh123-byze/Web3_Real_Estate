"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  BarChart3,
  Clock,
  CreditCard,
  Home,
  Mic,
  PieChart,
  Plus,
  Receipt,
  RotateCcw,
  Send,
  Sparkles,
  Store,
  TrendingUp,
  Users,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { formatChatStatText } from "@/lib/chat-stat-format";
import { cn } from "@/lib/utils";
import { HighlightedAssistantText } from "@/lib/ai/assistant-text";
import { useAgentStore } from "@/lib/ai/agent-store";
import type { AIState } from "@/lib/ai/types";
import { unlockAudio } from "@/lib/ai/voice";
import {
  getQuickActions,
  getRoleFromPath,
  type QuickAction,
} from "@/lib/ai/quick-actions";

const ICON_MAP: Record<string, LucideIcon> = {
  Store,
  PieChart,
  TrendingUp,
  Receipt,
  Plus,
  BarChart3,
  Wallet,
  Users,
  CreditCard,
  Home,
  Clock,
};

/** Soft Figma-like tint per quick-action slot. */
const ACTION_TINTS: { bg: string; border: string; iconBg: string; icon: string }[] = [
  {
    bg: "bg-violet-50/80 dark:bg-gradient-to-br dark:from-[#151a3a] dark:via-[#0b1028] dark:to-[#111629]",
    border: "border-[#4d3bb6] hover:border-[#3f2fa2] dark:border-[#3B309E] dark:hover:border-[#7c6cff]",
    iconBg: "bg-violet-100 dark:bg-gradient-to-br dark:from-[#211a54] dark:to-[#10172f]",
    icon: "text-violet-600 dark:text-[#9b8cff]",
  },
  {
    bg: "bg-cyan-50/80 dark:bg-gradient-to-br dark:from-[#101b36] dark:via-[#08152c] dark:to-[#071f2c]",
    border: "border-[#4ca8a8] hover:border-[#2f8e8e] dark:border-[#2f8e8e] dark:hover:border-[#62d4d4]",
    iconBg: "bg-cyan-100 dark:bg-gradient-to-br dark:from-[#0d3443] dark:to-[#0a1b2f]",
    icon: "text-cyan-600 dark:text-[#5dd5e8]",
  },
  {
    bg: "bg-lime-50/80 dark:bg-gradient-to-br dark:from-[#101d2f] dark:via-[#0b122a] dark:to-[#102412]",
    border: "border-[#20bf1a] hover:border-[#169b12] dark:border-[#20bf1a] dark:hover:border-[#69ef63]",
    iconBg: "bg-lime-100 dark:bg-gradient-to-br dark:from-[#14351b] dark:to-[#0a1f17]",
    icon: "text-lime-600 dark:text-[#7bea70]",
  },
  {
    bg: "bg-orange-50/80 dark:bg-gradient-to-br dark:from-[#1d1b2f] dark:via-[#101226] dark:to-[#27170a]",
    border: "border-[#ef8800] hover:border-[#d97706] dark:border-[#ef8800] dark:hover:border-[#ffad3d]",
    iconBg: "bg-orange-100 dark:bg-gradient-to-br dark:from-[#3d230c] dark:to-[#211827]",
    icon: "text-orange-600 dark:text-[#ffad3d]",
  },
];

const ACTION_SUBTITLES: Record<string, string> = {
  "investor.marketplace": "Explore real estate assets",
  "investor.portfolio": "View your holdings",
  "investor.yield": "Performance analysis",
  "investor.transactions": "Audit your history",
  "owner.create": "List a new asset",
  "owner.analytics": "Portfolio intelligence",
  "owner.rent": "Track rent payouts",
  "owner.investors": "Investor ownership",
  "tenant.pay": "Settle your rent",
  "tenant.rental": "Lease details",
  "tenant.history": "Review payments",
  "tenant.transactions": "Audit your history",
};

function ChatAssistantLogo({
  className,
  variant = "orb",
}: {
  className?: string;
  variant?: "avatar" | "orb";
}) {
  if (variant === "avatar") {
    return (
      <span
        className={cn(
          "relative inline-flex overflow-hidden rounded-full bg-white shadow-[0_5px_16px_-10px_rgba(15,23,42,0.45)] ring-1 ring-slate-200/40 dark:bg-[#070b1a] dark:ring-[#252b4a]",
          className,
        )}
        aria-hidden="true"
      >
        <svg className="h-full w-full" viewBox="0 0 100 100" role="presentation">
          <circle cx="50" cy="50" r="50" fill="white" />
          <g opacity="0.92">
            <circle cx="50" cy="17" r="8.7" fill="#e7a33a" />
            <circle cx="32" cy="30" r="8.3" fill="#f1bd60" />
            <circle cx="66" cy="30" r="8.1" fill="#f29963" />
            <circle cx="19" cy="50" r="8.2" fill="#f5c77d" />
            <circle cx="82" cy="50" r="8.1" fill="#f87171" />
          </g>
          <g fill="none" strokeLinecap="round">
            <circle cx="50" cy="50" r="7.8" stroke="#f3a8e8" strokeWidth="5.2" />
            <circle cx="32" cy="68" r="7.4" stroke="#f7c3cb" strokeWidth="5" />
            <circle cx="66" cy="68" r="7.4" stroke="#f59ac3" strokeWidth="5" />
            <circle cx="50" cy="84" r="7.1" stroke="#efb4f0" strokeWidth="4.8" />
          </g>
        </svg>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "relative inline-flex overflow-hidden rounded-full shadow-[0_10px_24px_-12px_rgba(244,114,182,0.85)]",
        className,
      )}
      aria-hidden="true"
    >
      <svg className="h-full w-full" viewBox="0 0 100 100" role="presentation">
        <defs>
          <radialGradient id="chatLogoGlow" cx="33%" cy="20%" r="70%">
            <stop offset="0%" stopColor="#f8df74" />
            <stop offset="38%" stopColor="#f2b443" />
            <stop offset="66%" stopColor="#fa6f7d" />
            <stop offset="100%" stopColor="#f2a7df" />
          </radialGradient>
          <radialGradient id="chatLogoSheen" cx="30%" cy="20%" r="65%">
            <stop offset="0%" stopColor="rgba(255,255,255,0.38)" />
            <stop offset="48%" stopColor="rgba(255,255,255,0.08)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0)" />
          </radialGradient>
          <pattern id="chatLogoSpeckles" width="3" height="3" patternUnits="userSpaceOnUse">
            <circle cx="0.8" cy="0.8" r="0.28" fill="rgba(255,255,255,0.7)" />
          </pattern>
          <filter id="chatLogoDotShadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="1" stdDeviation="1" floodColor="rgba(148,55,95,0.18)" />
          </filter>
        </defs>
        <circle cx="50" cy="50" r="50" fill="url(#chatLogoGlow)" />
        <circle cx="50" cy="50" r="50" fill="url(#chatLogoSheen)" />
        <circle cx="50" cy="50" r="50" fill="url(#chatLogoSpeckles)" opacity="0.38" />

        <g filter="url(#chatLogoDotShadow)">
          <circle cx="50" cy="24" r="9.2" fill="white" />
          <circle cx="35" cy="36" r="8.2" fill="white" />
          <circle cx="64" cy="36" r="8.2" fill="white" />
          <circle cx="24" cy="51" r="8.2" fill="white" />
          <circle cx="76" cy="51" r="8.2" fill="white" />
          <circle cx="50" cy="53" r="7.2" fill="none" stroke="white" strokeWidth="4.8" />
          <circle cx="35" cy="68" r="6.8" fill="none" stroke="white" strokeWidth="4.5" />
          <circle cx="64" cy="68" r="6.8" fill="none" stroke="white" strokeWidth="4.5" />
          <circle cx="50" cy="82" r="6.4" fill="none" stroke="white" strokeWidth="4.3" />
        </g>
      </svg>
    </span>
  );
}

function AgentActivityText({ state }: { state: AIState }) {
  const label = state === "transcribing" ? "Analyzing" : state === "speaking" ? "Speaking" : "Thinking";
  return (
    <span className="px-1 py-0.5 text-[14px] font-medium text-muted-foreground dark:!text-white">
      {label}
    </span>
  );
}

function AgentActivityDots({ state }: { state: AIState }) {
  const label = state === "transcribing" ? "Agent is analyzing" : "Agent is typing";
  return (
    <div className="flex items-center px-1 py-1 text-muted-foreground">
      <span className="flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-primary/75"
            animate={{ y: [0, -3, 0], opacity: [0.35, 1, 0.35] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.12, ease: "easeInOut" }}
          />
        ))}
      </span>
      <span className="sr-only">{label}</span>
    </div>
  );
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return target.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select";
}

function getStatePill(state: AIState) {
  if (state === "thinking") return { label: "Thinking" };
  if (state === "deploying") return { label: "Deploying" };
  if (state === "transcribing") return { label: "Analyzing" };
  if (state === "listening" || state === "recording")
    return { label: "Listening" };
  if (state === "speaking") return { label: "Speaking" };
  if (state === "error") return { label: "Offline" };
  return { label: "Online" };
}

/** Big quick-action card used on the welcome screen. */
function QuickActionCard({
  action,
  tint,
  onClick,
  disabled,
}: {
  action: QuickAction;
  tint: (typeof ACTION_TINTS)[number];
  onClick: () => void;
  disabled?: boolean;
}) {
  const Icon = ICON_MAP[action.icon] ?? Sparkles;
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      whileHover={{ y: -1 }}
      whileTap={{ scale: 0.985 }}
      className={cn(
        "group flex h-[72px] w-full items-center gap-3 rounded-[10px] border px-4 text-left max-sm:h-[72px] max-sm:gap-3 max-sm:px-4",
        "bg-white/70 backdrop-blur-sm",
        "transition-all hover:-translate-y-0.5 hover:bg-white dark:hover:brightness-110",
        "disabled:cursor-not-allowed disabled:opacity-50",
        tint.bg,
        tint.border,
      )}
    >
      <span
        className={cn(
          "grid h-11 w-11 shrink-0 place-items-center rounded-[10px]",
          tint.iconBg,
        )}
      >
        <Icon className={cn("h-6 w-6", tint.icon)} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold leading-tight tracking-tight text-slate-900 dark:text-slate-100">
          {action.label}
        </span>
        <span className="mt-0.5 block truncate text-[14px] leading-tight text-slate-600 dark:text-slate-400">
          {ACTION_SUBTITLES[action.id] ?? "Ask EstateChain"}
        </span>
      </span>
    </motion.button>
  );
}

function QuickActionChip({
  action,
  tint,
  onClick,
  disabled,
}: {
  action: QuickAction;
  tint: (typeof ACTION_TINTS)[number];
  onClick: () => void;
  disabled?: boolean;
}) {
  const Icon = ICON_MAP[action.icon] ?? Sparkles;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-9 min-w-0 items-center justify-center gap-1.5 rounded-full border bg-white/70 px-2 text-[13px] font-medium text-slate-900 dark:bg-gradient-to-r dark:from-[#141c40]/95 dark:via-[#0b1d2e]/95 dark:to-[#1f1739]/95 dark:text-slate-100",
        "backdrop-blur-sm transition-all max-sm:h-8 max-sm:px-1.5 max-sm:text-[12px]",
        "hover:-translate-y-0.5 hover:bg-white dark:hover:bg-[#101936] disabled:cursor-not-allowed disabled:opacity-50",
        tint.border,
      )}
    >
      <Icon className={cn("h-4 w-4 shrink-0 max-sm:h-3.5 max-sm:w-3.5", tint.icon)} />
      <span className="min-w-0 truncate">{action.label}</span>
    </button>
  );
}

function getMetricTone(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("+") || normalized.includes("yield") || normalized.includes("collected")) {
    return "text-[#2f6f1d] dark:text-[#7bea70]";
  }
  if (normalized.includes("₹") || normalized.includes("$") || normalized.includes("eth") || normalized.includes("%")) {
    return "text-[#3530a3] dark:text-[#9b8cff]";
  }
  return "text-slate-950 dark:text-slate-100";
}

function getChatRoleLabel(role: ReturnType<typeof getRoleFromPath>) {
  if (role === "property_owner") return "Admin";
  if (role === "investor") return "Investor";
  if (role === "tenant") return "Tenant";
  return "Guest";
}

function parseMetricRows(content: string) {
  return content
    .split("\n")
    .map((line) => line.trim().replace(/^[-•]\s+/, ""))
    .map((line) => {
      const [label, ...rest] = line.split(":");
      const value = rest.join(":").trim();
      return value ? { label: label.trim(), value } : null;
    })
    .filter((row): row is { label: string; value: string } => Boolean(row));
}

function extractQuotedItems(value: string) {
  return Array.from(value.matchAll(/"([^"]+)"/g), (match) => match[1].trim()).filter(Boolean);
}

function isLongResponseValue(value: string) {
  return value.length > 56 || value.includes("?") || extractQuotedItems(value).length > 1;
}

function splitSummaryCardContent(content: string): { title: string; body: string } {
  const trimmed = content.trim();
  const lines = trimmed.split("\n");
  const first = lines[0]?.trim() ?? "";
  if (/^(yield & returns summary|investment summary|rent payment summary)$/i.test(first)) {
    return { title: first, body: lines.slice(1).join("\n").trim() };
  }
  return { title: "Yield & returns summary", body: trimmed };
}

function YieldSummaryCard({ content }: { content: string }) {
  const { title, body } = splitSummaryCardContent(content);
  const metrics = parseMetricRows(body).slice(0, 5);
  const heading = /^investment summary$/i.test(title)
    ? "Investment summary"
    : /^rent payment summary$/i.test(title)
      ? "Rent payment summary"
      : "Yield & returns summary";

  return (
    <section className="w-full min-w-0 overflow-hidden rounded-[16px] bg-white px-4 py-3 text-[14px] text-[#1A1A2E] dark:border dark:border-[#1e2947] dark:bg-[#070b1a] dark:text-slate-100">
      <h3 className="mb-2 text-[14px] font-bold text-[#1A1A2E] dark:text-slate-100">{heading}</h3>
      <div className="space-y-1">
        {metrics.map((metric) => (
          <div key={metric.label} className="flex min-w-0 items-baseline justify-between gap-3 leading-snug">
            <span className="min-w-0 break-words text-[#474553] dark:text-slate-400">
              <HighlightedAssistantText text={metric.label} />:
            </span>
            <span className={cn("min-w-0 break-words text-right font-bold", getMetricTone(metric.value))}>
              <HighlightedAssistantText text={metric.value} />
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function PortfolioInsightCard({ content }: { content: string }) {
  const metrics = parseMetricRows(content);
  const totalInvested = metrics.find((row) => /total invested/i.test(row.label))?.value ?? "$142,000";
  const currentValue = metrics.find((row) => /current value/i.test(row.label))?.value ?? "$161,000";
  const overallGain = metrics.find((row) => /overall gain|gain/i.test(row.label))?.value ?? "+ $193";
  const assetRows = [
    { name: "Worli Commercial", detail: "Office Space • 1,200 sqft", value: "+18.2%", subValue: "$82.5L", icon: Store },
    { name: "Powai Residential", detail: "Luxury Condo • 3BHK", value: "+9.4%", subValue: "$55.2L", icon: Home },
    { name: "Thane Industrial", detail: "Warehouse • Plot B-14", value: "+4.1%", subValue: "$24.1L", icon: BarChart3 },
  ];

  return (
    <section className="w-full min-w-0 overflow-hidden rounded-[16px] bg-white pb-10 pt-0 text-[14px] text-[#1A1A2E] dark:border dark:border-[#1e2947] dark:bg-[#070b1a] dark:text-slate-100">
      <div className="min-w-0 px-4 pt-3">
        <div className="mb-3 flex items-center gap-2 font-bold">
          <span className="h-2 w-2 rounded-full bg-[#3B6D11]" />
          <span>Portfolio Insight</span>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-3">
          <div className="min-w-0 rounded-[10px] border border-rose-100 bg-white px-3 py-2 dark:border-[#442337] dark:bg-[#171426]">
            <div className="text-[12px] font-semibold uppercase tracking-wide text-[#8a82c8]">Total Invested</div>
            <div className="mt-1 break-words font-bold text-[#ef7478]">
              <HighlightedAssistantText text={totalInvested} />
            </div>
          </div>
          <div className="min-w-0 rounded-[10px] border border-rose-100 bg-white px-3 py-2 dark:border-[#442337] dark:bg-[#171426]">
            <div className="text-[12px] font-semibold uppercase tracking-wide text-[#8a82c8]">Current Value</div>
            <div className="mt-1 break-words font-bold text-[#ef7478]">
              <HighlightedAssistantText text={currentValue} />
            </div>
          </div>
        </div>

        <div className="mt-3 flex min-w-0 items-center justify-between gap-3 rounded-[10px] border border-rose-100 bg-white px-3 py-2 dark:border-[#442337] dark:bg-[#171426]">
          <div className="min-w-0">
            <div className="text-[12px] font-bold uppercase tracking-wide text-[#1A1A2E] dark:text-slate-100">Overall Gain</div>
            <div className="mt-1 break-words text-[18px] font-bold text-[#ef7478]">
              <HighlightedAssistantText text={overallGain} />
            </div>
          </div>
          <span className="rounded-full bg-[#ef7478] px-3 py-1 text-[12px] font-semibold text-white">+13.5%</span>
        </div>

        <div className="mt-4 text-[12px] font-bold uppercase tracking-[0.18em] text-[#8a82c8]">Asset Breakdown</div>
        <div className="mt-2 space-y-2">
          {assetRows.map((asset) => {
            const Icon = asset.icon;
            return (
              <div key={asset.name} className="flex min-w-0 items-center gap-3 rounded-[10px] bg-[#fffaf3] px-3 py-2 dark:bg-[#090f25]">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[9px] bg-[#fdeed8] text-[#3B309E] dark:bg-[#211a54] dark:text-[#9b8cff]">
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-bold text-[#1A1A2E] dark:text-slate-100">{asset.name}</div>
                  <div className="truncate text-[#474553] dark:text-slate-400">{asset.detail}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-bold text-[#3B6D11]">{asset.value}</div>
                  <div className="text-[#1A1A2E] dark:text-slate-100">{asset.subValue}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function isRichAssistantContent(content: string) {
  const normalizedContent = content.toLowerCase();
  return (
    normalizedContent.includes("yield & returns summary") ||
    normalizedContent.includes("investment summary") ||
    normalizedContent.includes("rent payment summary") ||
    normalizedContent.includes("tokens available") ||
    normalizedContent.includes("price per token") ||
    normalizedContent.includes("investment target:") ||
    normalizedContent.includes("portfolio insight") ||
    normalizedContent.includes("total invested")
  );
}

function normalizeInvestSummaryForCard(content: string): string {
  const normalized = content.trim();
  if (/^investment target:/im.test(normalized)) {
    const body = normalized
      .replace(/^investment target:[^\n]*\n?/im, "")
      .replace(/\nhow many tokens would you like to buy\??\s*$/i, "")
      .trim();
    const firstLine = normalized.match(/^investment target:\s*(.+)$/im)?.[1]?.trim() ?? "";
    const propertyLine = firstLine ? `Property name: ${firstLine}` : "";
    const detailLine = body.split("\n").find((line) => line.includes("—")) ?? body.split("\n")[0] ?? "";
    const parts = detailLine
      .split("—")
      .map((part) => part.trim())
      .filter(Boolean);
    const rows = [propertyLine];
    for (const part of parts) {
      if (/tokens available/i.test(part)) {
        rows.push(`Tokens available: ${part.replace(/tokens available/i, "").trim()}`);
      } else if (/eth per token|per token/i.test(part)) {
        rows.push(`Price per token: ${part.replace(/per token/i, "").trim()}`);
      } else if (/monthly rent/i.test(part)) {
        rows.push(`Monthly rent: ${part.replace(/monthly rent/i, "").trim()}`);
      } else if (!/sold/i.test(part)) {
        rows.push(`Location: ${part}`);
      }
    }
    return ["Investment summary", ...rows.filter(Boolean)].join("\n");
  }
  return normalized;
}

function AssistantMessageContent({ content }: { content: string }) {
  const displayContent = formatChatStatText(content);
  const normalizedContent = displayContent.toLowerCase();
  if (normalizedContent.includes("rent payment summary")) {
    const rentConfirmationPrompt = displayContent
      .match(/\n\n(reply yes[\s\S]*)$/i)?.[1]
      ?.trim();
    const rentCardContent = rentConfirmationPrompt
      ? displayContent.replace(/\n\nreply yes[\s\S]*$/i, "").trim()
      : displayContent;

    return (
      <div className="space-y-3">
        <YieldSummaryCard content={rentCardContent.replace(/^rent payment summary/im, "Rent payment summary")} />
        {rentConfirmationPrompt ? (
          <p className="text-[14px] font-medium text-slate-900 dark:text-slate-100">
            <HighlightedAssistantText text={rentConfirmationPrompt} />
          </p>
        ) : null}
      </div>
    );
  }
  if (
    normalizedContent.includes("yield & returns summary") ||
    normalizedContent.includes("investment summary") ||
    normalizedContent.includes("tokens available") ||
    normalizedContent.includes("price per token") ||
    normalizedContent.includes("investment target:")
  ) {
    const investConfirmationPrompt = displayContent
      .match(/\n\n(reply yes[\s\S]*)$/i)?.[1]
      ?.trim();
    const investCardContent = investConfirmationPrompt
      ? displayContent.replace(/\n\nreply yes[\s\S]*$/i, "").trim()
      : displayContent.replace(/\n\nhow many tokens would you like to buy\??\s*$/i, "").trim();

    return (
      <div className="space-y-3">
        <YieldSummaryCard content={normalizeInvestSummaryForCard(investCardContent)} />
        {/\n\nhow many tokens would you like to buy\??\s*$/i.test(displayContent) ? (
          <p className="text-[14px] font-medium text-slate-900 dark:text-slate-100">
            How many tokens would you like to buy?
          </p>
        ) : null}
        {investConfirmationPrompt ? (
          <p className="text-[14px] font-medium text-slate-900 dark:text-slate-100">
            <HighlightedAssistantText text={investConfirmationPrompt} />
          </p>
        ) : null}
      </div>
    );
  }
  if (normalizedContent.includes("portfolio insight") || normalizedContent.includes("total invested")) {
    return <PortfolioInsightCard content={displayContent} />;
  }

  const blocks = displayContent
    .trim()
    .split(/\n\s*\n/)
    .map((block) => block.split("\n").map((line) => line.trim()).filter(Boolean))
    .filter((block) => block.length > 0);

  const hasStructuredRows = blocks.some((block) =>
    block.some((line) => /^[-•]\s+/.test(line) || /^[^:]{2,48}:\s*\S/.test(line)),
  );

  if (!hasStructuredRows) {
    return (
      <span className="whitespace-pre-wrap">
        <HighlightedAssistantText text={displayContent} />
      </span>
    );
  }

  return (
    <div className="min-w-0 space-y-3 overflow-hidden">
      {blocks.map((lines, blockIndex) => {
        const firstLine = lines[0] ?? "";
        const hasTitle = !/^[-•]\s+/.test(firstLine) && !/^[^:]{2,48}:\s*\S/.test(firstLine);
        const title = hasTitle ? firstLine.replace(/:$/, "") : blockIndex === 0 ? "Summary" : "";
        const rows = hasTitle ? lines.slice(1) : lines;

        return (
          <section key={`${title}-${blockIndex}`} className="min-w-0 space-y-2 overflow-hidden">
            {title && (
              <div className="flex min-w-0 items-center gap-2 text-[14px] font-semibold text-slate-950 dark:text-slate-100">
                <span className="h-2 w-2 rounded-full bg-[#3c7f1f]" />
                <span className="min-w-0 break-words">
                  <HighlightedAssistantText text={title} />
                </span>
              </div>
            )}

            {rows.length > 0 && (
              <div className="min-w-0 space-y-1.5 overflow-hidden">
                {rows.map((rawRow, rowIndex) => {
                  const row = rawRow.replace(/^[-•]\s+/, "");
                  const [label, ...rest] = row.split(":");
                  const value = rest.join(":").trim();

                  if (!value) {
                    return (
                      <div
                        key={`${row}-${rowIndex}`}
                        className="min-w-0 overflow-hidden rounded-[9px] bg-[#fff9f1] px-3 py-1.5 text-[14px] leading-snug text-slate-700 [overflow-wrap:anywhere] dark:bg-[#11172b] dark:text-slate-300"
                      >
                        <HighlightedAssistantText text={row} />
                      </div>
                    );
                  }

                  return (
                    <div
                      key={`${row}-${rowIndex}`}
                      className={cn(
                        "min-w-0 rounded-[9px] bg-gradient-to-r from-[#fff8f4] to-white px-3 py-2 dark:from-[#11172b] dark:to-[#090f25]",
                        isLongResponseValue(value)
                          ? "block"
                          : "flex items-baseline justify-between gap-3",
                      )}
                    >
                      <span className="block min-w-0 break-words text-[14px] leading-snug text-slate-600 dark:text-slate-400">
                        <HighlightedAssistantText text={label.trim()} />:
                      </span>
                      {extractQuotedItems(value).length > 1 ? (
                        <ul className="mt-2 space-y-1 pl-4 text-[14px] font-semibold text-slate-950 dark:text-slate-100">
                          {extractQuotedItems(value).map((item) => (
                            <li key={item} className="list-disc break-words leading-snug">
                              <HighlightedAssistantText text={item} />
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span
                          className={cn(
                            "block min-w-0 break-words text-[14px] font-bold leading-snug",
                            isLongResponseValue(value) ? "mt-1 text-left" : "text-right",
                            getMetricTone(value),
                          )}
                        >
                          <HighlightedAssistantText text={value} />
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

/**
 * Autosizing textarea composer. Single-line by default, grows up to a
 * 4-line ceiling. Enter sends; Shift+Enter inserts a newline.
 */
function ComposerTextarea({
  textareaRef,
  disabled,
  onSubmit,
}: {
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  disabled?: boolean;
  onSubmit: () => void;
}) {
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, 132); // ~4 lines
    el.style.height = `${next}px`;
  }, [textareaRef]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (disabled) return;
      const text = textareaRef.current?.value ?? "";
      if (!text.trim()) return;
      onSubmit();
      // Parent clears value + height; schedule a resize next frame for safety.
      requestAnimationFrame(resize);
    }
  }

  return (
    <textarea
      ref={textareaRef}
      data-ai-chat-input=""
      rows={1}
      onInput={resize}
      onKeyDown={handleKeyDown}
      placeholder="Message EstateChain Copilot…"
      disabled={disabled}
      autoFocus
      className={cn(
        "block w-full resize-none border-0 bg-transparent px-4 py-2.5 text-[14px] leading-[1.5] text-foreground outline-none",
        "placeholder:text-muted-foreground/70",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "scrollbar-thin",
      )}
      style={{ maxHeight: 132 }}
    />
  );
}

export function AIBubble() {
  const router = useRouter();
  const pathname = usePathname();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const restoreComposerFocusRef = useRef(false);
  const store = useAgentStore();
  const { open, messages, state, error, voiceMode, micLevel, aiSpeaking } = store;

  const role = useMemo(() => getRoleFromPath(pathname), [pathname]);
  const quickActions = useMemo(() => getQuickActions(role), [role]);
  const panelTitle = `EstateChain Copilot - ${getChatRoleLabel(role)}`;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, state]);

  useEffect(() => {
    if (open) unlockAudio();
  }, [open]);

  const focusComposer = useCallback(() => {
    if (!open || voiceMode || state === "thinking") return;
    requestAnimationFrame(() => {
      textareaRef.current?.focus({ preventScroll: true });
    });
  }, [open, state, voiceMode]);

  const focusComposerWithText = useCallback((text: string) => {
    if (!open || voiceMode || state === "thinking") return;
    const input = textareaRef.current;
    if (!input || input.disabled) return;
    input.focus({ preventScroll: true });
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    input.setRangeText(text, start, end, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, [open, state, voiceMode]);

  useEffect(() => {
    if (open && !voiceMode) {
      focusComposer();
    }
  }, [focusComposer, open, voiceMode]);

  useEffect(() => {
    if (!open || voiceMode || state === "thinking" || !restoreComposerFocusRef.current) return;
    restoreComposerFocusRef.current = false;
    focusComposer();
  }, [focusComposer, open, state, voiceMode]);

  useEffect(() => {
    if (!open || voiceMode || state === "thinking") return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key.length !== 1 || isEditableTarget(e.target)) return;
      e.preventDefault();
      focusComposerWithText(e.key);
    }

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [focusComposerWithText, open, state, voiceMode]);

  // ESC closes the panel (when open).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") store.setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, store]);

  function submitDraft() {
    const text = textareaRef.current?.value ?? "";
    if (!text.trim() || state === "thinking") return;
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
    restoreComposerFocusRef.current = true;
    void store.send(text, router, { fromVoice: false });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submitDraft();
  }

  function handleQuickAction(action: QuickAction) {
    if (state === "thinking") return;
    restoreComposerFocusRef.current = true;
    focusComposer();
    const createPropertyPrompt =
      "Start a fresh new property listing. Ignore any old create-property draft. Ask me step by step in this exact order: first property name, then location, then total property value in ETH, then token supply, then token symbol, then monthly rent.";
    void store.send(action.prompt, router, {
      fromVoice: false,
      freshSession: action.id === "owner.create",
      apiText: action.id === "owner.create" ? createPropertyPrompt : undefined,
      quickActionId: action.id,
    });
  }

  async function handleVoiceClick() {
    unlockAudio();
    if (voiceMode) {
      store.exitVoiceMode();
    } else {
      await store.enterVoiceMode(router, { role });
    }
  }

  const lastMessages = messages.slice(-40);
  const displayState: AIState = aiSpeaking ? "speaking" : state;
  const pill = getStatePill(displayState);
  const busy = state === "thinking" || state === "deploying";
  const showAgentActivity =
    state === "thinking" || state === "deploying" || state === "transcribing";
  const isSpeaking = aiSpeaking || state === "speaking";
  const isListening = !isSpeaking && (state === "listening" || state === "recording");
  const hasUserConversation = messages.some((m) => m.role === "user");
  const showWelcome = !hasUserConversation;

  return (
    <div
      data-workflow-bubble=""
      className="pointer-events-none fixed bottom-6 right-6 z-[100] flex items-end justify-end"
    >
      <AnimatePresence mode="wait" initial={false}>
        {open ? (
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.97 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "pointer-events-auto relative flex flex-col overflow-hidden",
              showWelcome
                ? "h-[min(640px,calc(100dvh-1rem))] w-[min(600px,calc(100vw-1rem))]"
                : "h-[min(1038px,calc(100dvh-1rem))] w-[min(600px,calc(100vw-1rem))]",
              "rounded-[12px] border border-white/80 bg-[#f1f1f1] text-slate-950 backdrop-blur-2xl dark:border-[#252b4a] dark:bg-gradient-to-br dark:from-[#040817] dark:via-[#060b1d] dark:to-[#091427] dark:text-slate-100",
              "shadow-[0_28px_70px_-30px_rgba(15,23,42,0.55)]",
            )}
            role="dialog"
            aria-label="EstateChain Copilot"
          >
            <div
              className="pointer-events-none absolute inset-0 opacity-90 dark:hidden"
              style={{
                background:
                  "radial-gradient(circle at 18px 18px, rgba(255,255,255,0.8) 1px, transparent 1.5px), radial-gradient(circle at 78% 72%, rgba(125,211,252,0.42), transparent 34%), radial-gradient(circle at 16% 88%, rgba(251,191,36,0.24), transparent 30%), radial-gradient(circle at 58% 82%, rgba(236,72,153,0.12), transparent 38%)",
                backgroundSize: "28px 28px, 100% 100%, 100% 100%, 100% 100%",
              }}
            />
            <div
              className="pointer-events-none absolute inset-0 hidden opacity-95 dark:block"
              style={{
                background:
                  "radial-gradient(circle at 18px 18px, rgba(120,133,180,0.3) 1px, transparent 1.5px), radial-gradient(circle at 76% 70%, rgba(94,187,209,0.24), transparent 35%), radial-gradient(circle at 18% 88%, rgba(248,205,142,0.16), transparent 30%), radial-gradient(circle at 48% 78%, rgba(59,48,158,0.22), transparent 42%), linear-gradient(135deg,#050817 0%,#080d20 44%,#07192a 100%)",
                backgroundSize: "28px 28px, 100% 100%, 100% 100%, 100% 100%, 100% 100%",
              }}
            />

            {/* ─── Header ───────────────────────────────────── */}
            <header className="relative z-10 flex h-12 shrink-0 items-center justify-between border-b border-white/75 bg-white/80 px-4 backdrop-blur dark:border-[#1f2947] dark:bg-[#030815]/90">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="h-2 w-2 shrink-0 rounded-full bg-lime-600" />
                <h2 className="truncate text-[14px] font-semibold leading-none tracking-tight text-slate-900 dark:text-slate-100">
                  {panelTitle}
                </h2>
                <span className="sr-only">{pill.label}</span>
              </div>

              <div className="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => store.clear()}
                  title="Clear conversation"
                  className="grid h-7 w-7 place-items-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-[#11172b] dark:hover:text-slate-100"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => store.setOpen(false)}
                  title="Close (Esc)"
                  className="grid h-7 w-7 place-items-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-[#11172b] dark:hover:text-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </header>

            {/* ─── Transcript ───────────────────────────────── */}
            <div
              ref={scrollRef}
              className="scrollbar-thin relative z-10 flex min-h-0 flex-1 flex-col overflow-y-auto scroll-smooth"
            >
              <div
                className={cn(
                  "flex flex-1 flex-col gap-5 pb-4 max-sm:px-5",
                  showWelcome ? "px-8 pt-16 max-sm:pt-8" : "px-5 pt-5 max-sm:pt-5",
                )}
              >
                {showWelcome ? (
                  <>
                    {/* Hero greeting */}
                    <div className="mx-auto w-[474px] max-w-full">
                      <h3 className="text-[28px] font-semibold leading-[1.15] tracking-[-0.025em] text-slate-950 max-sm:text-[26px] dark:text-slate-100">
                        Welcome back!
                      </h3>
                      <p className="mt-1 text-[28px] font-medium leading-[1.15] tracking-[-0.03em] text-slate-950 max-sm:text-[24px] dark:text-slate-100">
                        What would you like to do today?
                      </p>
                    </div>

                    {quickActions.length > 0 && (
                      <div className="mx-auto mt-10 grid h-[160px] w-[480px] max-w-full grid-cols-2 gap-4 max-sm:mt-7 max-sm:h-auto max-sm:grid-cols-1">
                        {quickActions.map((action, idx) => (
                          <QuickActionCard
                            key={action.id}
                            action={action}
                            tint={ACTION_TINTS[idx % ACTION_TINTS.length]}
                            onClick={() => handleQuickAction(action)}
                            disabled={busy}
                          />
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex w-[560px] max-w-full items-start gap-3 overflow-hidden">
                      <ChatAssistantLogo className="h-8 w-8 shrink-0" variant="avatar" />
                      <div className="min-w-0 max-w-[474px] overflow-hidden rounded-[13px] rounded-tl-[3px] border border-[#dedcf1] bg-white px-4 py-2.5 text-[14px] leading-relaxed text-slate-900 [overflow-wrap:anywhere] dark:border-[#252b4a] dark:bg-[#070b1a] dark:text-slate-100">
                        Welcome back! What would you like to do today?
                      </div>
                    </div>
                    {lastMessages.map((msg, i) => {
                      if (!msg.content && msg.role === "assistant") return null;
                      const isUser = msg.role === "user";
                      const richAssistant = !isUser && isRichAssistantContent(msg.content);
                      return (
                        <div
                          key={i}
                          className={cn(
                            "flex w-[560px] max-w-full items-start gap-3 overflow-hidden",
                            isUser ? "justify-end" : "justify-start",
                          )}
                        >
                          {!isUser && <ChatAssistantLogo className="h-8 w-8 shrink-0" variant="avatar" />}
                          <div
                            className={cn(
                              "min-w-0 overflow-hidden whitespace-pre-wrap text-[14px] leading-relaxed [overflow-wrap:anywhere]",
                              isUser
                                ? "min-h-12 max-w-[78%] rounded-[15px] rounded-br-[3px] border border-rose-200 bg-rose-100/80 px-5 py-2.5 text-slate-900 dark:border-[#5f2b3c] dark:bg-gradient-to-r dark:from-[#351622]/95 dark:to-[#4a1c2b]/95 dark:text-slate-100"
                                : richAssistant
                                  ? "max-w-[516px] flex-1 rounded-none border-0 bg-transparent p-0 text-slate-900 shadow-none"
                                  : "w-fit max-w-[516px] rounded-[16px] rounded-tl-[3px] border border-white bg-white px-4 py-3 text-slate-900 dark:border-[#1e2947] dark:bg-gradient-to-r dark:from-[#071126] dark:to-[#090d1d] dark:text-slate-100",
                            )}
                          >
                            {isUser ? msg.content : <AssistantMessageContent content={msg.content} />}
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}

                <AnimatePresence>
                  {showAgentActivity && !showWelcome && (
                      <motion.div
                        key="agent-typing"
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        className="flex w-[560px] max-w-full items-start gap-3 overflow-hidden"
                      >
                        <ChatAssistantLogo className="h-8 w-8 shrink-0" variant="avatar" />
                        <div className="rounded-[14px] border border-white bg-white px-4 py-2.5 dark:border-[#1e2947] dark:bg-gradient-to-r dark:from-[#071126] dark:to-[#090d1d]">
                          <AgentActivityDots state={state} />
                        </div>
                      </motion.div>
                    )}
                </AnimatePresence>

                {error && (
                  <div className="mt-1 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-[14px] leading-tight text-destructive dark:bg-destructive/15">
                    <span className="font-semibold">Error:</span> {error}
                  </div>
                )}
              </div>
            </div>

            {!voiceMode && !showWelcome && quickActions.length > 0 && (
              <div className="relative z-10 px-5 py-3">
                <div className="mx-auto grid w-[480px] max-w-full min-w-0 grid-cols-4 gap-2">
                  {quickActions.map((action, idx) => (
                    <QuickActionChip
                      key={action.id}
                      action={action}
                      tint={ACTION_TINTS[idx % ACTION_TINTS.length]}
                      onClick={() => handleQuickAction(action)}
                      disabled={busy}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* ─── Footer: voice panel OR composer ────────── */}
            {voiceMode ? (
              <div className="relative z-10 border-t border-border/40 bg-gradient-to-b from-transparent to-primary/[0.04] px-5 py-5 dark:border-[#263250]/80">
                <div className="flex flex-col items-center gap-3">
                  <div className="flex h-10 items-center justify-center gap-[3px]">
                    {isListening ? (
                      [...Array(16)].map((_, i) => (
                        <motion.div
                          key={i}
                          className="w-[2px] rounded-full bg-primary dark:bg-[#8b7cff] dark:shadow-[0_0_8px_rgba(139,124,255,0.65)]"
                          animate={{
                            height: [4, 4 + micLevel * 26, 4],
                            opacity: [0.5, 0.9, 0.5],
                          }}
                          transition={{
                            duration: 0.5 + (i % 4) * 0.08,
                            repeat: Infinity,
                            delay: i * 0.05,
                            ease: "easeInOut",
                          }}
                        />
                      ))
                    ) : isSpeaking ? (
                      [...Array(16)].map((_, i) => (
                        <motion.div
                          key={i}
                          className="w-[2px] rounded-full bg-[hsl(var(--chart-3))] dark:bg-[#a78bfa] dark:shadow-[0_0_8px_rgba(167,139,250,0.7)]"
                          animate={{ height: [6, 22, 6] }}
                          transition={{
                            duration: 0.8,
                            repeat: Infinity,
                            delay: i * 0.06,
                            ease: "easeInOut",
                          }}
                        />
                      ))
                    ) : busy ? (
                      <div className="flex items-center gap-1.5 text-[14px] font-semibold text-muted-foreground dark:!text-white">
                        <motion.span
                          className="inline-block h-1.5 w-1.5 rounded-full bg-warning dark:bg-[#fbbf24]"
                          animate={{ scale: [1, 1.4, 1], opacity: [0.5, 1, 0.5] }}
                          transition={{ duration: 1.2, repeat: Infinity }}
                        />
                        Thinking…
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-[14px] font-semibold text-muted-foreground dark:!text-white">
                        <span className="h-1.5 w-1.5 rounded-full bg-primary dark:bg-[#7c6cff]" />
                        Ready to listen
                      </div>
                    )}
                  </div>

                  <div className="flex min-h-[18px] items-center justify-center text-[14px] font-semibold text-muted-foreground dark:!text-white dark:[text-shadow:0_1px_10px_rgba(255,255,255,0.22)]">
                    {showAgentActivity ? (
                      <AgentActivityText state={state} />
                    ) : isSpeaking ? (
                      "Speaking"
                    ) : isListening ? (
                      "Listening — speak naturally"
                    ) : (
                      "Tap the mic to end voice mode"
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleVoiceClick}
                    className={cn(
                      "grid h-12 w-12 place-items-center rounded-full transition-all",
                      "bg-destructive text-destructive-foreground shadow-lg shadow-destructive/30 hover:bg-destructive/90 hover:shadow-destructive/40 dark:bg-[#5f1f3c] dark:text-white dark:shadow-[0_0_22px_rgba(244,114,182,0.28)]",
                    )}
                    title="Stop voice conversation"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="relative z-10 bg-transparent px-5 pb-7 pt-2 max-sm:pb-5">
                <form
                  name="ai-text-input"
                  onSubmit={handleSubmit}
                  className={cn(
                    "relative mx-auto flex min-h-[42px] w-[480px] max-w-full items-center gap-1 rounded-[12px] border border-cyan-200/80 bg-white dark:border-[#5EBBD1] dark:bg-gradient-to-r dark:from-[#071126] dark:via-[#07192a] dark:to-[#141c40]",
                    "transition-all focus-within:border-cyan-400 dark:focus-within:border-[#5dd5e8]",
                  )}
                >
                  <ComposerTextarea
                    textareaRef={textareaRef}
                    disabled={busy}
                    onSubmit={submitDraft}
                  />

                  <button
                    type="button"
                    onClick={handleVoiceClick}
                    className={cn(
                      "grid h-8 w-8 shrink-0 place-items-center rounded-[10px] text-rose-400 transition-all",
                      "hover:bg-rose-50 hover:text-rose-500 active:scale-[0.96] dark:hover:bg-[#351622] dark:hover:text-rose-300",
                    )}
                    title="Start voice conversation"
                    aria-label="Start voice conversation"
                  >
                    <Mic className="h-4 w-4" />
                  </button>

                  <button
                    type="submit"
                    disabled={busy}
                    className={cn(
                      "mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] transition-all",
                      "bg-orange-300 text-white hover:bg-orange-400 dark:bg-[#f59e0b] dark:hover:bg-[#fbbf24]",
                      "disabled:cursor-not-allowed disabled:opacity-40",
                    )}
                    title="Send"
                    aria-label="Send"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                </form>
              </div>
            )}
          </motion.div>
        ) : (
          /* ─── Orb launcher (only when chat is closed) ─── */
          <motion.button
            key="orb"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.92 }}
            onClick={() => store.setOpen(true)}
            aria-label="Open EstateChain Copilot"
            className={cn(
              "pointer-events-auto group relative grid h-14 w-14 place-items-center rounded-full transition-shadow duration-300",
              "shadow-[0_16px_42px_-16px_rgba(244,114,182,0.65)] hover:shadow-[0_20px_55px_-16px_rgba(168,85,247,0.7)]",
            )}
          >
            <ChatAssistantLogo className="absolute inset-0" />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
