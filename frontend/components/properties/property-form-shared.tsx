"use client";

import { Label } from "@/components/ui/label";
import type { CreatePropertyPayload } from "@/lib/mutations";
import { cn, formatEth } from "@/lib/utils";

/** Per-token sale price in ETH from total property value (ETH) ÷ token supply. */
export function calculateTokenPriceEth(totalValueEth: string, tokenSupply: string): number {
  const total = Number(totalValueEth);
  const supply = Number(tokenSupply);
  if (!Number.isFinite(total) || !Number.isFinite(supply) || total <= 0 || supply <= 0) return 0;
  return total / supply;
}

export function formatTokenPriceEth(priceEth: number, digits = 6): string {
  if (priceEth <= 0) return "";
  return formatEth(priceEth, { digits });
}

/** Per-token sale price string for API payloads, debug logs, and SSE (empty when invalid). */
export function tokenSalePriceEthForPayload(
  totalValueEth: string | undefined,
  tokenSupply: string | undefined,
): string {
  return formatTokenPriceEth(
    calculateTokenPriceEth(String(totalValueEth ?? ""), String(tokenSupply ?? "")),
  );
}

export type CreatePropertyFormValues = {
  name: string;
  location: string;
  total_value: string;
  token_supply: string;
  token_symbol: string;
  monthly_rent_eth?: string;
  images?: string[];
};

/** Matches backend MAX_PROPERTY_IMAGE_CHARS (base64 + data-URL prefix slack). */
export const MAX_PROPERTY_IMAGE_ENCODED_CHARS = 2_800_000;

export function normalizeDecimalField(value: string | undefined): string {
  return String(value ?? "").trim().replace(/,/g, "");
}

function isPositiveDecimal(value: string): boolean {
  const n = Number(value);
  return Number.isFinite(n) && n > 0;
}

function isNonNegativeDecimal(value: string): boolean {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0;
}

export type CreatePropertyValidationResult =
  | { ok: true; values: CreatePropertyFormValues }
  | { ok: false; message: string };

/** Client-side checks so invalid payloads never hit POST /properties/stream. */
export function validateCreatePropertyFormValues(
  values: CreatePropertyFormValues,
): CreatePropertyValidationResult {
  const name = String(values.name ?? "").trim();
  const location = String(values.location ?? "").trim();
  const total_value = normalizeDecimalField(values.total_value);
  const token_supply = normalizeDecimalField(values.token_supply);
  const token_symbol = String(values.token_symbol ?? "").trim();
  const monthly_rent_eth = normalizeDecimalField(values.monthly_rent_eth);
  const images = values.images ?? [];

  if (!name) return { ok: false, message: "Property name is required." };
  if (!location) return { ok: false, message: "Location is required." };
  if (!isPositiveDecimal(total_value)) {
    return { ok: false, message: "Total value must be a positive number." };
  }
  if (!isPositiveDecimal(token_supply)) {
    return { ok: false, message: "Token supply must be a positive whole number." };
  }
  if (!token_symbol) return { ok: false, message: "Token symbol is required." };
  if (token_symbol.length > 12) {
    return { ok: false, message: "Token symbol must be 12 characters or fewer." };
  }
  if (monthly_rent_eth && !isNonNegativeDecimal(monthly_rent_eth)) {
    return { ok: false, message: "Monthly rent must be a valid number." };
  }
  for (let i = 0; i < images.length; i += 1) {
    if (images[i].length > MAX_PROPERTY_IMAGE_ENCODED_CHARS) {
      return {
        ok: false,
        message: `Image ${i + 1} is too large. Use images under 1.5 MB each.`,
      };
    }
  }

  return {
    ok: true,
    values: {
      name,
      location,
      total_value,
      token_supply,
      token_symbol,
      ...(monthly_rent_eth ? { monthly_rent_eth } : {}),
      images,
    },
  };
}

/** JSON body for POST /properties and /properties/stream (no empty-string decimals). */
export function buildCreatePropertyApiPayload(
  values: CreatePropertyFormValues,
): CreatePropertyPayload {
  const validated = validateCreatePropertyFormValues(values);
  if (!validated.ok) {
    throw new Error(validated.message);
  }
  const normalized = validated.values;
  const total = normalized.total_value;
  const supply = normalized.token_supply;
  const rent = normalized.monthly_rent_eth ?? "";
  const sale = tokenSalePriceEthForPayload(total, supply);
  const payload: CreatePropertyPayload = {
    name: normalized.name,
    location: normalized.location,
    total_value: total,
    token_supply: supply,
    token_symbol: normalized.token_symbol,
    images: normalized.images ?? [],
  };
  if (sale) {
    payload.token_sale_price_eth = sale;
  }
  if (rent) {
    payload.monthly_rent_eth = rent;
  }
  return payload;
}

export const propertyDialogContentClass =
  "flex max-h-[calc(100vh-3rem)] w-[min(100vw-2rem,28rem)] max-w-[min(100vw-2rem,28rem)] flex-col gap-3 overflow-hidden p-0 sm:max-w-md";

/** Inner padded scroll container used inside each property dialog. */
export const propertyDialogBodyClass =
  "scrollbar-thin flex min-h-0 flex-col gap-4 overflow-y-auto px-6 pb-6 pt-5";

/** Scrollable main area for property detail overview modals (admin / tenant). */
export const propertyDetailScrollBodyClass =
  "scrollbar-thin min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth";

/** Investor detail modal shell — compact 580px shell shared with the property detail screenshots. */
export const investorPropertyDetailDialogClass =
  "flex h-fit w-[min(calc(100vw-1rem),580px)] max-w-[580px] flex-col gap-0 overflow-hidden p-0 max-h-[min(92vh,920px)] sm:rounded-2xl";

/** Investor detail scroll body (reserves ~48px for the pinned Invest footer). */
export const investorPropertyDetailScrollBodyClass =
  "scrollbar-thin overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth max-h-[calc(min(92vh,920px)-3rem)]";

/** Sticky footer styling used at the bottom of property dialogs. */
export const propertyDialogFooterClass =
  "sticky bottom-0 z-10 flex flex-col-reverse gap-2 border-t border-border/60 bg-card/95 px-6 py-3 backdrop-blur sm:flex-row sm:justify-end";

export const propertyFormClass = "grid min-w-0 gap-3";

export const propertyFormGridClass = "grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2";

export function PropertyFormField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid min-w-0 gap-1.5", className)}>
      <Label className="text-xs">{label}</Label>
      <div className="min-w-0 [&_input]:min-w-0 [&_input]:w-full [&_input]:max-w-full">{children}</div>
    </div>
  );
}
