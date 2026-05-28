"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Building2, Home, MapPin, Receipt, Wallet } from "lucide-react";
import { AdminTopbar } from "@/components/layout/topbar";
import { GradientStatCard } from "@/components/dashboard/gradient-stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTenantActiveRentals, useTenantPayments, useTenantProperties, useWalletBalances } from "@/lib/queries";
import { formatDateTime, formatEth, shortAddress } from "@/lib/utils";
import { useCurrentWallet } from "@/components/investor/use-current-wallet";

export default function TenantDashboardPage() {
  const wallet = useCurrentWallet();
  const properties = useTenantProperties(wallet);
  const payments = useTenantPayments(wallet);
  const rentals = useTenantActiveRentals(wallet);
  const balances = useWalletBalances(wallet);

  const rentEnabledProperties = useMemo(
    () => (properties.data ?? []).filter((p) => p.rent_enabled),
    [properties.data],
  );
  const totalPaid = useMemo(
    () => (payments.data ?? []).reduce((sum, payment) => sum + Number(payment.amount_eth ?? 0), 0),
    [payments.data],
  );

  return (
    <>
      <AdminTopbar title="Tenant Dashboard" subtitle="Manage rentals, pay rent, and track your payment history" />
      <main className="flex-1 space-y-4 p-4 lg:p-5">
        <section className="grid auto-rows-fr grid-cols-1 gap-3 md:grid-cols-3">
          <GradientStatCard
            icon={Receipt}
            title="Total Rent Paid"
            value={`${totalPaid.toFixed(4)} ETH`}
            sub={`${payments.data?.length ?? 0} payments`}
            loading={payments.isLoading}
            accent="violet"
            graph="steps"
          />
          <GradientStatCard
            icon={Home}
            title="Rental Properties"
            value={String(rentals.data?.length ?? 0)}
            sub={`${rentEnabledProperties.length} rent-ready`}
            loading={rentals.isLoading || properties.isLoading}
            accent="mint"
            graph="bars"
          />
          <GradientStatCard
            icon={Wallet}
            title="Available Balance"
            value={balances.isLoading ? "" : formatEth(balances.data?.native?.balance ?? "0", { digits: 4 })}
            sub={wallet ? shortAddress(wallet, 4, 4).replace("…", "...") : "Wallet not connected"}
            loading={balances.isLoading}
            accent="cyan"
            graph="line"
          />
        </section>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Active Rentals</CardTitle>
                <CardDescription>Properties you are currently renting.</CardDescription>
              </div>
              <Button asChild size="sm" variant="outline">
                <Link href="/tenant/rentals">View All</Link>
              </Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {rentals.isLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : (rentals.data ?? []).length === 0 ? (
                <EmptyState title="No active rentals" description="Browse available properties and start renting." icon={Building2} />
              ) : (
                (rentals.data ?? []).slice(0, 4).map((rental) => (
                  <div key={rental.id} className="flex items-center justify-between gap-4 rounded-xl border border-border/70 bg-muted/15 p-3 text-left">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary/10 text-primary">
                        <Home className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{rental.property_name ?? `Property #${rental.property_id}`}</div>
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <MapPin className="h-3 w-3" /> {rental.location ?? "—"}
                        </div>
                      </div>
                    </div>
                    <div className="min-w-[150px] text-left">
                      <Badge variant="success" className="rounded-md text-[10px]">Active</Badge>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {rental.current_cycle_paid && rental.next_rent_due_at
                          ? `Next due ${formatDateTime(rental.next_rent_due_at)}`
                          : rental.rental_start_date
                            ? `Since ${formatDateTime(rental.rental_start_date)}`
                            : "—"}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Recent Payments</CardTitle>
                <CardDescription>Your latest rent payments on Sepolia.</CardDescription>
              </div>
              <Button asChild size="sm" variant="outline">
                <Link href="/tenant/transactions">View All</Link>
              </Button>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              {payments.isLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : (payments.data ?? []).length === 0 ? (
                <div className="py-10">
                  <EmptyState title="No payments yet" description="Your rent payments will appear here after confirmation." />
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Property</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(payments.data ?? []).slice(0, 4).map((payment) => (
                      <TableRow key={payment.id}>
                        <TableCell className="text-sm font-medium">{payment.property_name ?? `Property #${payment.property_id}`}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatDateTime(payment.payment_date)}</TableCell>
                        <TableCell>
                          <Badge variant={payment.payment_status === "completed" ? "success" : "warning"} className="rounded-md text-[10px]">
                            {payment.payment_status}
                          </Badge>
                        </TableCell>
                        <TableCell className="tabular-nums text-sm font-medium">{payment.amount_eth} ETH</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}

