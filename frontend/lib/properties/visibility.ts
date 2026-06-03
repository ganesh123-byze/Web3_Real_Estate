import type { Property } from "@/lib/types";

const hiddenDuringCreation = new Set<number>();
const hiddenDuringCreationNames = new Set<string>();

function toPropertyId(id?: number | string | null): number | null {
  const value = Number(id);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function toNumber(value?: number | string | null): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toPropertyName(name?: string | null): string | null {
  const value = String(name ?? "").trim().toLowerCase();
  return value || null;
}

export function markPropertyCreationPending(id?: number | string | null, name?: string | null) {
  const propertyId = toPropertyId(id);
  if (propertyId) hiddenDuringCreation.add(propertyId);
  const propertyName = toPropertyName(name);
  if (propertyName) hiddenDuringCreationNames.add(propertyName);
}

export function markPropertyCreationComplete(id?: number | string | null, name?: string | null) {
  const propertyId = toPropertyId(id);
  if (propertyId) hiddenDuringCreation.delete(propertyId);
  const propertyName = toPropertyName(name);
  if (propertyName) hiddenDuringCreationNames.delete(propertyName);
}

export function isPropertyFullyCreated(
  property: Pick<Property, "id" | "name" | "token_address" | "token_supply" | "tokens_available" | "tokens_sold">,
): boolean {
  const hasTokenContract = Boolean(String(property.token_address ?? "").trim());
  const supply = toNumber(property.token_supply);
  const available = toNumber(property.tokens_available);
  const sold = toNumber(property.tokens_sold);
  const inventoryFinalized = supply > 0 && available + sold >= supply;
  const hiddenByName = hiddenDuringCreationNames.has(toPropertyName(property.name) ?? "");

  return hasTokenContract && inventoryFinalized && !hiddenDuringCreation.has(property.id) && !hiddenByName;
}

export function filterFullyCreatedProperties<
  T extends Pick<Property, "id" | "name" | "token_address" | "token_supply" | "tokens_available" | "tokens_sold">,
>(properties: T[]): T[] {
  return properties.filter(isPropertyFullyCreated);
}

/** True when the signed-in admin may manage this property (matches backend ``can_manage``). */
export function isPropertyManagedByOwner(
  property: Pick<Property, "can_manage" | "owner_wallet">,
  ownerWallet?: string | null,
): boolean {
  if (property.can_manage === true) return true;
  const owner = String(property.owner_wallet ?? "").trim().toLowerCase();
  const viewer = String(ownerWallet ?? "").trim().toLowerCase();
  return Boolean(owner && viewer && owner === viewer);
}

/** Properties created by the signed-in admin — for operational pages (rent, dashboard, etc.). */
export function filterManagedProperties<
  T extends Pick<Property, "can_manage" | "owner_wallet">,
>(properties: T[], ownerWallet?: string | null): T[] {
  if (!ownerWallet) {
    return properties.filter((property) => property.can_manage === true);
  }
  return properties.filter((property) => isPropertyManagedByOwner(property, ownerWallet));
}
