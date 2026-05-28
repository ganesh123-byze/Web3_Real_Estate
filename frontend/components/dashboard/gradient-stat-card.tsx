"use client";

import type { LucideIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Accent = "violet" | "mint" | "cyan" | "lavender";
type Graph = "bars" | "line" | "steps" | "dots";

const ACCENTS: Record<Accent, string> = {
  violet: "from-white via-white to-fuchsia-200 dark:from-slate-950 dark:via-slate-950 dark:to-fuchsia-950/85",
  mint: "from-white via-teal-50/75 to-cyan-200 dark:from-slate-950 dark:via-slate-950 dark:to-teal-900/90",
  cyan: "from-white via-sky-50/85 to-blue-300 dark:from-slate-950 dark:via-slate-950 dark:to-blue-900/95",
  lavender: "from-white via-violet-50/85 to-indigo-200 dark:from-slate-950 dark:via-slate-950 dark:to-purple-950/95",
};

const ICON_ACCENTS: Record<Accent, string> = {
  violet: "text-violet-600 bg-violet-100/70 ring-violet-200 dark:text-violet-200 dark:bg-violet-400/15 dark:ring-violet-300/20",
  mint: "text-emerald-700 bg-emerald-100/70 ring-emerald-200 dark:text-emerald-200 dark:bg-emerald-400/15 dark:ring-emerald-300/20",
  cyan: "text-sky-700 bg-sky-100/80 ring-sky-200 dark:text-sky-200 dark:bg-sky-400/15 dark:ring-sky-300/20",
  lavender: "text-indigo-700 bg-indigo-100/80 ring-indigo-200 dark:text-indigo-200 dark:bg-indigo-400/15 dark:ring-indigo-300/20",
};

const BORDER_ACCENTS: Record<Accent, string> = {
  violet: "border-violet-200/80 dark:border-violet-400/20",
  mint: "border-emerald-200/80 dark:border-emerald-400/20",
  cyan: "border-sky-200/90 dark:border-sky-400/20",
  lavender: "border-indigo-200/90 dark:border-indigo-400/20",
};

const TOP_ACCENTS: Record<Accent, string> = {
  violet: "bg-violet-500 dark:bg-violet-400",
  mint: "bg-teal-500 dark:bg-teal-400",
  cyan: "bg-sky-500 dark:bg-sky-400",
  lavender: "bg-indigo-500 dark:bg-indigo-400",
};

const GRAPH_ACCENTS: Record<Accent, string> = {
  violet: "bg-violet-500 dark:bg-violet-300",
  mint: "bg-teal-500 dark:bg-teal-300",
  cyan: "bg-sky-500 dark:bg-sky-300",
  lavender: "bg-indigo-500 dark:bg-indigo-300",
};

const TITLE_ACCENTS: Record<Accent, string> = {
  violet: "text-violet-700 dark:text-violet-200",
  mint: "text-teal-700 dark:text-teal-200",
  cyan: "text-sky-700 dark:text-sky-200",
  lavender: "text-indigo-700 dark:text-indigo-200",
};

const SUB_ACCENTS: Record<Accent, string> = {
  violet: "text-violet-600/75 dark:text-violet-200/65",
  mint: "text-teal-700/75 dark:text-teal-200/65",
  cyan: "text-sky-700/75 dark:text-sky-200/65",
  lavender: "text-indigo-700/75 dark:text-indigo-200/65",
};

const SOFT_GLOWS: Record<Accent, string> = {
  violet: "bg-fuchsia-300/35 dark:bg-fuchsia-500/15",
  mint: "bg-teal-300/40 dark:bg-teal-400/15",
  cyan: "bg-sky-300/45 dark:bg-sky-400/15",
  lavender: "bg-indigo-300/40 dark:bg-indigo-400/15",
};

const GRAPH_BY_ACCENT: Record<Accent, Graph> = {
  violet: "bars",
  mint: "line",
  cyan: "steps",
  lavender: "dots",
};

export function GradientStatCard({
  title,
  value,
  sub,
  icon: Icon,
  loading,
  accent = "violet",
  graph,
  className,
}: {
  title: string;
  value: string;
  sub?: string;
  icon: LucideIcon;
  loading?: boolean;
  accent?: Accent;
  graph?: Graph;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative h-full min-h-36 overflow-hidden rounded-2xl border bg-background/40 p-px shadow-[0_18px_50px_-38px_hsl(var(--foreground)/0.65)]",
        BORDER_ACCENTS[accent],
        className,
      )}
    >
      <div className={cn("relative flex h-full min-h-36 flex-col overflow-hidden rounded-[calc(1rem-1px)] bg-gradient-to-br p-4 text-left", ACCENTS[accent])}>
        <div className={cn("absolute inset-x-0 top-0 h-1", TOP_ACCENTS[accent])} />
        <div className={cn("pointer-events-none absolute -bottom-12 -right-10 h-32 w-32 rounded-full blur-2xl", SOFT_GLOWS[accent])} />
        <div className="pointer-events-none absolute inset-0 bg-white/20 dark:bg-white/[0.03]" />
        <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-white/40 dark:ring-white/10" />
        <div className="relative flex items-start justify-between gap-3">
          <span className={cn("text-[11px] font-semibold uppercase tracking-[0.18em]", TITLE_ACCENTS[accent])}>
            {title}
          </span>
          <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-full shadow-sm ring-1 backdrop-blur", ICON_ACCENTS[accent])}>
            <Icon className="h-4 w-4" />
          </span>
        </div>

        {loading ? (
          <Skeleton className="relative mt-2 h-8 w-28 bg-white/55 dark:bg-muted/45" />
        ) : (
          <span className="relative mt-1.5 truncate text-2xl font-semibold leading-tight tracking-tight text-foreground tabular-nums dark:text-white">
            {value}
          </span>
        )}

        <div className="relative mt-auto h-px w-full bg-foreground/15 dark:bg-white/25" />

        <div className="relative mt-3 flex items-end justify-between gap-3">
          {sub && !loading ? (
            <span className={cn("flex min-w-0 items-center gap-1.5 truncate text-[11px]", SUB_ACCENTS[accent])}>
              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", GRAPH_ACCENTS[accent])} />
              <span className="truncate">{sub}</span>
            </span>
          ) : (
            <span />
          )}
          <MiniGraph graph={graph ?? GRAPH_BY_ACCENT[accent]} barClassName={GRAPH_ACCENTS[accent]} />
        </div>
      </div>
    </div>
  );
}

function MiniGraph({ graph, barClassName }: { graph: Graph; barClassName: string }) {
  if (graph === "line") {
    return (
      <span className="relative h-7 w-12 shrink-0 opacity-60">
        <span className={cn("absolute bottom-1 left-0 h-1.5 w-1.5 rounded-full", barClassName)} />
        <span className={cn("absolute bottom-2 left-2 h-px w-4 rotate-[-24deg]", barClassName)} />
        <span className={cn("absolute bottom-4 left-5 h-1.5 w-1.5 rounded-full", barClassName)} />
        <span className={cn("absolute bottom-3 left-7 h-px w-4 rotate-[28deg]", barClassName)} />
        <span className={cn("absolute bottom-2 right-0 h-1.5 w-1.5 rounded-full", barClassName)} />
      </span>
    );
  }

  if (graph === "steps") {
    return (
      <span className="flex h-7 shrink-0 items-end gap-1 opacity-55">
        {[10, 10, 16, 16, 22, 22, 28].map((height, index) => (
          <span key={index} className={cn("w-1.5 rounded-sm", barClassName)} style={{ height }} />
        ))}
      </span>
    );
  }

  if (graph === "dots") {
    return (
      <span className="grid h-7 shrink-0 grid-cols-4 items-end gap-1 opacity-55">
        {[12, 18, 9, 24, 16, 28, 20, 11].map((height, index) => (
          <span key={index} className={cn("h-1.5 w-1.5 rounded-full", barClassName)} style={{ marginBottom: height / 3 }} />
        ))}
      </span>
    );
  }

  return (
    <span className="flex h-7 shrink-0 items-end gap-1 opacity-55">
      {[8, 12, 16, 11, 20, 24, 28].map((height, index) => (
        <span key={index} className={cn("w-1 rounded-t-full", barClassName)} style={{ height }} />
      ))}
    </span>
  );
}
