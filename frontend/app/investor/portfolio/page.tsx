"use client";

import { useMemo, useState } from "react";
import { Building2, ChevronDown, Coins, History, Wallet } from "lucide-react";
import { motion } from "framer-motion";
import { InvestorTopbar } from "@/components/investor/investor-topbar";
import { InvestorKpiCard } from "@/components/investor/investor-kpi-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/common/empty";
import { InvestmentSimulationWorkbench } from "@/components/investor/investment-simulation-workbench";
import { useInvestorYieldSummary, usePortfolio, useProperties, useWalletBalances } from "@/lib/queries";
import { cn, formatCurrency, formatEth, shortAddress } from "@/lib/utils";
import { buildInvestorMetrics, holdingValue, humanTokenAmount, ownershipPercent } from "@/components/investor/investor-utils";
import { useCurrentWallet } from "@/components/investor/use-current-wallet";
import type { PortfolioItem, Property, WalletBalanceToken } from "@/lib/types";

const ALLOCATION_COLORS = ["#4f46e5", "#22c6e8", "#8b5cf6", "#06b6d4", "#a855f7"];
type PortfolioView = "cards" | "table";

export default function InvestorPortfolioPage() {
  const wallet = useCurrentWallet();
  const properties = useProperties();
  const portfolio = usePortfolio(wallet);
  const yieldSummary = useInvestorYieldSummary(wallet);
  const balances = useWalletBalances(wallet);
  const [holdingsView, setHoldingsView] = useState<PortfolioView>("cards");
  const [walletTokenView, setWalletTokenView] = useState<PortfolioView>("cards");
  const propertyMap = useMemo(() => new Map((properties.data ?? []).map((p) => [Number(p.id), p])), [properties.data]);
  const activePropertyIds = useMemo(() => new Set((properties.data ?? []).map((p) => Number(p.id))), [properties.data]);
  const holdings = useMemo(
    () =>
      (portfolio.data?.holdings ?? []).filter((holding) => {
        const property = propertyMap.get(Number(holding.property_id));
        return !!property && property.is_active !== false;
      }),
    [portfolio.data?.holdings, propertyMap],
  );
  const walletTokens = useMemo(
    () =>
      (balances.data?.tokens ?? []).filter((token) => {
        if (token.property_id == null) return false;
        return activePropertyIds.has(Number(token.property_id));
      }),
    [activePropertyIds, balances.data?.tokens],
  );
  const metrics = buildInvestorMetrics(holdings, properties.data ?? []);
  const chartData = holdings.map((h) => {
    const property = propertyMap.get(Number(h.property_id));
    return {
      id: h.property_id,
      name: h.property_name.length > 18 ? `${h.property_name.slice(0, 16)}…` : h.property_name,
      value: holdingValue(h, property),
    };
  }).filter((item) => item.value > 0);

  const simulationSlices = useMemo(
    () => chartData.filter((c) => c.value > 0).map((c) => ({ id: c.id, name: c.name, value: c.value })),
    [chartData],
  );

  return (
    <>
      <InvestorTopbar title="Portfolio" subtitle="Token holdings, ownership percentages, and wallet balances" />
      <main className="flex-1 space-y-4 p-4 lg:p-6">
        <section className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <InvestorKpiCard
            title="Estimated Value"
            value={formatCurrency(metrics.estimatedValue)}
            icon={Wallet}
            variant="violet"
            loading={properties.isLoading || portfolio.isLoading}
          />
          <InvestorKpiCard
            title="Properties Owned"
            value={String(metrics.propertiesOwned)}
            icon={Building2}
            variant="mint"
            loading={portfolio.isLoading}
          />
          <InvestorKpiCard
            title="Total Earned"
            value={formatEth(yieldSummary.data?.total_earned_eth ?? "0")}
            icon={Coins}
            variant="sky"
            loading={yieldSummary.isLoading}
          />
          <InvestorKpiCard
            title="Payout Records"
            value={String(yieldSummary.data?.total_payouts ?? 0)}
            icon={History}
            variant="periwinkle"
            loading={yieldSummary.isLoading}
          />
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-[0.72fr_1.28fr]">
          <Card>
            <CardHeader>
              <CardTitle>Allocation</CardTitle>
              <CardDescription>Estimated value share by property.</CardDescription>
            </CardHeader>
            <CardContent>
              {portfolio.isLoading || properties.isLoading ? (
                <Skeleton className="h-[260px] w-full" />
              ) : chartData.length === 0 ? (
                <EmptyState
                  title="No holdings yet"
                  description="Allocation appears after you purchase property tokens."
                  className="min-h-[260px] border-0"
                />
              ) : (
                <>
                  <PortfolioAllocationDonut items={chartData} />
                  <div className="space-y-1.5">
                    {chartData.map((item, index) => (
                      <div key={item.id} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: ALLOCATION_COLORS[index % ALLOCATION_COLORS.length] }} /> {item.name}</div>
                        <span className="tabular-nums text-muted-foreground">{formatCurrency(item.value)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle>Holdings</CardTitle>
                <CardDescription>Ownership positions reconciled from SecurityToken balances.</CardDescription>
              </div>
              <PortfolioViewSelect value={holdingsView} onChange={setHoldingsView} ariaLabel="Holdings view" />
            </CardHeader>
            <CardContent>
              {portfolio.isLoading || properties.isLoading ? (
                <div className="space-y-2.5">
                  {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
                </div>
              ) : holdings.length === 0 ? (
                <EmptyState title="No property tokens yet" description="Your purchased ownership tokens will appear here after confirmation." />
              ) : holdingsView === "cards" ? (
                <HoldingCards holdings={holdings} propertyMap={propertyMap} />
              ) : (
                <HoldingTable holdings={holdings} propertyMap={propertyMap} />
              )}
            </CardContent>
          </Card>
        </section>

        {simulationSlices.length > 1 ? (
          <motion.section
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <InvestmentSimulationWorkbench
              slices={simulationSlices}
              totalValue={metrics.estimatedValue}
              loading={portfolio.isLoading || properties.isLoading}
            />
          </motion.section>
        ) : null}

        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Wallet Tokens</CardTitle>
              <CardDescription>Live token balances read from deployed property contracts.</CardDescription>
            </div>
            <PortfolioViewSelect value={walletTokenView} onChange={setWalletTokenView} ariaLabel="Wallet token view" />
          </CardHeader>
          <CardContent>
            {balances.isLoading ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
              </div>
            ) : walletTokens.length === 0 ? (
              <EmptyState title="No token balances" />
            ) : walletTokenView === "cards" ? (
              <WalletTokenCards tokens={walletTokens} />
            ) : (
              <WalletTokenTable tokens={walletTokens} />
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div><div className="font-medium tabular-nums">{value}</div></div>;
}

function formatTokenBalance(value: WalletBalanceToken["balance"]) {
  return Number(value ?? 0).toLocaleString("en-US", { maximumFractionDigits: 4 });
}

function PortfolioViewSelect({
  value,
  onChange,
  ariaLabel,
}: {
  value: PortfolioView;
  onChange: (value: PortfolioView) => void;
  ariaLabel: string;
}) {
  return (
    <div className="relative w-full sm:w-[180px] sm:shrink-0">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as PortfolioView)}
        aria-label={ariaLabel}
        className={cn(
          "h-9 w-full cursor-pointer appearance-none rounded-md border border-input bg-background pl-3 pr-9 text-sm shadow-sm",
          "text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        <option value="cards">Card View</option>
        <option value="table">Table View</option>
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
    </div>
  );
}

function HoldingCards({
  holdings,
  propertyMap,
}: {
  holdings: PortfolioItem[];
  propertyMap: Map<number, Property>;
}) {
  return (
    <div className="max-h-[300px] overflow-y-auto pr-1 scrollbar-thin">
      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        {holdings.map((holding) => {
          const property = propertyMap.get(Number(holding.property_id));
          const pct = ownershipPercent(holding, property);
          const value = holdingValue(holding, property);
          return (
            <div key={holding.property_id} className="rounded-xl border border-border bg-card/80 p-2.5">
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <h3 className="truncate text-sm font-semibold">{holding.property_name}</h3>
                  <Badge variant="outline" className="h-5 shrink-0 rounded-md px-2 py-0 text-[10px]">
                    {property?.token_symbol ?? "TOKEN"}
                  </Badge>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {property?.location ?? `Property #${holding.property_id}`}
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <Fact label="Tokens" value={humanTokenAmount(holding.token_amount)} />
                <Fact label="Ownership" value={`${pct.toFixed(4)}%`} />
                <Fact label="Value" value={formatCurrency(value)} />
              </div>
              <Progress value={Math.min(pct, 100)} className="mt-2 h-1" indicatorClassName={cn(pct > 1 ? "bg-success" : "bg-primary")} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HoldingTable({
  holdings,
  propertyMap,
}: {
  holdings: PortfolioItem[];
  propertyMap: Map<number, Property>;
}) {
  return (
    <div className="max-h-[320px] overflow-y-auto rounded-xl border border-border scrollbar-thin">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow className="hover:bg-transparent">
            <TableHead>Property</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="text-right">Ownership</TableHead>
            <TableHead className="text-right">Est. Value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {holdings.map((holding) => {
            const property = propertyMap.get(Number(holding.property_id));
            const pct = ownershipPercent(holding, property);
            const value = holdingValue(holding, property);
            return (
              <TableRow key={holding.property_id}>
                <TableCell className="max-w-[220px]">
                  <div className="truncate font-medium">{holding.property_name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {property?.location ?? `Property #${holding.property_id}`}
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">{humanTokenAmount(holding.token_amount)}</TableCell>
                <TableCell className="text-right tabular-nums">{pct.toFixed(4)}%</TableCell>
                <TableCell className="text-right font-semibold tabular-nums">{formatCurrency(value)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function WalletTokenCards({ tokens }: { tokens: WalletBalanceToken[] }) {
  return (
    <div className="max-h-[320px] overflow-y-auto pr-1 scrollbar-thin">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tokens.map((token) => (
          <div key={`${token.token_address}-${token.property_id}`} className="rounded-lg border border-border bg-muted/20 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{token.property_name}</div>
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">{shortAddress(token.token_address, 6, 4)}</div>
              </div>
              <Badge variant="muted">{token.symbol ?? "TOKEN"}</Badge>
            </div>
            <div className="mt-3 text-lg font-semibold tabular-nums">{formatTokenBalance(token.balance)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WalletTokenTable({ tokens }: { tokens: WalletBalanceToken[] }) {
  return (
    <div className="max-h-[320px] overflow-y-auto rounded-xl border border-border scrollbar-thin">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow className="hover:bg-transparent">
            <TableHead>Property</TableHead>
            <TableHead>Token</TableHead>
            <TableHead>Address</TableHead>
            <TableHead className="text-right">Balance</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tokens.map((token) => (
            <TableRow key={`${token.token_address}-${token.property_id}`}>
              <TableCell className="max-w-[220px] truncate font-medium">{token.property_name}</TableCell>
              <TableCell><Badge variant="muted">{token.symbol ?? "TOKEN"}</Badge></TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{shortAddress(token.token_address, 6, 4)}</TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{formatTokenBalance(token.balance)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function PortfolioAllocationDonut({
  items,
}: {
  items: Array<{ id: number | string; name: string; value: number }>;
}) {
  const totalValue = items.reduce((sum, item) => sum + item.value, 0);
  const radius = 65;
  const strokeWidth = 28;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="mx-auto grid h-[220px] w-full max-w-[336px] place-items-center">
      <svg
        className="h-[220px] w-full overflow-visible"
        viewBox="0 0 220 220"
        role="img"
        aria-label="Portfolio allocation by property"
      >
        {items.map((item, index) => {
          const share = totalValue > 0 ? item.value / totalValue : 0;
          const dash = Math.max(0, share * circumference - 4);
          const gap = circumference - dash;
          const rotation = -90 + (offset / circumference) * 360;
          offset += share * circumference;

          return (
            <circle
              key={item.id}
              cx="110"
              cy="110"
              r={radius}
              fill="none"
              stroke={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]}
              strokeWidth={strokeWidth}
              strokeDasharray={`${dash} ${gap}`}
              strokeLinecap="round"
              transform={`rotate(${rotation} 110 110)`}
            >
              <title>{item.name}: {formatCurrency(item.value)}</title>
            </circle>
          );
        })}
      </svg>
    </div>
  );
}
