"use client";

import { useMemo, useState } from "react";
import { Building2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/common/empty";
import { cn, formatNumber, shortAddress } from "@/lib/utils";
import type { OwnerInvestor, Property, Transaction } from "@/lib/types";
import { pickColor } from "@/lib/charts";
import { propertyOwnershipFor, type PropertyOwnershipItem } from "@/lib/ownership";

export function PropertiesOverviewTable({
  properties,
  loading,
  onSelectProperty,
  selectedId,
  ownerInvestors,
  investorsLoading,
  transactions,
}: {
  properties: Property[];
  loading?: boolean;
  onSelectProperty?: (p: Property) => void;
  selectedId?: number | null;
  ownerInvestors?: OwnerInvestor[];
  investorsLoading?: boolean;
  transactions?: Transaction[];
}) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return properties;
    const q = search.toLowerCase();
    return properties.filter(
      (p) => p.name.toLowerCase().includes(q) || (p.location || "").toLowerCase().includes(q),
    );
  }, [properties, search]);

  if (!loading && properties.length === 0) {
    return (
      <div className="h-full overflow-hidden rounded-2xl border border-border/60 bg-card/[0.78] shadow-none backdrop-blur-2xl">
        <div className="flex items-center gap-2 border-b border-border/60 p-3">
          <div className="grid h-8 w-8 place-items-center rounded-xl bg-primary/10 text-primary">
            <Building2 className="h-4 w-4" />
          </div>
          <h3 className="text-base font-semibold leading-none tracking-tight">Properties Overview</h3>
        </div>
        <div className="p-4">
          <EmptyState
            title="No properties yet"
            description="Create your first property listing to start tracking token supply and investors."
            icon={Building2}
            className="min-h-[260px] border-0"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-hidden rounded-2xl border border-border/60 bg-card/[0.78] shadow-none backdrop-blur-2xl transition-shadow hover:shadow-sm">
      <div className="flex flex-col gap-3 border-b border-border/60 p-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-xl bg-primary/10 text-primary">
            <Building2 className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-base font-semibold leading-none tracking-tight">Properties Overview</h3>
          </div>
        </div>
        <div className="flex w-full max-w-xs items-center gap-2">
          <div className="relative w-full">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
              }}
              placeholder="Search property…"
              className="h-8 rounded-xl pl-8 text-xs"
            />
          </div>
        </div>
      </div>

      {!loading && filtered.length === 0 ? (
        <div className="p-4">
          <EmptyState
            title="No properties"
            description="No managed properties match your search."
            icon={Building2}
            className="min-h-[240px] border-0"
          />
        </div>
      ) : (
      <div className="max-h-[300px] overflow-auto scrollbar-thin">
        <div className="min-w-[720px]">
        <div className="sticky top-0 z-10 grid grid-cols-[26px_minmax(0,1.5fr)_96px_minmax(88px,0.7fr)_94px_58px] gap-2 border-b border-border bg-card px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <span>No</span>
          <span>Property</span>
          <span className="whitespace-nowrap">Total Tokens</span>
          <span>Distribution</span>
          <span className="whitespace-nowrap">Token Price</span>
          <span>Investors</span>
        </div>
        <div>
          {loading && properties.length === 0
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="border-b border-border px-4 py-3">
                  <Skeleton className="h-11 w-full" />
                </div>
              ))
            : filtered.length === 0
              ? (
                <div className="py-10 text-center text-sm text-muted-foreground">
                  No managed properties to show.
                </div>
              )
              : filtered.map((p, idx) => {
              const ownership = propertyOwnershipFor(ownerInvestors, p, transactions);
              const investorCount = ownership.length;
              const soldPct = Number(p.sold_percentage ?? 0);
              const tokensSold = Number(p.tokens_sold ?? 0);
              const tokensTotal = Number(p.token_supply ?? 0);
              const priceEth = p.token_sale_price_eth ?? "0";
              const isSelected = selectedId === p.id;
              return (
                <button
                  key={p.id}
                  data-state={isSelected ? "selected" : undefined}
                  onClick={() => onSelectProperty?.(p)}
                  className={cn(
                    "grid w-full grid-cols-[26px_minmax(0,1.5fr)_96px_minmax(88px,0.7fr)_94px_58px] items-center gap-2 border-b border-border px-4 py-3 text-left transition-colors hover:bg-muted/40",
                    isSelected && "bg-muted/60",
                  )}
                >
                  <span className="text-sm text-muted-foreground">{idx + 1}</span>
                  <span>
                    <div className="flex items-center gap-3">
                      <div
                        className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-xs font-semibold text-white"
                        style={{ background: pickColor(p.id) }}
                      >
                        {p.token_symbol?.slice(0, 2) || "PR"}
                      </div>
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate text-sm font-medium">{p.name}</span>
                        <span className="truncate text-xs text-muted-foreground">{p.location}</span>
                      </div>
                    </div>
                  </span>
                  <span className="text-left text-xs tabular-nums">
                    {formatNumber(tokensTotal)}
                  </span>
                  <span className="text-xs font-medium tabular-nums">
                    {formatNumber(tokensSold)} ({soldPct.toFixed(1)}%)
                  </span>
                  <span className="text-left text-xs tabular-nums">
                    {Number(priceEth).toFixed(4)} ETH
                  </span>
                  <span className="text-left">
                    <InvestorAvatars
                      ownership={ownership}
                      isLoading={investorsLoading && !!p.token_address}
                      hasToken={!!p.token_address}
                      count={investorCount}
                    />
                  </span>
                </button>
              );
            })}
        </div>
        </div>
      </div>
      )}
    </div>
  );
}

function InvestorAvatars({
  ownership,
  isLoading,
  hasToken,
  count,
}: {
  ownership: PropertyOwnershipItem[];
  isLoading?: boolean;
  hasToken: boolean;
  count: number;
}) {
  if (isLoading) return <Skeleton className="mx-auto h-5 w-6" />;
  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex cursor-default items-center justify-center text-sm font-medium tabular-nums">
            {count}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" align="end" className="w-64 p-3">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Investors
          </div>
          {!hasToken || ownership.length === 0 ? (
            <div className="text-[11px] text-muted-foreground">
              {!hasToken ? "No token deployed yet." : "No investors yet."}
            </div>
          ) : (
          <div className="max-h-44 space-y-1.5 overflow-y-auto pr-1 scrollbar-thin">
            {ownership.map((item) => (
              <div key={item.investor} className="flex items-center justify-between gap-3">
                <span className="truncate font-mono text-[11px]">{shortAddress(item.investor, 6, 4)}</span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                  {item.share_pct.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
