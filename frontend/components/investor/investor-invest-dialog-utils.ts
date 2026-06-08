import type { ManualInvestOrderCheck } from "@/components/investor/investor-invest-order-utils";

export type InvestDialogStep = "idle" | "prepare" | "wallet" | "confirm";

/** True while the dialog is driving prepare → MetaMask → backend confirm. */
export function isInvestDialogTransactionInFlight(
  step: InvestDialogStep,
  busy = false,
): boolean {
  return busy || step !== "idle";
}

/**
 * Pre-submit order feedback (insufficient funds, supply, balance loading) applies
 * only on the idle form. After payment the wallet balance drops, so re-running
 * those checks mid-flow would show a false insufficient-funds warning.
 */
export function shouldShowInvestPreSubmitOrderFeedback(
  step: InvestDialogStep,
  busy = false,
): boolean {
  return !isInvestDialogTransactionInFlight(step, busy);
}

export function resolveInvestOrderBalanceWei(params: {
  step: InvestDialogStep;
  busy: boolean;
  liveBalanceWei: bigint | null;
  lockedBalanceWei: bigint | null;
}): bigint | null | undefined {
  if (
    isInvestDialogTransactionInFlight(params.step, params.busy) &&
    params.lockedBalanceWei !== null
  ) {
    return params.lockedBalanceWei;
  }
  return params.liveBalanceWei;
}

export function isInvestSubmitDisabled(params: {
  busy: boolean;
  step: InvestDialogStep;
  amountValid: boolean;
  wallet: string | null;
  orderCheck: ManualInvestOrderCheck;
  balanceLoading: boolean;
}): boolean {
  if (params.busy || isInvestDialogTransactionInFlight(params.step, false)) {
    return true;
  }
  if (!params.amountValid || !params.wallet) {
    return true;
  }
  if (params.balanceLoading || !params.orderCheck.ok) {
    return true;
  }
  return false;
}
