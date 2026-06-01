import type { OwnerInvestor, Property, Transaction } from "@/lib/types";

export type PropertyOwnershipItem = {
  investor: string;
  share_pct: number;
  token_amount: string | number;
};

function toTokenUnits(value: string | number | null | undefined, supply: number): number {
  const raw = Number(value ?? 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return supply > 0 && raw > supply * 1_000 ? raw / 1e18 : raw;
}

function isCompletedInvestment(transaction: Transaction): boolean {
  const type = String(transaction.type ?? "").toLowerCase();
  const status = String(transaction.status ?? "").toLowerCase();
  const unit = String(transaction.amount_unit ?? "").toLowerCase();
  const investmentType = type.includes("investment") || type === "issue_tokens";
  const completed = !status || ["completed", "confirmed", "success"].includes(status);
  return investmentType && completed && (unit.includes("token") || unit === "");
}

export function ownerInvestorsWithTransactionFallback(
  ownerInvestors: OwnerInvestor[] | undefined,
  properties: Property[] | undefined,
  transactions: Transaction[] | undefined,
): OwnerInvestor[] {
  const byProperty = new Map((properties ?? []).map((property) => [String(property.id), property]));
  const byWallet = new Map<string, OwnerInvestor>();

  for (const investor of ownerInvestors ?? []) {
    byWallet.set(investor.wallet_address.toLowerCase(), {
      ...investor,
      positions: [...investor.positions],
    });
  }

  for (const transaction of transactions ?? []) {
    const propertyId = transaction.property_id;
    const wallet = transaction.wallet_address;
    if (propertyId == null || !wallet || !isCompletedInvestment(transaction)) continue;

    const property = byProperty.get(String(propertyId));
    const supply = Number(property?.token_supply ?? 0);
    const tokens = toTokenUnits(transaction.display_amount ?? transaction.amount, supply);
    if (tokens <= 0) continue;

    const walletKey = wallet.toLowerCase();
    const investor = byWallet.get(walletKey) ?? {
      wallet_address: wallet,
      user_id: null,
      email: null,
      kyc_status: "pending",
      positions: [],
      properties_count: 0,
      avg_ownership_pct: 0,
    };

    const existing = investor.positions.find((position) => String(position.property_id) === String(propertyId));
    const ownership = supply > 0 ? (tokens / supply) * 100 : 0;

    if (existing) {
      if (Number(existing.ownership_percentage ?? 0) <= 0 && ownership > 0) {
        existing.ownership_percentage = ownership;
      }
      continue;
    }

    investor.positions.push({
      property_id: Number(propertyId),
      property_name: transaction.property_name || property?.name || `Property #${propertyId}`,
      token_symbol: property?.token_symbol ?? null,
      token_amount: tokens,
      ownership_percentage: ownership,
    });
    byWallet.set(walletKey, investor);
  }

  return Array.from(byWallet.values())
    .map((investor) => {
      const positions = investor.positions.filter((position) => Number(position.token_amount ?? 0) > 0);
      const avg =
        positions.length > 0
          ? positions.reduce((sum, position) => sum + Number(position.ownership_percentage ?? 0), 0) / positions.length
          : 0;
      return {
        ...investor,
        positions,
        properties_count: positions.length,
        avg_ownership_pct: avg,
      };
    })
    .filter((investor) => investor.positions.length > 0)
    .sort((a, b) => b.avg_ownership_pct - a.avg_ownership_pct || a.wallet_address.localeCompare(b.wallet_address));
}

export function propertyOwnershipFor(
  ownerInvestors: OwnerInvestor[] | undefined,
  propertyOrId: Property | number | string | null | undefined,
  transactions: Transaction[] = [],
): PropertyOwnershipItem[] {
  const property = typeof propertyOrId === "object" && propertyOrId !== null ? propertyOrId : null;
  const propertyId = property?.id ?? propertyOrId;
  if (propertyId == null) return [];

  const supply = Number(property?.token_supply ?? 0);
  const rows = new Map<string, PropertyOwnershipItem>();

  for (const investor of ownerInvestors ?? []) {
    for (const position of investor.positions) {
      if (String(position.property_id) !== String(propertyId)) continue;
      const investorWallet = String(investor.wallet_address ?? "");
      const tokens = toTokenUnits(position.token_amount, supply);
      if (!investorWallet || tokens <= 0) continue;
      const rawShare = Number(position.ownership_percentage ?? 0);
      const share = rawShare > 0 ? rawShare : supply > 0 ? (tokens / supply) * 100 : 0;
      rows.set(investorWallet.toLowerCase(), {
        investor: investorWallet,
        share_pct: share,
        token_amount: tokens,
      });
    }
  }

  for (const transaction of transactions) {
    if (String(transaction.property_id ?? "") !== String(propertyId)) continue;
    if (!transaction.wallet_address || !isCompletedInvestment(transaction)) continue;
    const key = transaction.wallet_address.toLowerCase();
    if (rows.has(key)) continue;

    const tokens = toTokenUnits(transaction.display_amount ?? transaction.amount, supply);
    if (tokens <= 0) continue;
    rows.set(key, {
      investor: transaction.wallet_address,
      share_pct: supply > 0 ? (tokens / supply) * 100 : 0,
      token_amount: tokens,
    });
  }

  const result = Array.from(rows.values());
  const total = result.reduce((sum, item) => sum + item.share_pct, 0);
  const scale = total > 0 && total <= 1 ? 100 : 1;
  return result
    .map((item) => ({ ...item, share_pct: item.share_pct * scale }))
    .sort((a, b) => b.share_pct - a.share_pct || a.investor.localeCompare(b.investor));
}
