"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Building2, CheckCircle2, CreditCard, MapPin, Receipt, Search, ShieldCheck, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { queryKeys, useTenantActiveRentals, useTenantProperties } from "@/lib/queries";
import { AdminTopbar } from "@/components/layout/topbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty";
import { cn, formatCurrency, formatDateTime, formatNumber, percent, shortAddress } from "@/lib/utils";
import { PropertyImageCarousel } from "@/components/properties/property-image-carousel";
import { PropertyDetailDialog } from "@/components/properties/property-detail-dialog";
import type { PayRentPrepareResponse, Property } from "@/lib/types";
import { useCurrentWallet } from "@/components/investor/use-current-wallet";
import { sendPayRentTx } from "@/components/investor/contract-actions";
import { useTenantDistributionPreview } from "@/lib/queries";
import {
  clearPendingWorkflowActions,
  emitWorkflowCompletion,
  isWorkflowModalAction,
  preventCloseFromWorkflowBubble,
  subscribeWorkflowAction,
  takePendingModalOpen,
  workflowPropertyMatches,
} from "@/lib/ai/action-executor";

export default function TenantRentalsPage() {
  const wallet = useCurrentWallet();
  const properties = useTenantProperties(wallet);
  const rentals = useTenantActiveRentals(wallet);
  const [search, setSearch] = useState("");

  const activeRentalIds = useMemo(
    () => new Set((rentals.data ?? []).map((rental) => rental.property_id)),
    [rentals.data],
  );

  const filtered = useMemo(() => {
    const list = properties.data ?? [];
    if (!search.trim()) return list;
    const q = search.toLowerCase();
    return list.filter((p) => p.name.toLowerCase().includes(q) || (p.location || "").toLowerCase().includes(q));
  }, [properties.data, search]);

  const myRentals = useMemo(
    () => filtered.filter((property) => activeRentalIds.has(property.id) || property.current_cycle_paid),
    [activeRentalIds, filtered],
  );
  const availableRentals = useMemo(
    () =>
      filtered.filter(
        (property) =>
          Number(property.tokens_sold ?? 0) > 0 &&
          !activeRentalIds.has(property.id) &&
          !property.current_cycle_paid,
      ),
    [activeRentalIds, filtered],
  );

  return (
    <>
      <AdminTopbar title="Rentals" subtitle="Browse properties and pay rent directly via the RentDistribution contract" />
      <main className="flex-1 space-y-5 p-4 lg:p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold">Rental Properties</h2>
            <p className="text-xs text-muted-foreground">Search by property name or location and pay rent directly on-chain.</p>
          </div>
          <div className="relative w-full md:w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search properties…" className="h-9 pl-8 text-sm" />
          </div>
        </div>

        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold">My Rentals</h3>
            <p className="text-xs text-muted-foreground">Paid and active rental properties.</p>
          </div>
          {properties.isLoading || rentals.isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[410px] rounded-xl" />)}
            </div>
          ) : myRentals.length === 0 ? (
            <EmptyState title="No paid rentals yet" description="Paid rentals will appear here after confirmation." />
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {myRentals.map((property) => (
                <RentalCard key={property.id} property={property} wallet={wallet} isActiveRental />
              ))}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold">Available Rentals</h3>
            <p className="text-xs text-muted-foreground">Properties with investor ownership and rent enabled.</p>
          </div>
          {properties.isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[410px] rounded-xl" />)}
            </div>
          ) : availableRentals.length === 0 ? (
            <EmptyState title="No available rentals" description="Try a different search term or wait for rent-ready properties." />
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {availableRentals.map((property) => (
                <RentalCard key={property.id} property={property} wallet={wallet} isActiveRental={false} />
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  );
}

function RentalCard({
  property,
  wallet,
  isActiveRental,
}: {
  property: Property & {
    rent_enabled?: boolean;
    current_cycle_paid?: boolean;
    rent_cycle_label?: string;
    next_rent_due_at?: string | null;
  };
  wallet: string | null;
  isActiveRental: boolean;
}) {
  const sold = Number(property.tokens_sold ?? 0);
  const supply = Number(property.token_supply ?? 0);
  const soldPct = Number(property.sold_percentage ?? percent(sold, supply));
  const monthlyRent = Number(property.monthly_rent_eth ?? 0);
  const [open, setOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    if (takePendingModalOpen("PAY_RENT", property.id)) {
      setOpen(true);
    }
    return subscribeWorkflowAction((action) => {
      if (!isWorkflowModalAction(action, "PAY_RENT")) return;
      if (action.type === "OPEN_MODAL" && workflowPropertyMatches(action, property.id)) {
        setOpen(true);
      }
    });
  }, [property.id]);

  return (
    <>
      <Card
        role="button"
        tabIndex={0}
        className="group cursor-pointer overflow-hidden transition-transform duration-200 hover:-translate-y-0.5"
        onClick={() => setDetailOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setDetailOpen(true);
          }
        }}
      >
        <PropertyImageCarousel images={property.images?.slice(0, 1)} propertyId={property.id} title={property.name} className="h-44" />
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="shrink-0 text-base font-semibold text-foreground">#{property.id}</span>
                <h3 className="truncate text-base font-semibold">{property.name}</h3>
                <Badge variant="outline" className="shrink-0 rounded-md px-2 py-0 font-mono text-xs">{property.token_symbol}</Badge>
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                <MapPin className="h-3 w-3" /> {property.location}
              </div>
            </div>
            <Badge variant={isActiveRental ? "success" : property.rent_enabled ? "success" : "warning"} className="h-5 shrink-0 rounded-md px-2 text-[10px]">
              {isActiveRental ? "Renting" : property.rent_enabled ? "Rent ready" : "Rent not set"}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Fact label="Monthly Rent" value={monthlyRent > 0 ? `${monthlyRent.toFixed(4)} ETH` : "Not set"} />
            <Fact label="Property Value" value={formatCurrency(property.total_value)} />
            <Fact label="Supply" value={formatNumber(supply)} />
            <Fact label="Ownership Sold" value={`${soldPct.toFixed(1)}%`} />
          </div>
          <div>
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Token Sale Progress</span>
              <span className="font-medium tabular-nums">{formatNumber(sold)} / {formatNumber(supply)}</span>
            </div>
            <Progress value={soldPct} className="h-1.5" />
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
            <div className="min-w-0 text-[11px] text-muted-foreground font-mono">{shortAddress(property.token_address, 6, 4)}</div>
            <Button
              size="sm"
              variant={property.current_cycle_paid ? "secondary" : "default"}
              disabled={!wallet || !property.rent_enabled || property.current_cycle_paid}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(true);
              }}
            >
              {property.current_cycle_paid ? (
                <>
                  <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                  Paid ✔
                </>
              ) : (
                <>
                  <Receipt className="mr-1 h-3.5 w-3.5" />
                  Rent Now
                </>
              )}
            </Button>
          </div>
          {property.current_cycle_paid ? (
            <div className="rounded-md border border-success/25 bg-success/5 px-3 py-2 text-xs font-medium text-success">
              Rent paid for this period.
              {property.next_rent_due_at ? (
                <span className="mt-0.5 block font-normal text-success/90">
                  Next due {formatDateTime(property.next_rent_due_at)}
                </span>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <PropertyDetailDialog
        property={property}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        statusLabel={isActiveRental ? "Renting" : property.rent_enabled ? "Rent ready" : "Rent not set"}
        actionLabel={property.current_cycle_paid ? "Paid ✔" : "Rent Now"}
        actionDisabled={!wallet || !property.rent_enabled || property.current_cycle_paid}
        onAction={() => {
          setDetailOpen(false);
          setOpen(true);
        }}
      />
      <PayRentDialog property={property} wallet={wallet} open={open} onOpenChange={setOpen} />
    </>
  );
}

function PayRentDialog({ property, wallet, open, onOpenChange }: { property: Property; wallet: string | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient();
  const preview = useTenantDistributionPreview(property.id);
  const formRef = useRef<HTMLFormElement | null>(null);
  const [step, setStep] = useState<"idle" | "prepare" | "wallet" | "mine" | "confirm">("idle");
  const [busy, setBusy] = useState(false);
  const monthlyRentEth = Number(property.monthly_rent_eth ?? 0);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!wallet || !property.id) return;
    // Defensive guard: if the dialog gets a SUBMIT_FORM event (from the
    // agent or otherwise) for a cycle that's already paid, do not open
    // MetaMask. Surface a clear completion-error so the agent can explain
    // the rent is already paid + next due date.
    const propWithStatus = property as Property & {
      current_cycle_paid?: boolean;
      next_rent_due_at?: string | null;
    };
    if (propWithStatus.current_cycle_paid) {
      const nextDue = propWithStatus.next_rent_due_at
        ? formatDateTime(propWithStatus.next_rent_due_at)
        : "next cycle";
      const errMsg = `Rent for ${property.name} is already paid for this cycle. Next due ${nextDue}.`;
      toast.info(errMsg);
      clearPendingWorkflowActions("PAY_RENT");
      emitWorkflowCompletion({ modal: "PAY_RENT", status: "error", message: errMsg });
      onOpenChange(false);
      return;
    }
    setBusy(true);
    try {
      setStep("prepare");
      const prepared = await api.get<PayRentPrepareResponse>(`/tenant/pay-rent/prepare/${property.id}`, {
        tenant_wallet: wallet,
      });
      setStep("wallet");
      const tx = await sendPayRentTx({ rentContractAddress: prepared.rent_contract_address, propertyId: property.id, valueWei: prepared.monthly_rent_wei });
      setStep("mine");
      const receipt = await tx.wait();
      setStep("confirm");
      await api.post(`/tenant/pay-rent/confirm/${property.id}`, { tx_hash: tx.hash, tenant_wallet: wallet });
      toast.success(`Rent paid! Block ${receipt?.blockNumber ?? "latest"}.`);
      clearPendingWorkflowActions("PAY_RENT");
      emitWorkflowCompletion({
        modal: "PAY_RENT",
        status: "success",
        message: `Rent payment confirmed for ${property.name}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["tenant"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.tenantProperties(wallet) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tenantActiveRentals(wallet) });
      queryClient.invalidateQueries({ queryKey: queryKeys.transactions });
      queryClient.invalidateQueries({ queryKey: ["investor"] });
      onOpenChange(false);
      setStep("idle");
    } catch (err: any) {
      clearPendingWorkflowActions("PAY_RENT");
      const errMsg = err?.message || "Rent payment failed.";
      toast.error(errMsg);
      emitWorkflowCompletion({ modal: "PAY_RENT", status: "error", message: errMsg });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    return subscribeWorkflowAction((action) => {
      if (!isWorkflowModalAction(action, "PAY_RENT")) return;
      if (action.property_id !== undefined && !workflowPropertyMatches(action, property.id)) return;
      if (action.type === "SUBMIT_FORM") {
        setStep("prepare");
        const trySubmit = (attemptsLeft: number) => {
          window.setTimeout(() => {
            if (formRef.current) {
              formRef.current.requestSubmit();
              return;
            }
            if (attemptsLeft > 0) trySubmit(attemptsLeft - 1);
          }, 180);
        };
        trySubmit(24);
      }
    });
  }, [property.id]);

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="max-w-md"
        onPointerDownOutside={preventCloseFromWorkflowBubble}
        onInteractOutside={preventCloseFromWorkflowBubble}
      >
        <DialogHeader>
          <DialogTitle>Pay Rent — {property.name}</DialogTitle>
          <DialogDescription>Send rent to the RentDistribution contract. Investors will receive their share automatically.</DialogDescription>
        </DialogHeader>
        <form ref={formRef} onSubmit={onSubmit} className="space-y-4" data-workflow-form="PAY_RENT">
          <input data-workflow-field="PAY_RENT.confirm" type="hidden" value="ready" readOnly />
          <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/30 p-3 text-xs">
            <Fact label="Monthly rent" value={`${monthlyRentEth.toFixed(4)} ETH`} />
            <Fact label="Wallet" value={shortAddress(wallet, 6, 4)} />
            <Fact label="Property ID" value={`#${property.id}`} />
            <Fact label="Location" value={property.location} />
          </div>

          {preview.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : preview.data ? (
            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mb-2">Distribution preview ({preview.data.investor_count} investors)</div>
              <div className="max-h-32 overflow-y-auto space-y-1 scrollbar-thin">
                {preview.data.breakdown.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No investors to distribute to yet.</div>
                ) : (
                  preview.data.breakdown.map((b, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="font-mono text-[11px]">{shortAddress(b.investor, 6, 4)}</span>
                      <span className="tabular-nums">{b.payout_eth} ETH ({b.ownership_pct}%)</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}

          <div className="space-y-2 text-xs text-muted-foreground">
            <Step active={step === "prepare"} done={["wallet", "mine", "confirm"].includes(step)} icon={ShieldCheck} label="Preparing payment quote" />
            <Step active={step === "wallet"} done={["mine", "confirm"].includes(step)} icon={Wallet} label="Confirming transaction in MetaMask" />
            <Step active={step === "mine"} done={step === "confirm"} icon={CreditCard} label="Mining on blockchain" />
            <Step active={step === "confirm"} done={false} icon={Receipt} label="Indexing & confirming" />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button
              type="submit"
              disabled={busy || !wallet || !property.rent_enabled || property.current_cycle_paid}
            >
              {busy ? "Processing…" : "Pay Rent via MetaMask"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="flex flex-col gap-0.5"><span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span><span className="font-medium tabular-nums">{value}</span></div>;
}

function Step({ active, done, icon: Icon, label }: { active: boolean; done: boolean; icon: React.ComponentType<{ className?: string }>; label: string }) {
  return <div className={cn("flex items-center gap-2 rounded-md border border-border px-2.5 py-2", active && "border-primary/40 bg-primary/5 text-primary", done && "border-success/40 bg-success/5 text-success")}><Icon className="h-3.5 w-3.5" /> {label}</div>;
}
