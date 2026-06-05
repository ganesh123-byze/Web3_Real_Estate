import type { WalletBalances } from "@/lib/types";

export type ManualInvestFundingCheck = {
  ok: boolean;
  requiredWei: bigint;
  balanceWei: bigint;
  shortfallWei: bigint;
  error?: string;
  balancePending?: boolean;
};

/** Full-precision ETH display for funding messages (matches backend funding copy). */
export function formatEthFundingDisplay(wei: bigint): string {
  const value = Number(wei) / 1e18;
  if (!Number.isFinite(value) || value <= 0) return "0";
  return value.toFixed(18).replace(/\.?0+$/, "") || "0";
}

export function parseWalletNativeBalanceWei(
  balances: WalletBalances | null | undefined,
): bigint | null {
  const raw = balances?.native?.balance_wei;
  if (raw === undefined || raw === null || raw === "") return null;
  try {
    const value = BigInt(raw);
    return value >= 0n ? value : 0n;
  } catch {
    return null;
  }
}

export function buildManualInvestInsufficientFundsMessage(params: {
  tokenAmount: number;
  propertyName: string;
  requiredWei: bigint;
  balanceWei: bigint;
  shortfallWei: bigint;
}): string {
  const { tokenAmount, propertyName, requiredWei, balanceWei, shortfallWei } = params;
  const requiredEth = formatEthFundingDisplay(requiredWei);
  const balanceEth = formatEthFundingDisplay(balanceWei);
  const shortfallEth = formatEthFundingDisplay(shortfallWei);
  const label = propertyName.trim() || "this property";
  const tokenLabel = tokenAmount === 1 ? "token" : "tokens";
  return (
    `You have insufficient funds to buy. Purchasing ${tokenAmount} ${tokenLabel} in ${label} ` +
    `requires ${requiredEth} ETH, but your wallet balance is ${balanceEth} ETH ` +
    `(you need about ${shortfallEth} ETH more). Add ETH to your wallet or reduce the token amount.`
  );
}

/** Compare estimated order cost to the connected wallet's native ETH balance. */
export function checkManualInvestFunding(params: {
  costWei: bigint;
  balanceWei: bigint | null | undefined;
  tokenAmount: number;
  propertyName: string;
}): ManualInvestFundingCheck {
  const requiredWei = params.costWei > 0n ? params.costWei : 0n;
  if (params.balanceWei === null || params.balanceWei === undefined) {
    return {
      ok: false,
      requiredWei,
      balanceWei: 0n,
      shortfallWei: requiredWei,
      balancePending: true,
    };
  }

  const balanceWei = params.balanceWei >= 0n ? params.balanceWei : 0n;
  if (requiredWei <= 0n || balanceWei >= requiredWei) {
    return {
      ok: true,
      requiredWei,
      balanceWei,
      shortfallWei: 0n,
    };
  }

  const shortfallWei = requiredWei - balanceWei;
  return {
    ok: false,
    requiredWei,
    balanceWei,
    shortfallWei,
    error: buildManualInvestInsufficientFundsMessage({
      tokenAmount: params.tokenAmount,
      propertyName: params.propertyName,
      requiredWei,
      balanceWei,
      shortfallWei,
    }),
  };
}
