"use client";

import { MapPin, Store, TrendingUp } from "lucide-react";
import { HighlightedAssistantText } from "@/lib/ai/assistant-text";
import type { MarketplaceCatalog } from "@/lib/ai/investor-marketplace-catalog";
import { cn } from "@/lib/utils";

function Metric({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-[#8a82c8]">{label}</div>
      <div className={cn("mt-0.5 break-words text-[13px] font-bold text-[#1A1A2E] dark:text-slate-100", valueClassName)}>
        <HighlightedAssistantText text={value} />
      </div>
    </div>
  );
}

export function InvestorMarketplaceCatalogCard({ catalog }: { catalog: MarketplaceCatalog }) {
  return (
    <section className="w-full min-w-0 overflow-hidden rounded-[16px] bg-white px-4 py-3 text-[14px] text-[#1A1A2E] dark:border dark:border-[#1e2947] dark:bg-[#070b1a] dark:text-slate-100">
      <div className="mb-3 flex items-center gap-2 font-bold">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-[#ede9ff] text-[#3B309E] dark:bg-[#211a54] dark:text-[#9b8cff]">
          <Store className="h-3.5 w-3.5" />
        </span>
        <span>{catalog.heading}</span>
      </div>

      <div className="space-y-3">
        {catalog.properties.map((property) => {
          const hasYield =
            property.grossAnnualYield !== "—" || property.netProjectedYield !== "—";

          return (
            <article
              key={`${property.id ?? property.name}`}
              className="rounded-[12px] border border-[#ece8ff] bg-[#faf9ff] p-3 dark:border-[#1e2947] dark:bg-[#090f25]"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h4 className="truncate text-[14px] font-bold text-[#1A1A2E] dark:text-slate-100">
                    {property.id ? `#${property.id} ` : ""}
                    {property.name}
                  </h4>
                  <p className="mt-0.5 flex items-center gap-1 text-[12px] text-[#474553] dark:text-slate-400">
                    <MapPin className="h-3 w-3 shrink-0" />
                    <span className="truncate">
                      <HighlightedAssistantText text={property.location} />
                    </span>
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-[#ede9ff] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#3B309E] dark:bg-[#211a54] dark:text-[#9b8cff]">
                  <HighlightedAssistantText text={property.saleProgress} />
                </span>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-3">
                <Metric label="Tokens available" value={property.tokensAvailable} />
                <Metric label="Price per token" value={property.pricePerToken} />
                <Metric label="Monthly rent" value={property.monthlyRent} />
                {hasYield ? (
                  <Metric
                    label="Gross annual yield"
                    value={property.grossAnnualYield}
                    valueClassName="text-[#3B6D11] dark:text-[#8fd44f]"
                  />
                ) : (
                  <Metric label="Yield" value="Rent not configured" />
                )}
              </div>

              {property.netProjectedYield !== "—" ? (
                <div className="mt-3 flex items-center justify-between gap-3 rounded-[10px] border border-emerald-100 bg-white px-3 py-2 dark:border-[#1f3d2a] dark:bg-[#07140d]">
                  <div className="flex items-center gap-2 text-[12px] font-semibold text-[#3B6D11] dark:text-[#8fd44f]">
                    <TrendingUp className="h-3.5 w-3.5" />
                    Net projected yield
                  </div>
                  <div className="text-[13px] font-bold text-[#3B6D11] dark:text-[#8fd44f]">
                    <HighlightedAssistantText text={property.netProjectedYield} />
                  </div>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {catalog.footer ? (
        <p className="mt-3 text-[13px] leading-snug text-[#474553] dark:text-slate-400">
          <HighlightedAssistantText text={catalog.footer} />
        </p>
      ) : null}
    </section>
  );
}
