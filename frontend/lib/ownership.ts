import type { OwnerInvestor } from "@/lib/types";

export type PropertyOwnershipItem = {
  investor: string;
  share_pct: number;
  token_amount: string | number;
};

export function propertyOwnershipFor(
  ownerInvestors: OwnerInvestor[] | undefined,
  propertyId: number | string | null | undefined,
): PropertyOwnershipItem[] {
  if (propertyId == null) return [];
  const rows = (ownerInvestors ?? [])
    .flatMap((investor) =>
      investor.positions
        .filter((position) => String(position.property_id) === String(propertyId))
        .map((position) => ({
          investor: investor.wallet_address,
          share_pct: Number(position.ownership_percentage ?? 0),
          token_amount: position.token_amount,
        })),
    )
    .filter((item) => item.investor && Number(item.token_amount ?? 0) > 0);

  const total = rows.reduce((sum, item) => sum + item.share_pct, 0);
  const scale = total > 0 && total <= 1 ? 100 : 1;
  return rows
    .map((item) => ({ ...item, share_pct: item.share_pct * scale }))
    .sort((a, b) => b.share_pct - a.share_pct || a.investor.localeCompare(b.investor));
}
