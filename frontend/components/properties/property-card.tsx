"use client";

import { motion } from "framer-motion";
import { Archive, CheckCircle2, MapPin, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useDeleteProperty } from "@/lib/mutations";
import { useEditPropertyDialog } from "./edit-property-dialog";
import { PropertyImageCarousel } from "@/components/properties/property-image-carousel";
import { PropertyDetailDialog } from "@/components/properties/property-detail-dialog";
import type { Property } from "@/lib/types";
import { cn, formatCurrency, formatNumber, percent, shortAddress } from "@/lib/utils";
import { isWorkflowModalAction, subscribeWorkflowAction, workflowPropertyMatches } from "@/lib/ai/action-executor";
import { useEffect, useState } from "react";
import { useCurrentWallet } from "@/components/investor/use-current-wallet";

export function PropertyCard({ property }: { property: Property }) {
  const remove = useDeleteProperty();
  const { openEdit } = useEditPropertyDialog();
  const wallet = useCurrentWallet();
  const [detailOpen, setDetailOpen] = useState(false);
  const canManage = Boolean(
    wallet && property.owner_wallet && property.owner_wallet.toLowerCase() === wallet.toLowerCase(),
  );

  const sold = Number(property.tokens_sold ?? 0);
  const total = Number(property.token_supply ?? 0);
  const soldPct = Number(property.sold_percentage ?? percent(sold, total));
  const tokenPriceEth = Number(property.token_sale_price_eth ?? 0);
  const monthlyRentEth = Number(property.monthly_rent_eth ?? 0);

  useEffect(() => {
    return subscribeWorkflowAction((action) => {
      if (!canManage) return;
      if (!isWorkflowModalAction(action, "EDIT_PROPERTY")) return;
      if (action.type === "OPEN_MODAL" && workflowPropertyMatches(action, property.id)) {
        openEdit(property);
      }
    });
  }, [canManage, openEdit, property]);

  async function handleArchive() {
    if (!window.confirm(`Archive or delete ${property.name}? Active on-chain/history records will be preserved.`)) return;
    try {
      const result = await remove.mutateAsync(property.id);
      toast.success(result.mode === "archived" ? "Property archived." : "Property deleted.");
    } catch (e: any) {
      toast.error(e?.message || "Archive failed.");
    }
  }

  return (
    <>
      <motion.div
        layout
        role="button"
        tabIndex={0}
        whileHover={{ y: -2 }}
        className="group relative flex cursor-pointer flex-col overflow-hidden rounded-2xl border border-border/60 bg-card/[0.82] shadow-[0_20px_60px_-38px_hsl(var(--foreground)/0.45)] backdrop-blur-2xl"
        onClick={() => setDetailOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setDetailOpen(true);
          }
        }}
      >
        <PropertyImageCarousel images={property.images?.slice(0, 1)} propertyId={property.id} title={property.name} className="h-44 w-full">
          {canManage ? (
            <div className="absolute right-3 top-3 flex items-center gap-1 rounded-full border border-border/60 bg-background/80 p-1 shadow-sm backdrop-blur">
              <TooltipProvider delayDuration={150}>
                <IconAction
                  icon={<Pencil className="h-3.5 w-3.5" />}
                  label="Edit"
                  onClick={() => openEdit(property)}
                />
                <IconAction
                  icon={<Archive className="h-3.5 w-3.5" />}
                  label="Archive or delete"
                  busy={remove.isPending}
                  onClick={handleArchive}
                />
              </TooltipProvider>
            </div>
          ) : null}
        </PropertyImageCarousel>

      <div className="flex flex-1 flex-col gap-2.5 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1.5 text-base font-semibold leading-tight">
            <span className="shrink-0 text-foreground">#{property.id}</span>
            <h3 className="min-w-0 truncate">{property.name}</h3>
            <Badge variant="outline" className="shrink-0 rounded-md px-2 py-0 font-mono text-xs">{property.token_symbol}</Badge>
          </div>
          <Badge variant={property.token_address ? "success" : "warning"} className="h-5 shrink-0 rounded-md px-2 text-[10px]">
            {property.token_address ? "Ready" : "Setup pending"}
          </Badge>
        </div>
        <div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3" />
            <span className="truncate">{property.location}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-xs">
          <Stat label="Total Value" value={formatCurrency(property.total_value)} />
          <Stat label="Token Price" value={`${tokenPriceEth.toFixed(4)} ETH`} />
          <Stat label="Supply" value={formatNumber(total)} />
          <Stat label="Available" value={formatNumber(Number(property.tokens_available ?? 0))} />
          <Stat label="Rent" value={monthlyRentEth > 0 ? `${monthlyRentEth.toFixed(4)} ETH/mo` : "Not set"} />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Tokens Sold</span>
            <span className="tabular-nums font-medium">
              {formatNumber(sold)} / {formatNumber(total)} ({soldPct.toFixed(1)}%)
            </span>
          </div>
          <Progress
            value={soldPct}
            className="h-1.5"
            indicatorClassName={cn(
              soldPct >= 60 ? "bg-success" : soldPct >= 30 ? "bg-chart-2" : "bg-chart-4",
            )}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {property.token_address ? (
            <span className="font-mono text-[10px]">{shortAddress(property.token_address, 6, 4)}</span>
          ) : null}
          {property.nft_token_id ? (
            <Badge variant="outline" className="ml-auto rounded-md">
              <CheckCircle2 className="mr-1 h-3 w-3" /> NFT #{property.nft_token_id}
            </Badge>
          ) : null}
        </div>

        </div>
      </motion.div>
      <PropertyDetailDialog
        property={property}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        actionLabel={canManage ? "Edit Property" : undefined}
        onAction={
          canManage
            ? () => {
                setDetailOpen(false);
                openEdit(property);
              }
            : undefined
        }
      />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="mt-0.5 block truncate text-sm font-medium tabular-nums">{value}</span>
    </div>
  );
}

function IconAction({
  icon,
  label,
  onClick,
  busy,
  variant,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  busy?: boolean;
  variant?: "primary";
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={variant === "primary" ? "default" : "ghost"}
          size="icon"
          className="h-7 w-7 rounded-full"
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation();
            onClick();
          }}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
