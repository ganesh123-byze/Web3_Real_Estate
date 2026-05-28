"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Building2, Coins, Receipt, Wallet } from "lucide-react";
import { AdminTopbar } from "@/components/layout/topbar";
import { GradientStatCard } from "@/components/dashboard/gradient-stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useProperties,
  useRentAnalytics,
  useRentDistributions,
  useTransactions,
} from "@/lib/queries";
import { cn, formatEth, formatNumber, formatShortDate, parseBackendDate } from "@/lib/utils";
import { pickColor } from "@/lib/charts";

export default function AnalyticsPage() {
  const properties = useProperties();
  const transactions = useTransactions();
  const rent = useRentAnalytics();
  const distributions = useRentDistributions();

  const investments = useMemo(
    () => (transactions.data ?? []).filter((t) => t.type === "investment"),
    [transactions.data],
  );

  const totalInvestmentEth = investments.reduce(
    (acc, t) => acc + Number(t.amount_spent ?? t.amount ?? 0),
    0,
  );
  const avgInvestmentEth = investments.length ? totalInvestmentEth / investments.length : 0;
  const activeProperties = (properties.data ?? []).filter(
    (p) => Number(p.tokens_sold ?? 0) > 0 || !!p.token_address,
  ).length;

  const propertyPerf = (properties.data ?? [])
    .map((p) => ({
      id: p.id,
      name: p.name?.length > 14 ? `${p.name.slice(0, 12)}…` : p.name,
      sold: Number(p.tokens_sold ?? 0),
      total: Number(p.token_supply ?? 0),
      pct: Number(p.sold_percentage ?? 0),
    }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 8);

  const txByType = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of transactions.data ?? []) {
      map.set(t.type, (map.get(t.type) ?? 0) + 1);
    }
    return Array.from(map.entries())
      .map(([type, count]) => ({ name: prettyType(type), type, count }))
      .sort((a, b) => b.count - a.count);
  }, [transactions.data]);

  const distributionTimeline = useMemo(() => {
    return (distributions.data ?? [])
      .slice()
      .sort((a, b) => (parseBackendDate(a.distributed_at)?.getTime() ?? 0) - (parseBackendDate(b.distributed_at)?.getTime() ?? 0))
      .map((d) => ({
        name: formatShortDate(d.distributed_at),
        amount: Number(d.total_distributed) / 1e18,
      }));
  }, [distributions.data]);

  return (
    <>
      <AdminTopbar
        title="Analytics"
        subtitle="Portfolio trends — investments, rent, transactions, and property performance"
      />
      <main className="flex-1 space-y-4 p-4 lg:p-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <GradientStatCard
            title="Investment Volume"
            value={`${totalInvestmentEth.toFixed(3)} ETH`}
            sub={`${investments.length} investments`}
            icon={Wallet}
            loading={transactions.isLoading}
            accent="violet"
            graph="bars"
          />
          <GradientStatCard
            title="Avg Investment Size"
            value={`${avgInvestmentEth.toFixed(4)} ETH`}
            sub={investments.length ? `Across ${investments.length} txs` : "No investments yet"}
            icon={Coins}
            loading={transactions.isLoading}
            accent="mint"
            graph="line"
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
            title="Active Properties"
            value={String(activeProperties)}
            sub={`${properties.data?.length ?? 0} total`}
            icon={Building2}
            loading={properties.isLoading}
            accent="lavender"
            graph="dots"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Rent Distribution Timeline</CardTitle>
              <CardDescription>Total ETH paid out per distribution event.</CardDescription>
            </CardHeader>
            <CardContent>
              {distributions.isLoading ? (
                <Skeleton className="h-[260px] w-full" />
              ) : distributionTimeline.length === 0 ? (
                <div className="grid h-[260px] place-items-center text-sm text-muted-foreground">
                  No distributions yet.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={distributionTimeline} margin={{ top: 16, right: 8, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--popover))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(v: number) => [`${v.toFixed(4)} ETH`, "Distributed"]}
                    />
                    <Area
                      type="monotone"
                      dataKey="amount"
                      stroke="hsl(var(--chart-1))"
                      fill="url(#g1)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transaction Breakdown</CardTitle>
              <CardDescription>By event type</CardDescription>
            </CardHeader>
            <CardContent>
              {transactions.isLoading ? (
                <Skeleton className="h-[200px] w-full" />
              ) : txByType.length === 0 ? (
                <div className="grid h-[200px] place-items-center text-sm text-muted-foreground">
                  No data
                </div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={180}>
                    <PieChart>
                      <Pie
                        data={txByType}
                        dataKey="count"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={48}
                        outerRadius={70}
                        paddingAngle={2}
                        stroke="hsl(var(--card))"
                        strokeWidth={2}
                      >
                        {txByType.map((d, i) => (
                          <Cell key={d.type} fill={pickColor(i)} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="mt-2 space-y-1">
                    {txByType.map((it, i) => (
                      <div key={it.type} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ background: pickColor(i) }}
                          />
                          <span>{it.name}</span>
                        </div>
                        <span className="tabular-nums text-muted-foreground">{it.count}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Property Performance</CardTitle>
            <CardDescription>Sold percentage per property.</CardDescription>
          </CardHeader>
          <CardContent>
            {properties.isLoading ? (
              <Skeleton className="h-[260px] w-full" />
            ) : propertyPerf.length === 0 ? (
              <div className="grid h-[260px] place-items-center text-sm text-muted-foreground">
                No properties.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={propertyPerf} margin={{ top: 12, right: 16, left: -12, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tickFormatter={(v) => `${v}%`}
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
                    formatter={(v: number, _name, p) => [`${v.toFixed(1)}% (${formatNumber((p.payload as any).sold)} / ${formatNumber((p.payload as any).total)})`, "Sold"]}
                  />
                  <Bar dataKey="pct" radius={[8, 8, 0, 0]}>
                    {propertyPerf.map((d) => (
                      <Cell key={d.id} fill={pickColor(d.id)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function prettyType(t: string) {
  return t
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}
