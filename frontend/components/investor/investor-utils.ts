import { parseEther } from "ethers";
import type { PortfolioItem, Property } from "@/lib/types";

export const TOKEN_DECIMALS = 18;
const TOKEN_DIVISOR = 10 ** TOKEN_DECIMALS;

export function tokenUnits(value: string | number | null | undefined): number {
  const raw = Number(value ?? 0);
  if (!Number.isFinite(raw)) return 0;
  return raw / TOKEN_DIVISOR;
}

export function humanTokenAmount(value: string | number | null | undefined, digits = 4): string {
  const units = tokenUnits(value);
  if (!Number.isFinite(units)) return "0";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(units);
}

export function propertyUnitValue(property?: Property | null): number {
  if (!property) return 0;
  const value = Number(property.total_value ?? 0);
  const supply = Number(property.token_supply ?? 0);
  if (!Number.isFinite(value) || !Number.isFinite(supply) || supply <= 0) return 0;
  return value / supply;
}

export function holdingValue(item: PortfolioItem, property?: Property | null): number {
  return tokenUnits(item.token_amount) * propertyUnitValue(property);
}

export function ownershipPercent(item: PortfolioItem, property?: Property | null): number {
  const supply = Number(property?.token_supply ?? 0);
  if (!supply) return 0;
  return (tokenUnits(item.token_amount) / supply) * 100;
}

export function buildInvestorMetrics(holdings: PortfolioItem[] = [], properties: Property[] = []) {
  const byId = new Map(properties.map((p) => [Number(p.id), p]));
  let totalTokens = 0;
  let estimatedValue = 0;
  for (const holding of holdings) {
    const property = byId.get(Number(holding.property_id));
    const units = tokenUnits(holding.token_amount);
    totalTokens += units;
    estimatedValue += holdingValue(holding, property);
  }
  return {
    totalTokens,
    estimatedValue,
    propertiesOwned: holdings.filter((h) => tokenUnits(h.token_amount) > 0).length,
    avgValuePerToken: totalTokens > 0 ? estimatedValue / totalTokens : 0,
  };
}

export function availablePropertyTokens(property: Property): number {
  return Number(property.tokens_available ?? 0);
}

export function propertyIsInvestable(property: Property): boolean {
  return Boolean(property.token_address) && availablePropertyTokens(property) > 0;
}

export function investmentCostWei(property: Property, tokenAmount: number): bigint {
  const priceWei = property.token_sale_price_wei || "0";
  return BigInt(priceWei) * BigInt(Math.max(0, Math.trunc(tokenAmount || 0)));
}

export function parseZeroEth() {
  return parseEther("0");
}

export const INVEST_TOKEN_AMOUNT_HINT =
  "Whole numbers only — enter 1 or greater.";

export const INVEST_TOKEN_AMOUNT_DECIMAL_ERROR =
  "Decimals aren't allowed. Please use whole numbers (1 or greater).";

export const INVEST_TOKEN_AMOUNT_MIN_ERROR =
  "Enter a whole number of 1 or greater.";

export type InvestTokenAmountValidation = {
  valid: boolean;
  error?: string;
  wholeAmount: number;
};

/** Whole tokens only — on-chain purchases do not support fractional counts. */
export function validateInvestTokenAmountInput(raw: string): InvestTokenAmountValidation {
  const text = raw.trim();
  if (!text) {
    return { valid: false, error: INVEST_TOKEN_AMOUNT_MIN_ERROR, wholeAmount: 0 };
  }
  if (/[.,eE+-]/.test(text) || !/^\d+$/.test(text)) {
    return {
      valid: false,
      error: INVEST_TOKEN_AMOUNT_DECIMAL_ERROR,
      wholeAmount: 0,
    };
  }
  const wholeAmount = Number(text);
  if (!Number.isSafeInteger(wholeAmount) || wholeAmount < 1) {
    return { valid: false, error: INVEST_TOKEN_AMOUNT_MIN_ERROR, wholeAmount: 0 };
  }
  return { valid: true, wholeAmount };
}
