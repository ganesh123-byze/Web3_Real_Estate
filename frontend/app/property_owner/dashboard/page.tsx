"use client";

import { useEffect, useMemo, useState, type MouseEvent } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Building2, Coins, Receipt, Wallet } from "lucide-react";
import { AdminTopbar } from "@/components/layout/topbar";
import { useDashboardSummary, useProperties, useRentAnalytics, useTransactions } from "@/lib/queries";
import { PropertiesOverviewTable } from "@/components/dashboard/properties-overview-table";
import { InvestorShareChart } from "@/components/dashboard/investor-share-chart";
import { GradientStatCard } from "@/components/dashboard/gradient-stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Property } from "@/lib/types";
import { pickColor } from "@/lib/charts";
import { formatCurrency, formatEth, formatNumber } from "@/lib/utils";

type DonutHover = {
  key: string;
  label: string;
  value: string;
  x: number;
  y: number;
  color: string;
};

export default function DashboardPage() {
  const properties = useProperties();
  const transactions = useTransactions();
  const rent = useRentAnalytics();
  const summary = useDashboardSummary();

  const [selected, setSelected] = useState<Property | null>(null);
  useEffect(() => {
    const list = properties.data ?? [];
    if (list.length === 0) return;
    if (selected && list.some((property) => property.id === selected.id)) return;

    const firstInvestedProperty = list.find(
      (property) => !!property.token_address && Number(property.tokens_sold ?? 0) > 0,
    );
    setSelected(firstInvestedProperty ?? list[0]);
  }, [properties.data, selected]);

  const allProperties = properties.data ?? [];
  const investments = useMemo(
    () => (transactions.data ?? []).filter((transaction) => {
      const type = transaction.type.toLowerCase();
      return type.includes("investment") || transaction.type === "ISSUE_TOKENS";
    }),
    [transactions.data],
  );
  const totalInvestmentEth = investments.reduce(
    (acc, transaction) => acc + toEthDisplayAmount(transaction.amount_spent ?? transaction.amount ?? 0),
    0,
  );
  const totalPortfolio = Number(summary.data?.total_portfolio_value ?? 0) / 1e18;
  const selectedProperty = selected
    ? allProperties.find((property) => property.id === selected.id) ?? selected
    : null;
  const propertyPerf = allProperties
    .map((property) => ({
      id: property.id,
      name: property.name?.length > 14 ? `${property.name.slice(0, 12)}...` : property.name,
      sold: Number(property.tokens_sold ?? 0),
      total: Number(property.token_supply ?? 0),
      pct: Number(property.sold_percentage ?? 0),
    }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 8);
  const txByType = useMemo(() => {
    const map = new Map<string, number>();
    for (const transaction of transactions.data ?? []) {
      map.set(transaction.type, (map.get(transaction.type) ?? 0) + 1);
    }
    return Array.from(map.entries())
      .map(([type, count]) => ({ name: prettyType(type), type, count }))
      .sort((a, b) => b.count - a.count);
  }, [transactions.data]);
  const txTotal = txByType.reduce((acc, item) => acc + item.count, 0);

  return (
    <>
      <AdminTopbar
        title="Dashboard"
        subtitle="Properties, analytics, investor ownership, and transaction intelligence"
      />
      <main className="flex-1 space-y-4 p-4 lg:p-5">
        <section className="grid auto-rows-fr grid-cols-2 gap-3 xl:grid-cols-4">
          <GradientStatCard
            title="Total Portfolio Value"
            value={formatCurrency(totalPortfolio)}
            sub={`${summary.data?.properties_loaded ?? allProperties.length} properties indexed`}
            icon={Wallet}
            loading={summary.isLoading}
            accent="violet"
            graph="dots"
          />
          <GradientStatCard
            title="Investment Volume"
            value={`${totalInvestmentEth.toFixed(3)} ETH`}
            sub={`${investments.length} investments`}
            icon={Coins}
            loading={transactions.isLoading}
            accent="mint"
            graph="bars"
          />
          <GradientStatCard
            title="Rent Distributed"
            value={formatEth(rent.data?.total_rent_distributed_wei ?? "0", { fromWei: true, digits: 3 })}
            sub={`${rent.data?.total_distributions ?? 0} distributions`}
            icon={Receipt}
            loading={rent.isLoading}
            accent="cyan"
            graph="steps"
          />
          <GradientStatCard
            title="Total Properties"
            value={String(allProperties.length)}
            sub="Available properties"
            icon={Building2}
            loading={properties.isLoading}
            accent="lavender"
            graph="line"
          />
        </section>

        <section className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
          <div className="min-w-0">
            <PropertiesOverviewTable
              properties={properties.data ?? []}
              loading={properties.isLoading}
              selectedId={selected?.id ?? null}
              onSelectProperty={(property) => setSelected(property)}
            />
          </div>
          <InvestorShareChart property={selectedProperty} />
        </section>

        <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Property Performance</CardTitle>
              <CardDescription>Sold percentage for all available properties.</CardDescription>
            </CardHeader>
            <CardContent>
              {properties.isLoading ? (
                <Skeleton className="h-[280px] w-full" />
              ) : propertyPerf.length === 0 ? (
                <div className="grid h-[280px] place-items-center text-sm text-muted-foreground">
                  No properties.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={propertyPerf} margin={{ top: 12, right: 16, left: -12, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tickFormatter={(value) => `${value}%`}
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                      domain={[0, 100]}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--popover))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(value: number, _name, point) => {
                        const payload = point.payload as { sold: number; total: number };
                        return [
                          `${value.toFixed(1)}% (${formatNumber(payload.sold)} / ${formatNumber(payload.total)})`,
                          "Sold",
                        ];
                      }}
                    />
                    <Bar dataKey="pct" radius={[8, 8, 0, 0]}>
                      {propertyPerf.map((property) => (
                        <Cell key={property.id} fill={pickColor(property.id)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card className="h-full">
            <CardHeader>
              <CardTitle>Transaction Breakdown</CardTitle>
              <CardDescription>Activity grouped by event type.</CardDescription>
            </CardHeader>
            <CardContent>
              {transactions.isLoading ? (
                <Skeleton className="h-[280px] w-full" />
              ) : txByType.length === 0 ? (
                <div className="grid h-[280px] place-items-center text-sm text-muted-foreground">
                  No transaction data.
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-[1fr_0.78fr] md:items-center">
                  <div className="relative">
                    <ContinuousTransactionDonut items={txByType} total={txTotal} />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <span className="text-3xl font-semibold tabular-nums text-foreground">
                        {txTotal}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-3">
                    {txByType.map((item, index) => {
                      const percent = txTotal ? (item.count / txTotal) * 100 : 0;
                      return (
                        <div key={item.type} className="space-y-1.5 text-xs">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: pickColor(index) }} />
                              <span className="truncate font-medium">{item.name}</span>
                            </div>
                            <span className="tabular-nums font-semibold text-foreground">
                              {percent.toFixed(0)}%
                            </span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${percent}%`, background: pickColor(index) }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}

function prettyType(type: string) {
  return type
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function ContinuousTransactionDonut({
  items,
  total,
}: {
  items: Array<{ name: string; type: string; count: number }>;
  total: number;
}) {
  const [hover, setHover] = useState<DonutHover | null>(null);
  const radius = 76;
  const strokeWidth = 30;
  const circumference = 2 * Math.PI * radius;
  let start = 0;

  function updateHover(
    event: MouseEvent<SVGCircleElement>,
    item: { name: string; type: string; count: number },
    index: number,
  ) {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    const percent = total ? (item.count / total) * 100 : 0;
    setHover({
      key: item.type,
      label: item.name,
      value: `${item.count} (${percent.toFixed(0)}%)`,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
      color: pickColor(index),
    });
  }

  return (
    <div className="relative h-[240px] w-full">
      <svg
        className="h-[240px] w-full overflow-visible"
        viewBox="0 0 220 220"
        role="img"
        aria-label="Transaction breakdown chart"
        onMouseLeave={() => setHover(null)}
      >
        {items.map((item, index) => {
          const percent = total ? (item.count / total) * 100 : 0;
          if (percent <= 0) return null;
          const dash = Math.min(circumference, (percent / 100) * circumference + 3);
          const rotation = -112 + (start / 100) * 360;
          start += percent;

          return (
            <circle
              key={item.type}
              className="cursor-pointer transition-all duration-150"
              cx="110"
              cy="110"
              r={radius}
              fill="none"
              stroke={pickColor(index)}
              strokeWidth={hover?.key === item.type ? strokeWidth + 4 : strokeWidth}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeLinecap="round"
              opacity={hover && hover.key !== item.type ? 0.58 : 1}
              transform={`rotate(${rotation} 110 110)`}
              onMouseEnter={(event) => updateHover(event, item, index)}
              onMouseMove={(event) => updateHover(event, item, index)}
            >
              <title>
                {item.name}: {percent.toFixed(0)}%
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

function toEthDisplayAmount(value: string | number | null | undefined) {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount)) return 0;
  return Math.abs(amount) > 1_000_000 ? amount / 1e18 : amount;
}
