import type { Property } from "@/lib/types";
import {
  checkManualInvestFunding,
  type ManualInvestFundingCheck,
} from "@/components/investor/investor-funding-utils";
import { availablePropertyTokens } from "@/components/investor/investor-utils";

export type ManualInvestOrderFailureReason =
  | "insufficient_tokens"
  | "insufficient_funds"
  | "balance_pending";

export type ManualInvestOrderCheck = {
  ok: boolean;
  error?: string;
  reason?: ManualInvestOrderFailureReason;
  availableTokens: number;
  funding?: ManualInvestFundingCheck;
};

export function availableTokensForInvest(property: Property): number {
  const count = availablePropertyTokens(property);
  if (!Number.isFinite(count) || count < 0) return 0;
  return Math.trunc(count);
}

export function buildInsufficientAvailableTokensMessage(params: {
  tokenAmount: number;
  availableTokens: number;
  propertyName: string;
}): string {
  const { tokenAmount, availableTokens, propertyName } = params;
  const label = propertyName.trim() || "this property";
  const requestedLabel = tokenAmount === 1 ? "token" : "tokens";
  const availableLabel = availableTokens === 1 ? "token is" : "tokens are";
  const availableShown = availableTokens.toLocaleString("en-US");
  return (
    `Insufficient tokens available to buy. You entered ${tokenAmount.toLocaleString("en-US")} ` +
    `${requestedLabel} for ${label}, but only ${availableShown} ${availableLabel} available. ` +
    `Enter ${availableShown} or fewer to continue.`
  );
}

export function checkManualInvestTokenAvailability(params: {
  tokenAmount: number;
  availableTokens: number;
  propertyName: string;
}): ManualInvestOrderCheck {
  const availableTokens = Math.max(0, Math.trunc(params.availableTokens));
  const tokenAmount = Math.max(0, Math.trunc(params.tokenAmount));

  if (tokenAmount <= 0 || tokenAmount <= availableTokens) {
    return { ok: true, availableTokens };
  }

  return {
    ok: false,
    availableTokens,
    reason: "insufficient_tokens",
    error: buildInsufficientAvailableTokensMessage({
      tokenAmount,
      availableTokens,
      propertyName: params.propertyName,
    }),
  };
}

/** Pre-submit order validation: token supply first, then wallet ETH balance. */
export function checkManualInvestOrder(params: {
  property: Property;
  tokenAmount: number;
  costWei: bigint;
  balanceWei: bigint | null | undefined;
}): ManualInvestOrderCheck {
  const availableTokens = availableTokensForInvest(params.property);
  const supplyCheck = checkManualInvestTokenAvailability({
    tokenAmount: params.tokenAmount,
    availableTokens,
    propertyName: params.property.name,
  });
  if (!supplyCheck.ok) {
    return supplyCheck;
  }

  const funding = checkManualInvestFunding({
    costWei: params.costWei,
    balanceWei: params.balanceWei,
    tokenAmount: params.tokenAmount,
    propertyName: params.property.name,
  });

  if (funding.balancePending) {
    return {
      ok: false,
      availableTokens,
      reason: "balance_pending",
      funding,
    };
  }

  if (!funding.ok) {
    return {
      ok: false,
      availableTokens,
      reason: "insufficient_funds",
      error: funding.error,
      funding,
    };
  }

  return { ok: true, availableTokens, funding };
}
