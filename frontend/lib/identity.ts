"use client";

import { BrowserProvider } from "ethers";
import { getSession, type SessionRecord } from "@/lib/api";
import { shortAddress } from "@/lib/utils";

export type IdentityLike = {
  wallet_address?: string | null;
  full_name?: string | null;
  display_id?: string | null;
  profile_role?: string | null;
  email?: string | null;
  user_id?: number | null;
};

const ENS_CACHE_KEY = "estatechain.identity.ens.v1";

function clean(value?: string | null): string {
  return String(value ?? "").trim();
}

function readEnsCache(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(ENS_CACHE_KEY) || "{}");
  } catch {
    return {};
  }
}

function writeEnsCache(cache: Record<string, string>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ENS_CACHE_KEY, JSON.stringify(cache));
}

export function roleLabel(role?: string | null): string {
  if (role === "property_owner") return "Admin";
  if (role === "investor") return "Investor";
  if (role === "tenant") return "Tenant";
  return "User";
}

export function identityDisplayName(identity?: IdentityLike | null, fallbackWallet?: string | null): string {
  const wallet = clean(identity?.wallet_address ?? fallbackWallet);
  const cachedEns = wallet ? readEnsCache()[wallet.toLowerCase()] : "";
  return (
    clean(cachedEns) ||
    clean(identity?.full_name) ||
    clean(identity?.display_id) ||
    (identity?.user_id ? `Member #${identity.user_id}` : "") ||
    (wallet ? shortAddress(wallet, 6, 4) : "MetaMask account")
  );
}

export function identityDisplayId(identity?: IdentityLike | null): string {
  return clean(identity?.display_id) || roleLabel(identity?.profile_role);
}

export function identityInitials(identity?: IdentityLike | null, fallbackWallet?: string | null): string {
  const label = identityDisplayName(identity, fallbackWallet);
  const parts = label.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return label.slice(0, 2).toUpperCase();
}

export function currentSessionIdentity(): SessionRecord["user"] | null {
  return getSession()?.user ?? null;
}

export async function cacheEnsName(walletAddress?: string | null): Promise<string | null> {
  const wallet = clean(walletAddress);
  if (!wallet || typeof window === "undefined" || !window.ethereum) return null;
  const key = wallet.toLowerCase();
  const cache = readEnsCache();
  if (cache[key]) return cache[key];
  try {
    const provider = new BrowserProvider(window.ethereum);
    const ens = await provider.lookupAddress(wallet);
    if (ens) {
      cache[key] = ens;
      writeEnsCache(cache);
      window.dispatchEvent(new CustomEvent("estatechain:identity-changed"));
      return ens;
    }
  } catch {
    /* ENS is optional and should never block dashboard rendering. */
  }
  return null;
}
