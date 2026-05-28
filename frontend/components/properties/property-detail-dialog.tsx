"use client";

import { useMemo, useState } from "react";
import { BadgeCheck, Check, Copy, MapPin, Pencil, Receipt } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  InvestorPropertyDetailContent,
  InvestorPropertyDetailFooter,
} from "@/components/investor/investor-property-detail-content";
import {
  investorPropertyDetailDialogClass,
  investorPropertyDetailScrollBodyClass,
  propertyDetailScrollBodyClass,
} from "@/components/properties/property-form-shared";
import { PropertyImageGallery } from "@/components/properties/property-image-gallery";
import { availablePropertyTokens, propertyIsInvestable, propertyUnitValue } from "@/components/investor/investor-utils";
import { useProperty, useTransactions } from "@/lib/queries";
import { addressExplorerUrl, RUNTIME_CONFIG } from "@/lib/runtime-config";
import type { Property, Role } from "@/lib/types";
import { cn, formatCurrency, formatDateTime, formatNumber, percent, shortAddress } from "@/lib/utils";

export type PropertyDetailRole = Role;

const CHAIN_LABELS: Record<number, string> = {
  1: "Ethereum Mainnet",
  11155111: "Sepolia",
};

function chainLabel(): string {
  return CHAIN_LABELS[RUNTIME_CONFIG.chainId] ?? `Chain ${RUNTIME_CONFIG.chainId}`;
}

function propertyDescription(property: Property): string {
  const location = property.location || "its listed region";
  const rentNote = property.rent_enabled
    ? " Rental yield is distributed on-chain to token holders when rent is collected."
    : " Rent distribution can be enabled once the owner configures monthly rent on-chain.";
  return `${property.name} is a tokenized real estate listing in ${location}. Ownership is represented by ${property.token_symbol} security tokens on ${chainLabel()}.${rentNote}`;
}

function deriveFinancialOverview(property: Property) {
  const monthlyRent = Number(property.monthly_rent_eth ?? 0);
  const tokenPrice = Number(property.token_sale_price_eth ?? 0);
  const supply = Number(property.token_supply ?? 0);
  const navEth = tokenPrice > 0 && supply > 0 ? tokenPrice * supply : 0;
  const annualRentEth = monthlyRent > 0 ? monthlyRent * 12 : 0;

  if (!navEth || !annualRentEth) return null;

  const expectedRoi = (annualRentEth / navEth) * 100;
  return {
    expectedRoi: `${expectedRoi.toFixed(1)}%`,
    netYield: `${(expectedRoi * 0.66).toFixed(1)}%`,
    payback: `${(navEth / annualRentEth).toFixed(1)} Years`,
  };
}

export function PropertyDetailDialog({
  property: initialProperty,
  open,
  onOpenChange,
  role = "property_owner",
  wallet,
  onPrimaryAction,
  primaryDisabled,
  isActiveRental,
  statusLabel,
  actionLabel,
  actionDisabled,
  onAction,
}: {
  property: Property | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  role?: PropertyDetailRole;
  wallet?: string | null;
  onPrimaryAction?: () => void;
  primaryDisabled?: boolean;
  isActiveRental?: boolean;
  statusLabel?: string;
  actionLabel?: string;
  actionDisabled?: boolean;
  onAction?: () => void;
}) {
  const propertyQuery = useProperty(open ? initialProperty?.id : null);
  const transactionsQuery = useTransactions();
  const property = propertyQuery.data ?? initialProperty;
  const loading = propertyQuery.isLoading && !property;
  const isInvestor = role === "investor";

  const sold = Number(property?.tokens_sold ?? 0);
  const supply = Number(property?.token_supply ?? 0);
  const soldPct = Number(property?.sold_percentage ?? percent(sold, supply));
  const tokenPrice = Number(property?.token_sale_price_eth ?? 0);
  const monthlyRent = Number(property?.monthly_rent_eth ?? 0);
  const available = property ? availablePropertyTokens(property) : 0;
  const investable = property ? propertyIsInvestable(property) : false;
  const unitValue = propertyUnitValue(property);
  const rentReady = Boolean(property?.rent_enabled && monthlyRent > 0);
  const financials = property ? deriveFinancialOverview(property) : null;
  const creatorWallet = useMemo(() => {
    if (!property) return null;
    if (property.owner_wallet) return property.owner_wallet;

    const creatorTx = (transactionsQuery.data ?? []).find((tx) => {
      if (!tx.wallet_address || String(tx.property_id ?? "") !== String(property.id)) return false;
      const type = tx.type?.toLowerCase() ?? "";
      return (
        type.includes("property_listing") ||
        type.includes("property_token_deployment") ||
        type.includes("mint_nft") ||
        type.includes("token_deployed")
      );
    });
    return creatorTx?.wallet_address ?? null;
  }, [property, transactionsQuery.data]);

  if (!initialProperty && !open) return null;

  const effectivePrimaryAction = onPrimaryAction ?? onAction;
  const effectivePrimaryDisabled = primaryDisabled ?? actionDisabled;
  const primaryLabel = actionLabel ?? (role === "tenant"
      ? property?.current_cycle_paid
        ? "Rent paid"
        : "Pay rent"
      : "Edit property");

  const primaryIcon = role === "tenant" ? Receipt : Pencil;

  const footerHint =
    role === "tenant"
      ? property?.current_cycle_paid
        ? property.next_rent_due_at
          ? `Next rent due ${formatDateTime(property.next_rent_due_at)}.`
          : "Rent is paid for the current cycle."
        : rentReady
          ? "Pay rent via MetaMask to the RentDistribution contract."
          : "Rent has not been configured for this property."
      : "Update listing details, images, and pricing from the admin panel.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={
          isInvestor
            ? investorPropertyDetailDialogClass
            : cn(
                "flex min-h-0 w-[min(calc(100vw-1rem),580px)] max-w-[580px] max-h-[min(92vh,920px)] flex-col gap-0 overflow-hidden p-0 sm:rounded-2xl",
              )
        }
      >
        {loading || !property ? (
          <div
            className={cn(
              isInvestor ? investorPropertyDetailScrollBodyClass : propertyDetailScrollBodyClass,
              "space-y-4 p-6",
            )}
          >
            <Skeleton className="aspect-[16/10] w-full rounded-xl" />
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : isInvestor ? (
          <>
            <div className={cn(investorPropertyDetailScrollBodyClass, "px-4 py-3.5")}>
              <InvestorPropertyDetailContent property={property} />
            </div>
            {onPrimaryAction ? (
              <InvestorPropertyDetailFooter
                wallet={wallet}
                investable={investable}
                disabled={primaryDisabled}
                onInvest={() => {
                  onOpenChange(false);
                  onPrimaryAction();
                }}
              />
            ) : null}
          </>
        ) : (
          <>
            <div className={propertyDetailScrollBodyClass}>
              <div className="p-4 pb-3.5">
                <DialogHeader className="space-y-2.5 p-0 text-left">
                  <div className="flex flex-wrap items-start justify-between gap-2 pr-6">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <DialogTitle className="text-base font-semibold leading-tight tracking-tight">
                          #{property.id} {property.name}
                        </DialogTitle>
                        <Badge variant="outline" className="h-4 px-1.5 font-mono text-[9px] font-semibold uppercase tracking-wide">
                          {property.token_symbol}
                        </Badge>
                      </div>
                      <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                        <MapPin className="h-3 w-3 shrink-0" />
                        {property.location || "—"}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                      {statusLabel ? (
                        <Badge variant={statusLabel.toLowerCase().includes("not") ? "muted" : "success"} className="h-5 px-1.5 text-[10px]">
                          {statusLabel}
                        </Badge>
                      ) : rentReady ? (
                        <Badge variant="success" className="h-5 px-1.5 text-[10px]">
                          Rent ready
                        </Badge>
                      ) : (
                        <Badge variant="muted" className="h-5 px-1.5 text-[10px]">
                          Rent not set
                        </Badge>
                      )}
                      {isActiveRental ? (
                        <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                          Active rental
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </DialogHeader>

                <div className="mt-3">
                  <PropertyImageGallery
                    variant="compact"
                    images={property.images}
                    propertyId={property.id}
                    title={property.name}
                  />
                </div>

                <div className="mt-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
                  <div className="grid grid-flow-col auto-cols-max items-start justify-between gap-x-4">
                    <StatPill label="Monthly rent" value={monthlyRent > 0 ? `${monthlyRent.toFixed(4)} ETH` : "—"} />
                    <StatPill label="Property value" value={formatCurrency(property.total_value)} />
                    <StatPill label="Supply" value={formatNumber(supply)} />
                    <StatPill label="Ownership sold" value={`${soldPct.toFixed(1)}%`} />
                    <StatPill
                      label="Token price"
                      value={tokenPrice > 0 ? `${tokenPrice.toFixed(4)} ETH` : "—"}
                      subValue={unitValue > 0 ? `~${formatCurrency(unitValue)}` : undefined}
                    />
                  </div>
                  <div className="mt-2.5 border-t border-border pt-2.5">
                    <div className="mb-1 flex items-center justify-between text-[11px]">
                      <span className="text-muted-foreground">Token sale progress</span>
                      <span className="font-semibold tabular-nums text-foreground">
                        {formatNumber(sold)} / {formatNumber(supply)}
                      </span>
                    </div>
                    <Progress value={soldPct} className="h-1 bg-muted" indicatorClassName="bg-primary" />
                  </div>
                </div>

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <InfoCard title="Property description">
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      {propertyDescription(property)}
                    </p>
                  </InfoCard>

                  <InfoCard title="Property details">
                    <InfoRow label="Location" value={property.location || "—"} />
                    <InfoRow label="Token symbol" value={property.token_symbol} />
                    <InfoRow label="Total supply" value={formatNumber(supply)} />
                    <InfoRow label="Available tokens" value={formatNumber(available)} />
                    <InfoRow
                      label="Monthly rent"
                      value={monthlyRent > 0 ? `${monthlyRent.toFixed(4)} ETH` : "Not set"}
                    />
                  </InfoCard>

                  <InfoCard title="Financial overview">
                    {financials ? (
                      <>
                        <InfoRow label="Expected ROI (annual)" value={financials.expectedRoi} />
                        <InfoRow label="Net yield (annual)" value={financials.netYield} />
                        <InfoRow label="Payback period" value={financials.payback} />
                      </>
                    ) : (
                      <p className="text-xs leading-relaxed text-muted-foreground">
                        Configure monthly rent on this listing to display yield estimates.
                      </p>
                    )}
                  </InfoCard>

                  <InfoCard title="Smart contract">
                    <CopyRow
                      label="Contract address"
                      value={property.token_address}
                      fallback="Pending deployment"
                      explorer={
                        property.token_address ? addressExplorerUrl(property.token_address) : undefined
                      }
                    />
                    <InfoRow label="Token standard" value={property.nft_token_id != null ? "ERC-721" : property.token_address ? "ERC-20" : "—"} />
                    <CopyRow
                      label="Created by"
                      value={creatorWallet}
                      fallback="Creator not recorded"
                      mono
                      explorer={creatorWallet ? addressExplorerUrl(creatorWallet) : undefined}
                    />
                    <InfoRow
                      label="Verified"
                      value={
                        property.token_address ? (
                          <span className="inline-flex items-center gap-1 text-success">
                            <BadgeCheck className="h-3.5 w-3.5" /> Yes
                          </span>
                        ) : (
                          "Pending"
                        )
                      }
                    />
                  </InfoCard>
                </div>
              </div>
            </div>

            <Separator />

            <DialogFooter className="flex shrink-0 flex-row items-center justify-between gap-2 border-t border-border bg-card px-4 py-2">
              <span className="min-w-0 truncate font-mono text-[11px] text-muted-foreground">
                {wallet ? shortAddress(wallet, 6, 4) : property.owner_wallet ? shortAddress(property.owner_wallet, 6, 4) : footerHint}
              </span>
              <div className="flex shrink-0 gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                  Close
                </Button>
                {effectivePrimaryAction ? (
                  <Button
                    type="button"
                    size="sm"
                    disabled={effectivePrimaryDisabled}
                    onClick={() => {
                      onOpenChange(false);
                      effectivePrimaryAction();
                    }}
                  >
                    {primaryLabel}
                    {(() => {
                      const Icon = primaryIcon;
                      return <Icon className="h-3.5 w-3.5" />;
                    })()}
                  </Button>
                ) : null}
              </div>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function StatPill({ label, value, subValue }: { label: string; value: React.ReactNode; subValue?: React.ReactNode }) {
  return (
    <div className="min-w-0 text-left">
      <div className="whitespace-nowrap text-[10px] font-semibold uppercase leading-none tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 max-w-[7.25rem] truncate text-[18px] font-semibold leading-tight tabular-nums text-foreground">
        {value}
      </div>
      {subValue ? <div className="mt-0.5 truncate text-xs font-medium text-muted-foreground">{subValue}</div> : null}
    </div>
  );
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-2.5">
      <h4 className="text-xs font-semibold text-foreground">{title}</h4>
      <div className="mt-1.5 space-y-1.5">{children}</div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="min-w-0 text-muted-foreground">{label}</span>
      <span className="shrink-0 text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

function CopyRow({
  label,
  value,
  fallback,
  explorer,
  mono,
}: {
  label: string;
  value?: string | null;
  fallback: string;
  explorer?: string;
  mono?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const display = value ? shortAddress(value, 8, 6) : fallback;

  async function copy() {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success("Copied to clipboard");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy");
    }
  }

  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-1">
        {explorer ? (
          <a
            href={explorer}
            target="_blank"
            rel="noreferrer"
            className={cn("truncate font-medium text-primary hover:underline", mono && "font-mono")}
            onClick={(e) => e.stopPropagation()}
          >
            {display}
          </a>
        ) : (
          <span className={cn("truncate font-medium", mono && "font-mono")}>{display}</span>
        )}
        {value ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              void copy();
            }}
          >
            {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
