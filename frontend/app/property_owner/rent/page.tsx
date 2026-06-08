"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Coins, Receipt, Wallet } from "lucide-react";
import { toast } from "sonner";
import { AdminTopbar } from "@/components/layout/topbar";
import { GradientStatCard } from "@/components/dashboard/gradient-stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/empty";
import {
  useManagedProperties,
  useRentAnalytics,
  useRentDistributions,
  useRentPayments,
} from "@/lib/queries";
import { useSetRent } from "@/lib/mutations";
import { formatDateTime, formatEth } from "@/lib/utils";
import { identityDisplayName } from "@/lib/identity";
import { txExplorerUrl } from "@/lib/runtime-config";
import type { Property } from "@/lib/types";

const scrollTableViewportClass =
  "[&>div]:max-h-[360px] [&>div]:overflow-auto [&>div]:scrollbar-thin";
const stickyHeadClass =
  "sticky top-0 z-20 h-10 whitespace-nowrap bg-card py-2 text-sm";
const tableCellClass = "whitespace-nowrap py-3 text-sm";

export default function RentManagementPage() {
  const properties = useManagedProperties();
  const rent = useRentAnalytics();
  const distributions = useRentDistributions();
  const payments = useRentPayments();
  const adminProperties = properties.data ?? [];
  const recentRentPayments = useMemo(
    () => (payments.data ?? []).slice(0, 8),
    [payments.data],
  );
  const recentRentDistributions = useMemo(
    () => (distributions.data ?? []).slice(0, 8),
    [distributions.data],
  );

  return (
    <>
      <AdminTopbar
        title="Rent Management"
        subtitle="Live rent metrics, per-property controls, payments, and distributions"
      />
      <main className="flex-1 space-y-4 p-4 text-sm lg:p-6">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <GradientStatCard
            title="Total Rent Collected"
            value={formatEth(rent.data?.total_rent_collected_wei ?? "0", { fromWei: true, digits: 3 })}
            sub={`${rent.data?.total_payments ?? 0} payments`}
            icon={Wallet}
            loading={rent.isLoading}
            accent="violet"
            graph="steps"
          />
          <GradientStatCard
            title="Total Rent Distributed"
            value={formatEth(rent.data?.total_rent_distributed_wei ?? "0", { fromWei: true, digits: 3 })}
            sub={`${rent.data?.total_distributions ?? 0} distributions`}
            icon={Coins}
            loading={rent.isLoading}
            accent="mint"
            graph="line"
          />
          <GradientStatCard
            title="Payments Received"
            value={String(rent.data?.total_payments ?? 0)}
            sub="From tenants"
            icon={Receipt}
            loading={rent.isLoading}
            accent="cyan"
            graph="bars"
          />
          <GradientStatCard
            title="Active Rentals"
            value={String(rent.data?.active_rentals ?? 0)}
            sub="Current rentals"
            icon={ArrowRight}
            loading={rent.isLoading}
            accent="lavender"
            graph="dots"
          />
        </div>

        <Card className="text-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Properties</CardTitle>
            <CardDescription className="text-sm">Set monthly rent; blockchain sync is handled automatically.</CardDescription>
          </CardHeader>
          <CardContent className="px-0 pb-3">
            {properties.isLoading || adminProperties.length > 0 ? (
              <div className="[&>div]:max-h-[310px] [&>div]:overflow-auto [&>div]:scrollbar-thin">
                <PropertiesRentTable properties={adminProperties} loading={properties.isLoading} />
              </div>
            ) : (
              <div className="px-4 pb-1">
                <EmptyState
                  title="No properties yet"
                  description="Create a property before setting monthly rent."
                  className="min-h-[220px] border-0"
                />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card className="text-sm">
            <CardHeader>
              <CardTitle className="text-sm">Recent Rent Payments</CardTitle>
              <CardDescription className="text-sm">From tenants on Sepolia.</CardDescription>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              {payments.isLoading ? (
                <div className={scrollTableViewportClass}>
              <Table className="min-w-[760px] text-sm">
                <TableBody>
                  {Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i} className="hover:bg-transparent">
                        <TableCell colSpan={4}>
                          <Skeleton className="h-7 w-full" />
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
              </div>
              ) : recentRentPayments.length === 0 ? (
                <div className="px-4 pb-4">
                  <EmptyState
                    title="No rent payments yet"
                    description="Tenant payments will appear here after confirmation."
                    className="min-h-[220px] border-0"
                  />
                </div>
              ) : (
                <div className={scrollTableViewportClass}>
              <Table className="min-w-[760px] text-sm">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={stickyHeadClass}>Tenant</TableHead>
                    <TableHead className={stickyHeadClass}>Property</TableHead>
                    <TableHead className={stickyHeadClass}>Amount</TableHead>
                    <TableHead className={stickyHeadClass}>Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentRentPayments.map((p) => {
                      const tenantLabel = identityDisplayName(
                        {
                          wallet_address: p.tenant_wallet,
                          full_name: p.tenant_full_name,
                          display_id: p.tenant_display_id,
                          profile_role: p.tenant_profile_role,
                        },
                        p.tenant_wallet,
                      );
                      return (
                        <TableRow key={p.id ?? p.tx_hash}>
                        <TableCell className={tableCellClass}>
                          <a
                            href={txExplorerUrl(p.tx_hash)}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:underline"
                          >
                            {tenantLabel}
                          </a>
                        </TableCell>
                        <TableCell className={tableCellClass}>
                          {p.property_name ?? `#${p.property_id}`}
                        </TableCell>
                        <TableCell className={`${tableCellClass} tabular-nums`}>
                          {formatEth(p.amount_eth)}
                        </TableCell>
                        <TableCell className={`${tableCellClass} text-muted-foreground`}>
                          {formatDateTime(p.payment_date)}
                        </TableCell>
                      </TableRow>
                      );
                    })}
                </TableBody>
              </Table>
              </div>
              )}
            </CardContent>
          </Card>

          <Card className="text-sm">
            <CardHeader>
              <CardTitle className="text-sm">Recent Distributions</CardTitle>
              <CardDescription className="text-sm">Splits broadcast to investor wallets.</CardDescription>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              {distributions.isLoading ? (
                <div className={scrollTableViewportClass}>
              <Table className="min-w-[760px] text-sm">
                <TableBody>
                  {Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i} className="hover:bg-transparent">
                        <TableCell colSpan={4}>
                          <Skeleton className="h-7 w-full" />
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
              </div>
              ) : recentRentDistributions.length === 0 ? (
                <div className="px-4 pb-4">
                  <EmptyState
                    title="No distributions yet"
                    description="Investor distributions will appear here after rent is distributed."
                    className="min-h-[220px] border-0"
                  />
                </div>
              ) : (
                <div className={scrollTableViewportClass}>
              <Table className="min-w-[760px] text-sm">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={stickyHeadClass}>Property</TableHead>
                    <TableHead className={stickyHeadClass}>Distributed</TableHead>
                    <TableHead className={stickyHeadClass}>Investors</TableHead>
                    <TableHead className={stickyHeadClass}>Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentRentDistributions.map((d) => (
                      <TableRow key={d.id ?? d.distribution_tx_hash}>
                        <TableCell className={tableCellClass}>
                          {d.property_name ?? `#${d.property_id}`}
                        </TableCell>
                        <TableCell className={`${tableCellClass} tabular-nums`}>
                          {formatEth(d.total_distributed, { fromWei: true })}
                        </TableCell>
                        <TableCell className={`${tableCellClass} tabular-nums`}>
                          {d.investor_count}
                        </TableCell>
                        <TableCell className={`${tableCellClass} text-muted-foreground`}>
                          {formatDateTime(d.distributed_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
              </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}

function PropertiesRentTable({
  properties,
  loading,
}: {
  properties: Property[];
  loading?: boolean;
}) {
  if (!loading && properties.length === 0) {
    return (
      <EmptyState
        title="No properties yet"
        description="Create a property before setting monthly rent."
        className="min-h-[220px] border-0"
      />
    );
  }

  return (
    <Table className="min-w-[760px] text-sm">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={stickyHeadClass}>Property</TableHead>
          <TableHead className={stickyHeadClass}>Monthly Rent</TableHead>
          <TableHead className={stickyHeadClass}>Status</TableHead>
          <TableHead className={stickyHeadClass}>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <TableRow key={i} className="hover:bg-transparent">
              <TableCell colSpan={4}>
                <Skeleton className="h-7 w-full" />
              </TableCell>
            </TableRow>
          ))
        ) : (
          properties.map((p) => (
            <PropertyRentRow key={p.id} property={p} />
          ))
        )}
      </TableBody>
    </Table>
  );
}

function PropertyRentRow({ property }: { property: Property }) {
  const setRent = useSetRent();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(property.monthly_rent_eth ? String(property.monthly_rent_eth) : "");

  const monthly = Number(property.monthly_rent_eth ?? 0);

  async function onSubmitRent(e: React.FormEvent) {
    e.preventDefault();
    try {
      await setRent.mutateAsync({ property_id: property.id, monthly_rent_eth: value });
      toast.success("Rent updated.");
      setOpen(false);
    } catch (err: any) {
      toast.error(err?.message || "Failed to set rent.");
    }
  }

  return (
    <TableRow className="h-11">
      <TableCell className={tableCellClass}>
        <div className="flex flex-col">
          <span className="whitespace-nowrap text-sm font-medium leading-tight">{property.name}</span>
          <span className="whitespace-nowrap text-sm leading-tight text-muted-foreground">{property.location}</span>
        </div>
      </TableCell>
      <TableCell className={`${tableCellClass} tabular-nums`}>
        {monthly > 0 ? formatEth(monthly) : <span className="text-muted-foreground">Not set</span>}
      </TableCell>
      <TableCell className={tableCellClass}>
        {property.token_address ? (
          <Badge variant="success" className="h-6 whitespace-nowrap px-2 text-sm">Token deployed</Badge>
        ) : (
          <Badge variant="warning" className="h-6 whitespace-nowrap px-2 text-sm">Not deployed</Badge>
        )}
      </TableCell>
      <TableCell className={tableCellClass}>
        <div className="flex gap-1.5">
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" className="h-8 whitespace-nowrap px-3 text-sm">
                Set Rent
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-sm">
              <DialogHeader>
                <DialogTitle>Set Monthly Rent</DialogTitle>
                <DialogDescription>{property.name}</DialogDescription>
              </DialogHeader>
              <form onSubmit={onSubmitRent} className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>Amount (ETH)</Label>
                  <Input
                    type="number"
                    step="0.000000000000000001"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    required
                  />
                </div>
                <DialogFooter className="pt-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={setRent.isPending}>
                    {setRent.isPending ? "Saving…" : "Save"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </TableCell>
    </TableRow>
  );
}
