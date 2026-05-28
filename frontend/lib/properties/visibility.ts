import type { Property } from "@/lib/types";

const hiddenDuringCreation = new Set<number>();

function toPropertyId(id?: number | string | null): number | null {
  const value = Number(id);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function toNumber(value?: number | string | null): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function markPropertyCreationPending(id?: number | string | null) {
  const propertyId = toPropertyId(id);
  if (propertyId) hiddenDuringCreation.add(propertyId);
}

export function markPropertyCreationComplete(id?: number | string | null) {
  const propertyId = toPropertyId(id);
  if (propertyId) hiddenDuringCreation.delete(propertyId);
}

export function isPropertyFullyCreated(
  property: Pick<Property, "id" | "token_address" | "token_supply" | "tokens_available" | "tokens_sold">,
): boolean {
  const hasTokenContract = Boolean(String(property.token_address ?? "").trim());
  const supply = toNumber(property.token_supply);
  const available = toNumber(property.tokens_available);
  const sold = toNumber(property.tokens_sold);
  const inventoryFinalized = supply > 0 && available + sold >= supply;

  return hasTokenContract && inventoryFinalized && !hiddenDuringCreation.has(property.id);
}

export function filterFullyCreatedProperties<
  T extends Pick<Property, "id" | "token_address" | "token_supply" | "tokens_available" | "tokens_sold">,
>(properties: T[]): T[] {
  return properties.filter(isPropertyFullyCreated);
}
