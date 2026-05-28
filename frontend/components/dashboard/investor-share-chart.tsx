"use client";

import { useState, type MouseEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { shortAddress } from "@/lib/utils";
import type { Property } from "@/lib/types";

type PreviewBreakdownItem = {
  investor: string;
  payout_wei: number;
  payout_eth: string;
  ownership_bps: number;
  ownership_pct: number;
};

type PreviewResponse = {
  property_id: number;
  property_name: string;
  monthly_rent_wei: string;
  investor_count: number;
  breakdown: PreviewBreakdownItem[];
};

type OwnershipChartItem = PreviewBreakdownItem & {
  share_pct: number;
  isUnallocated?: boolean;
};

type DonutHover = {
  key: string;
  label: string;
  value: string;
  x: number;
  y: number;
  color: string;
};

const OWNERSHIP_COLORS = [
  "hsl(246 78% 59%)",
  "hsl(181 84% 40%)",
  "hsl(222 74% 42%)",
  "hsl(262 80% 64%)",
];

function getOwnershipColor(index: number, isUnallocated?: boolean) {
  return isUnallocated ? "hsl(var(--muted))" : OWNERSHIP_COLORS[index % OWNERSHIP_COLORS.length];
}

export function InvestorShareChart({ property }: { property: Property | null }) {
  const enabled = !!property?.id && !!property?.token_address;
  const { data, isLoading, error } = useQuery({
    queryKey: ["preview-distribution", property?.id],
    queryFn: () => api.get<PreviewResponse>(`/tenant/preview-distribution/${property?.id}`),
    enabled,
    retry: false,
    refetchInterval: 20_000,
  });

  const items = data?.breakdown ?? [];
  const total = items.reduce((acc, it) => acc + (it.ownership_pct || 0), 0);
  const headerName = property?.name ?? "Investor Ownership";
  const shareScale = total > 0 && total <= 1 ? 100 : 1;
  const allocatedShare = Math.min(100, total * shareScale);
  const ownershipChartItems: OwnershipChartItem[] = items.map((it) => ({
    ...it,
    share_pct: it.ownership_pct * shareScale,
  }));
  const unallocatedShare = Math.max(0, 100 - allocatedShare);
  const chartItems: OwnershipChartItem[] =
    unallocatedShare > 0
      ? [
          ...ownershipChartItems,
          {
            investor: "Unallocated",
            payout_wei: 0,
            payout_eth: "0",
            ownership_bps: 0,
            ownership_pct: 0,
            share_pct: unallocatedShare,
            isUnallocated: true,
          },
        ]
      : ownershipChartItems;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Investor Ownership</CardTitle>
            <CardDescription>
              {property
                ? `${headerName} — live on-chain data`
                : "Pick a property from the bar chart or table to see the breakdown."}
            </CardDescription>
          </div>
          <span className="shrink-0 text-base font-semibold tabular-nums text-foreground">
            {isLoading ? "Loading" : `${total.toFixed(1)}% invested`}
          </span>
        </div>
      </CardHeader>
      <CardContent className="grid flex-1 grid-cols-1 gap-4 pt-0 md:grid-cols-2">
        <div className="relative grid place-items-center">
          {!property ? (
            <div className="grid h-[220px] place-items-center text-sm text-muted-foreground">
              Select a property
            </div>
          ) : isLoading ? (
            <Skeleton className="h-[220px] w-[220px] rounded-full" />
          ) : error || items.length === 0 ? (
            <div className="grid h-[220px] place-items-center px-4 text-center text-xs text-muted-foreground">
              {error instanceof ApiError && error.status === 400
                ? "Set monthly rent on this property to see investor distribution."
                : "No investor data yet for this property."}
            </div>
          ) : (
            <>
              <ContinuousOwnershipDonut items={chartItems} />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="flex flex-col items-center text-center">
                  <span className="text-xl font-semibold tabular-nums">
                    {total.toFixed(1)}%
                  </span>
                  <span className="text-[11px] text-muted-foreground">Total Allocated</span>
                </div>
              </div>
            </>
          )}
        </div>
        <div className="flex max-h-[220px] min-h-[220px] flex-col gap-1.5 overflow-y-scroll overscroll-contain pr-1 scrollbar-thin">
          <div className="sticky top-0 z-10 grid grid-cols-[1fr_auto] gap-2 bg-card px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Investor</span>
            <span>Share</span>
          </div>
          {chartItems.map((it, i) => (
            <div
              key={it.investor}
              className="grid grid-cols-[1fr_auto] items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-xs hover:border-border hover:bg-muted/50"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: getOwnershipColor(i, it.isUnallocated) }}
                />
                <span
                  className={it.isUnallocated ? "truncate font-mono text-[11px] text-muted-foreground" : "truncate font-mono text-[11px] text-foreground/90"}
                  title={it.investor}
                >
                  {it.isUnallocated ? "Unallocated" : shortAddress(it.investor, 6, 4)}
                </span>
              </div>
              <span className={it.isUnallocated ? "tabular-nums font-medium text-muted-foreground" : "tabular-nums font-medium"}>
                {it.share_pct.toFixed(it.share_pct >= 10 ? 0 : 1)}%
              </span>
            </div>
          ))}
          {!items.length && property ? (
            <div className="grid flex-1 place-items-center text-xs text-muted-foreground">
              No investors yet.
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function ContinuousOwnershipDonut({ items }: { items: OwnershipChartItem[] }) {
  const [hover, setHover] = useState<DonutHover | null>(null);
  const radius = 76;
  const strokeWidth = 30;
  const circumference = 2 * Math.PI * radius;
  let start = 0;

  function updateHover(event: MouseEvent<SVGCircleElement>, item: OwnershipChartItem, index: number) {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    const label = item.isUnallocated ? "Unallocated" : shortAddress(item.investor);
    setHover({
      key: item.investor,
      label,
      value: `${item.share_pct.toFixed(item.share_pct >= 10 ? 0 : 1)}%`,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
      color: getOwnershipColor(index, item.isUnallocated),
    });
  }

  return (
    <div className="relative h-[220px] w-full">
      <svg
        className="h-[220px] w-full overflow-visible"
        viewBox="0 0 220 220"
        role="img"
        aria-label="Investor ownership allocation chart"
        onMouseLeave={() => setHover(null)}
      >
        {items.map((item, index) => {
          const value = Math.max(0, item.share_pct);
          if (value <= 0) return null;
          const dash = Math.min(circumference, (value / 100) * circumference + 3);
          const rotation = -112 + (start / 100) * 360;
          start += value;

          return (
            <circle
              key={item.investor}
              className="cursor-pointer transition-all duration-150"
              cx="110"
              cy="110"
              r={radius}
              fill="none"
              stroke={getOwnershipColor(index, item.isUnallocated)}
              strokeWidth={hover?.key === item.investor ? strokeWidth + 4 : strokeWidth}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeLinecap="round"
              opacity={hover && hover.key !== item.investor ? 0.58 : 1}
              transform={`rotate(${rotation} 110 110)`}
              onMouseEnter={(event) => updateHover(event, item, index)}
              onMouseMove={(event) => updateHover(event, item, index)}
            >
              <title>
                {item.isUnallocated ? "Unallocated" : shortAddress(item.investor)}:{" "}
                {item.share_pct.toFixed(item.share_pct >= 10 ? 0 : 1)}%
              </title>
            </circle>
          );
        })}
      </svg>
      {hover ? (
        <div
          className="pointer-events-none absolute z-20 rounded-xl border border-border bg-popover px-3 py-2 text-xs shadow-xl"
          style={{
            left: hover.x,
            top: hover.y,
            transform: "translate(-50%, calc(-100% - 10px))",
          }}
        >
          <div className="flex items-center gap-2 whitespace-nowrap">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: hover.color }} />
            <span className="font-medium text-popover-foreground">{hover.label}</span>
            <span className="font-semibold tabular-nums text-popover-foreground">{hover.value}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
