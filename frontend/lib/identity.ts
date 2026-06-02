"use client";

import { BrowserProvider } from "ethers";
import { getSession, type SessionRecord } from "@/lib/api";
import { shortAddress } from "@/lib/utils";

export type IdentityLike = {
  wallet_address?: string | null;
  full_name?: string | null;
  display_id?: string | null;
  profile_role?: string | null;
  /** Canonical role from session / API (`property_owner`, `investor`, `tenant`). */
  role?: string | null;
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
  const key = clean(role).toLowerCase();
  if (key === "property_owner" || key === "admin") return "Admin";
  if (key === "investor") return "Investor";
  if (key === "tenant") return "Tenant";
  return "User";
}

function resolveRoleKey(identity?: IdentityLike | null): string {
  return clean(identity?.profile_role) || clean(identity?.role);
}

/** Role line for account menus — never falls back to generic “User” when role is known. */
export function accountRoleLabel(identity?: IdentityLike | null): string {
  return roleLabel(resolveRoleKey(identity));
}

function readStoredFullName(identity?: IdentityLike | null): string {
  return clean(identity?.full_name);
}

function sessionNumericId(identity?: IdentityLike | null): number | null {
  if (identity?.user_id && identity.user_id > 0) return identity.user_id;
  const raw = (identity as { id?: number | null } | null | undefined)?.id;
  return typeof raw === "number" && raw > 0 ? raw : null;
}

/** Map API session user fields onto {@link IdentityLike} for account UI. */
export function identityFromSessionUser(
  user?: SessionRecord["user"] | IdentityLike | null,
): IdentityLike | null {
  if (!user) return null;
  const numericId = sessionNumericId(user);
  return {
    wallet_address: user.wallet_address,
    full_name: user.full_name,
    display_id: user.display_id,
    profile_role: user.profile_role,
    role: user.role,
    email: user.email,
    user_id: numericId ?? undefined,
  };
}

/**
 * Primary label for dashboard account cards (sidebar / header).
 * Uses stored full name only — never role or email guesses (avoids "Investor" twice).
 */
export function accountPrimaryLabel(identity?: IdentityLike | null): string {
  const name = readStoredFullName(identity);
  if (name) return name;

  const memberId = clean(identity?.display_id);
  if (memberId) return memberId;

  const numericId = sessionNumericId(identity);
  if (numericId) return `Member #${numericId}`;
  return "My account";
}

/** Wallet address for expanded account panels (truncated for display). */
export function accountWalletLine(identity?: IdentityLike | null): string {
  const wallet = clean(identity?.wallet_address);
  if (!wallet) return "";
  return shortAddress(wallet, 6, 4);
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
  return clean(identity?.display_id) || roleLabel(resolveRoleKey(identity));
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
