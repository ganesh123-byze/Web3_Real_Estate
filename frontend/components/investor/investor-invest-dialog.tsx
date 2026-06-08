"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, ShieldCheck, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { formatWalletTransactionError } from "@/lib/wallet-errors";
import { queryKeys, useWalletBalances } from "@/lib/queries";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  formatInvestDialogText,
  formatInvestEthAmount,
  formatInvestEthFromWei,
} from "@/components/investor/investor-display-format";
import { cn, formatNumber, shortAddress } from "@/lib/utils";
import type { InvestmentPrepareResponse, Property } from "@/lib/types";
import { currentSessionIdentity, identityDisplayName } from "@/lib/identity";
import { parseWalletNativeBalanceWei } from "@/components/investor/investor-funding-utils";
import { checkManualInvestOrder } from "@/components/investor/investor-invest-order-utils";
import {
  isInvestDialogTransactionInFlight,
  isInvestSubmitDisabled,
  resolveInvestOrderBalanceWei,
  shouldShowInvestPreSubmitOrderFeedback,
  type InvestDialogStep,
} from "@/components/investor/investor-invest-dialog-utils";
import {
  INVEST_TOKEN_AMOUNT_HINT,
  INVEST_TOKEN_AMOUNT_MIN_ERROR,
  investmentCostWei,
  validateInvestTokenAmountInput,
} from "@/components/investor/investor-utils";
import { sendInvestmentTx } from "@/components/investor/contract-actions";
import {
  clearPendingWorkflowActions,
  emitWorkflowCompletion,
  focusWorkflowField,
  getWorkflowFormValues,
  isWorkflowModalAction,
  preventCloseFromWorkflowBubble,
  subscribeWorkflowAction,
  workflowPropertyMatches,
} from "@/lib/ai/action-executor";

export function InvestorInvestDialog({
  property,
  wallet,
  open,
  onOpenChange,
}: {
  property: Property;
  wallet: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const formRef = useRef<HTMLFormElement | null>(null);
  const [amount, setAmount] = useState("1");
  const [step, setStep] = useState<InvestDialogStep>("idle");
  const [busy, setBusy] = useState(false);
  const [lockedFundingBalanceWei, setLockedFundingBalanceWei] = useState<bigint | null>(null);
  const walletBalances = useWalletBalances(open ? wallet : null);
  const amountValidation = validateInvestTokenAmountInput(amount);
  const tokenAmount = amountValidation.valid ? amountValidation.wholeAmount : 0;
  const costWei = investmentCostWei(property, tokenAmount);
  const walletBalanceWei = parseWalletNativeBalanceWei(walletBalances.data);
  const balanceWeiForOrderCheck = resolveInvestOrderBalanceWei({
    step,
    busy,
    liveBalanceWei: walletBalanceWei,
    lockedBalanceWei: lockedFundingBalanceWei,
  });
  const orderCheck = useMemo(
    () =>
      checkManualInvestOrder({
        property,
        tokenAmount,
        costWei,
        balanceWei: balanceWeiForOrderCheck,
      }),
    [property, costWei, balanceWeiForOrderCheck, tokenAmount],
  );
  const showPreSubmitOrderFeedback = shouldShowInvestPreSubmitOrderFeedback(step, busy);
  const submitDisabled = isInvestSubmitDisabled({
    busy,
    step,
    amountValid: amountValidation.valid,
    wallet,
    orderCheck,
    balanceLoading: walletBalances.isLoading,
  });
  const sessionIdentity = currentSessionIdentity();
  const walletLabel =
    wallet && sessionIdentity?.wallet_address?.toLowerCase() === wallet.toLowerCase()
      ? identityDisplayName(sessionIdentity, wallet)
      : shortAddress(wallet, 6, 4);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const workflowValues = getWorkflowFormValues("INVEST_PROPERTY");
    const submitValidation = validateInvestTokenAmountInput(
      String(workflowValues.token_amount ?? amount ?? ""),
    );
    if (!submitValidation.valid) {
      setStep("idle");
      toast.error(submitValidation.error ?? INVEST_TOKEN_AMOUNT_MIN_ERROR);
      return;
    }
    const submitAmount = submitValidation.wholeAmount;
    const submitCostWei = investmentCostWei(property, submitAmount);
    const submitOrder = checkManualInvestOrder({
      property,
      tokenAmount: submitAmount,
      costWei: submitCostWei,
      balanceWei: parseWalletNativeBalanceWei(walletBalances.data),
    });
    if (!submitOrder.ok) {
      setStep("idle");
      const message =
        submitOrder.error ??
        (submitOrder.reason === "balance_pending"
          ? "Your wallet balance is still loading. Please wait a moment and try again."
          : "This investment cannot be submitted right now. Please review the amount and try again.");
      toast.error(formatInvestDialogText(message));
      return;
    }
    if (!wallet || !property.token_address) return;
    const fundingBalanceWei = parseWalletNativeBalanceWei(walletBalances.data);
    if (fundingBalanceWei !== null) {
      setLockedFundingBalanceWei(fundingBalanceWei);
    }
    setBusy(true);
    try {
      setStep("prepare");
      const prepared = await api.post<InvestmentPrepareResponse>("/investments/prepare", {
        property_id: property.id,
        investor_wallet: wallet,
        token_amount: submitAmount,
      });
      setStep("wallet");
      const tx = await sendInvestmentTx({
        tokenAddress: property.token_address,
        propertyId: property.id,
        tokenAmount: submitAmount,
        valueWei: prepared.eth_amount_wei,
      });
      const receipt = await tx.wait();
      setStep("confirm");
      await api.post(`/investments/${prepared.investment_id}/confirm`, { tx_hash: tx.hash });
      toast.success(`Investment confirmed in block ${receipt?.blockNumber ?? "latest"}.`);
      clearPendingWorkflowActions("INVEST_PROPERTY");
      emitWorkflowCompletion({
        modal: "INVEST_PROPERTY",
        status: "success",
        message: `Investment confirmed: ${submitAmount} ${property.token_symbol || "tokens"} in ${property.name}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["investor"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.properties });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("estatechain:ai-data-changed"));
      }
      onOpenChange(false);
      setStep("idle");
    } catch (err: unknown) {
      clearPendingWorkflowActions("INVEST_PROPERTY");
      setStep("idle");
      setLockedFundingBalanceWei(null);
      const errMsg = formatWalletTransactionError(err, "Investment failed. Please try again.");
      toast.error(errMsg);
      emitWorkflowCompletion({ modal: "INVEST_PROPERTY", status: "error", message: errMsg });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (open) return;
    setStep("idle");
    setBusy(false);
    setLockedFundingBalanceWei(null);
  }, [open]);

  useEffect(() => {
    const handleAction = (action: Parameters<Parameters<typeof subscribeWorkflowAction>[0]>[0]) => {
      if (!isWorkflowModalAction(action, "INVEST_PROPERTY")) return;
      if (action.property_id !== undefined && !workflowPropertyMatches(action, property.id)) return;
      if (action.type === "FILL_FIELD" && action.field === "token_amount") {
        setAmount(String(action.value ?? ""));
        return;
      }
      if (action.type === "FOCUS_FIELD" && action.field) {
        window.setTimeout(() => focusWorkflowField("INVEST_PROPERTY", action.field!), 80);
        return;
      }
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
    };

    return subscribeWorkflowAction(handleAction);
  }, [property.id]);

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent
        className="max-w-md"
        onPointerDownOutside={preventCloseFromWorkflowBubble}
        onInteractOutside={preventCloseFromWorkflowBubble}
      >
        <DialogHeader>
          <DialogTitle>Invest in {property.name}</DialogTitle>
          <DialogDescription>
            Buy ownership tokens directly from the property SecurityToken contract.
          </DialogDescription>
        </DialogHeader>
        <form ref={formRef} onSubmit={onSubmit} className="space-y-4" data-workflow-form="INVEST_PROPERTY">
          <div className="grid gap-1.5">
            <Label>Token amount</Label>
            <Input
              data-workflow-field="INVEST_PROPERTY.token_amount"
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              aria-invalid={!amountValidation.valid}
              className={cn(!amountValidation.valid && amount.trim() !== "" && "border-destructive/60")}
              required
            />
            {!amountValidation.valid && amount.trim() !== "" ? (
              <p
                role="alert"
                className="rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-1.5 text-[11px] leading-snug text-destructive"
              >
                {amountValidation.error}
              </p>
            ) : (
              <p className="text-[11px] leading-snug text-muted-foreground">
                {INVEST_TOKEN_AMOUNT_HINT}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/30 p-3 text-xs">
            <InvestFact
              label="Estimated cost"
              value={
                amountValidation.valid ? `${formatInvestEthFromWei(costWei)} ETH` : "—"
              }
            />
            <InvestFact
              label="Wallet"
              value={
                walletBalances.isLoading
                  ? walletLabel
                  : walletBalanceWei !== null
                    ? `${walletLabel} · ${formatInvestEthFromWei(walletBalanceWei)} ETH`
                    : walletLabel
              }
            />
            <InvestFact
              label="Token price"
              value={`${formatInvestEthAmount(property.token_sale_price_eth ?? 0)} ETH`}
            />
            <InvestFact label="Available" value={formatNumber(property.tokens_available ?? 0)} />
          </div>
          {showPreSubmitOrderFeedback &&
          amountValidation.valid &&
          !orderCheck.ok &&
          orderCheck.error ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-2 text-[11px] leading-snug text-destructive"
            >
              {formatInvestDialogText(orderCheck.error)}
            </p>
          ) : null}
          {showPreSubmitOrderFeedback &&
          amountValidation.valid &&
          orderCheck.reason === "balance_pending" &&
          !orderCheck.error ? (
            <p className="text-[11px] leading-snug text-muted-foreground">
              Checking wallet balance…
            </p>
          ) : null}
          <div className="space-y-2 text-xs text-muted-foreground">
            <InvestStep
              active={step === "prepare"}
              done={["wallet", "confirm"].includes(step)}
              icon={ShieldCheck}
              label="Preparing backend quote"
            />
            <InvestStep
              active={step === "wallet"}
              done={step === "confirm"}
              icon={Wallet}
              label="Confirming transaction in MetaMask"
            />
            <InvestStep active={step === "confirm"} done={false} icon={CheckCircle2} label="Indexing investment on backend" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitDisabled}>
              {busy || isInvestDialogTransactionInFlight(step, false)
                ? "Processing…"
                : "Invest via MetaMask"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function InvestFact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

function InvestStep({
  active,
  done,
  icon: Icon,
  label,
}: {
  active: boolean;
  done: boolean;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-border px-2.5 py-2",
        active && "border-primary/40 bg-primary/5 text-primary",
        done && "border-success/40 bg-success/5 text-success",
      )}
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </div>
  );
}
