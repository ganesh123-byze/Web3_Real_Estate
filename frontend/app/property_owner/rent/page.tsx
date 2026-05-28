"use client";

import { useState } from "react";
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
  useProperties,
  useRentAnalytics,
  useRentDistributions,
  useRentPayments,
} from "@/lib/queries";
import { useSetRent } from "@/lib/mutations";
import { formatDateTime, formatEth, shortAddress } from "@/lib/utils";
import { txExplorerUrl } from "@/lib/runtime-config";
import type { Property } from "@/lib/types";

export default function RentManagementPage() {
  const properties = useProperties();
  const rent = useRentAnalytics();
  const distributions = useRentDistributions();
  const payments = useRentPayments();

  return (
    <>
      <AdminTopbar
        title="Rent Management"
        subtitle="Live rent metrics, per-property controls, payments, and distributions"
      />
      <main className="flex-1 space-y-4 p-4 lg:p-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Properties</CardTitle>
            <CardDescription>Set monthly rent; blockchain sync is handled automatically.</CardDescription>
          </CardHeader>
          <CardContent className="px-0 pb-3">
            <div className="max-h-[310px] overflow-y-auto scrollbar-thin">
              <PropertiesRentTable properties={properties.data ?? []} loading={properties.isLoading} />
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Recent Rent Payments</CardTitle>
              <CardDescription>From tenants on Sepolia.</CardDescription>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="text-sm">Tenant</TableHead>
                    <TableHead className="text-sm">Property</TableHead>
                    <TableHead className="text-sm">Amount</TableHead>
                    <TableHead className="text-sm">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {payments.isLoading ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i} className="hover:bg-transparent">
                        <TableCell colSpan={4}>
                          <Skeleton className="h-7 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (payments.data ?? []).length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="py-10">
                        <EmptyState title="No rent payments yet" />
                      </TableCell>
                    </TableRow>
                  ) : (
                    (payments.data ?? []).slice(0, 8).map((p) => (
                      <TableRow key={p.id ?? p.tx_hash}>
                        <TableCell className="font-mono text-sm">
                          <a
                            href={txExplorerUrl(p.tx_hash)}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:underline"
                          >
                            {shortAddress(p.tenant_wallet, 6, 4)}
                          </a>
                        </TableCell>
                        <TableCell className="text-sm">
                          {p.property_name ?? `#${p.property_id}`}
                        </TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {Number(p.amount_eth).toFixed(4)} ETH
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDateTime(p.payment_date)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent Distributions</CardTitle>
              <CardDescription>Splits broadcast to investor wallets.</CardDescription>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="text-sm">Property</TableHead>
                    <TableHead className="text-sm">Distributed</TableHead>
                    <TableHead className="text-sm">Investors</TableHead>
                    <TableHead className="text-sm">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {distributions.isLoading ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i} className="hover:bg-transparent">
                        <TableCell colSpan={4}>
                          <Skeleton className="h-7 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (distributions.data ?? []).length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="py-10">
                        <EmptyState title="No distributions yet" />
                      </TableCell>
                    </TableRow>
                  ) : (
                    (distributions.data ?? []).slice(0, 8).map((d) => (
                      <TableRow key={d.id ?? d.distribution_tx_hash}>
                        <TableCell className="text-sm">
                          {d.property_name ?? `#${d.property_id}`}
                        </TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {(Number(d.total_distributed) / 1e18).toFixed(4)} ETH
                        </TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {d.investor_count}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDateTime(d.distributed_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
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
  return (
    <Table className="text-xs">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-8 py-1">Property</TableHead>
          <TableHead className="h-8 py-1">Monthly Rent</TableHead>
          <TableHead className="h-8 py-1">Status</TableHead>
          <TableHead className="h-8 py-1">Actions</TableHead>
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
        ) : properties.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} className="py-10">
              <EmptyState title="No properties" />
            </TableCell>
          </TableRow>
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
    <TableRow className="h-10">
      <TableCell className="py-1.5">
        <div className="flex flex-col">
          <span className="text-xs font-medium leading-tight">{property.name}</span>
          <span className="text-[10px] leading-tight text-muted-foreground">{property.location}</span>
        </div>
      </TableCell>
      <TableCell className="py-1.5 tabular-nums">
        {monthly > 0 ? `${monthly.toFixed(4)} ETH` : <span className="text-muted-foreground">Not set</span>}
      </TableCell>
      <TableCell className="py-1.5">
        {property.token_address ? (
          <Badge variant="success" className="h-5 px-2 text-[10px]">Token deployed</Badge>
        ) : (
          <Badge variant="warning" className="h-5 px-2 text-[10px]">Not deployed</Badge>
        )}
      </TableCell>
      <TableCell className="py-1.5">
        <div className="flex gap-1.5">
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs">
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
