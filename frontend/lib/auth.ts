"use client";

import { BrowserProvider } from "ethers";
import { api, ApiError, clearSession, getSession, writeSession, type SessionRecord } from "./api";
import { expectedChainHex } from "./runtime-config";

declare global {
  interface Window {
    ethereum?: any;
  }
}

export type SignInResult =
  | { status: "authenticated"; session: SessionRecord }
  | { status: "needs_registration"; walletAddress: string };

export const VALID_ROLES = ["property_owner", "investor", "tenant"] as const;
export type Role = (typeof VALID_ROLES)[number];

/** Merge `/auth/me` onto the cached session user without dropping profile fields. */
export function mergeSessionUser(
  base: SessionRecord["user"],
  patch: Partial<SessionRecord["user"]>,
): SessionRecord["user"] {
  const patchName = patch.full_name != null ? String(patch.full_name).trim() : "";
  const baseName = base.full_name != null ? String(base.full_name).trim() : "";
  const fullName = patchName || baseName || null;
  const id = patch.id ?? base.id;
  return {
    ...base,
    ...patch,
    id,
    wallet_address: patch.wallet_address ?? base.wallet_address,
    role: patch.role ?? base.role,
    full_name: fullName,
    display_id: patch.display_id ?? base.display_id,
    profile_role: patch.profile_role ?? base.profile_role,
    email: patch.email ?? base.email,
    kyc_status: patch.kyc_status ?? base.kyc_status,
    active: patch.active ?? base.active,
  };
}

const DISPLAY_NAME_API_UNAVAILABLE =
  "The API server does not support saving display names yet. Deploy the latest backend to Render, then try again.";

/** Persist display name for legacy accounts missing `full_name` in the database. */
export async function updateMyDisplayName(fullName: string): Promise<SessionRecord["user"] | null> {
  const session = getSession();
  if (!session) return null;
  const trimmed = fullName.trim();
  if (!trimmed) throw new Error("Name is required.");

  const body = { full_name: trimmed };
  let updated: SessionRecord["user"];
  try {
    updated = await api.post<SessionRecord["user"]>("/auth/me/name", body);
  } catch (postErr) {
    if (postErr instanceof ApiError && (postErr.status === 404 || postErr.status === 405)) {
      try {
        updated = await api.patch<SessionRecord["user"]>("/auth/me", body);
      } catch (patchErr) {
        if (patchErr instanceof ApiError && (patchErr.status === 404 || patchErr.status === 405)) {
          throw new Error(DISPLAY_NAME_API_UNAVAILABLE);
        }
        throw patchErr;
      }
    } else {
      throw postErr;
    }
  }

  const merged = mergeSessionUser(session.user, updated);
  writeSession({ ...session, user: merged });
  return merged;
}

function ensureMetaMask() {
  if (typeof window === "undefined" || !window.ethereum) {
    throw new Error("MetaMask is not installed. Install it from https://metamask.io.");
  }
}

async function requestAccount(): Promise<string> {
  ensureMetaMask();
  const accounts = (await window.ethereum.request({ method: "eth_requestAccounts" })) as string[];
  if (!accounts || !accounts.length) throw new Error("No wallet account authorized.");
  return accounts[0];
}

export async function getConnectedWallet(): Promise<string | null> {
  ensureMetaMask();
  const accounts = (await window.ethereum.request({ method: "eth_accounts" })) as string[];
  return accounts?.[0] ? accounts[0].toLowerCase() : null;
}

export async function lookupWalletRegistration(walletAddress: string): Promise<{
  wallet_address: string;
  registered: boolean;
  role?: string | null;
}> {
  return api.get(`/auth/lookup/${walletAddress.toLowerCase()}`, { authOptional: true });
}

async function personalSign(address: string, message: string): Promise<string> {
  ensureMetaMask();
  return window.ethereum.request({
    method: "personal_sign",
    params: [message, address],
  }) as Promise<string>;
}

export async function ensureSepoliaNetwork() {
  ensureMetaMask();
  const expected = expectedChainHex();
  const current = (await window.ethereum.request({ method: "eth_chainId" })) as string;
  if (current?.toLowerCase() === expected.toLowerCase()) return;
  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: expected }],
    });
  } catch (err: any) {
    if (err?.code === 4902) {
      await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: expected,
            chainName: "Sepolia Testnet",
            rpcUrls: ["https://rpc.sepolia.org"],
            nativeCurrency: { name: "Sepolia ETH", symbol: "ETH", decimals: 18 },
            blockExplorerUrls: ["https://sepolia.etherscan.io"],
          },
        ],
      });
    } else {
      throw err;
    }
  }
}

export async function signIn(params?: { walletAddress?: string | null }): Promise<SignInResult> {
  const wallet = params?.walletAddress || await requestAccount();
  await ensureSepoliaNetwork();

  const lookup = await lookupWalletRegistration(wallet);
  if (!lookup.registered) {
    return { status: "needs_registration", walletAddress: wallet.toLowerCase() };
  }

  const challenge = await api.post<{ nonce: string; message: string; expires_at: string }>(
    "/auth/nonce",
    { wallet_address: wallet },
  );

  const signature = await personalSign(wallet, challenge.message);
  const verify = await api.post<{
    token: string;
    expires_at: string;
    user: SessionRecord["user"] & { registered?: boolean };
    is_new_user: boolean;
  }>("/auth/verify", { wallet_address: wallet, signature, nonce: challenge.nonce });

  if (verify.is_new_user) {
    return { status: "needs_registration", walletAddress: wallet.toLowerCase() };
  }

  const session: SessionRecord = {
    token: verify.token,
    user: verify.user,
    expires_at: verify.expires_at,
  };
  writeSession(session);
  await refreshMe();
  return { status: "authenticated", session: getSession() ?? session };
}

export async function registerWallet(params: {
  walletAddress?: string | null;
  role: Role;
  email?: string | null;
  fullName?: string | null;
}): Promise<SessionRecord> {
  const walletAddress = params.walletAddress || await requestAccount();
  await ensureSepoliaNetwork();
  const lookup = await lookupWalletRegistration(walletAddress);
  if (lookup.registered) {
    throw new Error("This wallet already has an account. Please login.");
  }

  const challenge = await api.post<{ nonce: string; message: string; expires_at: string }>(
    "/auth/nonce",
    { wallet_address: walletAddress },
  );
  const signature = await personalSign(walletAddress, challenge.message);
  const resp = await api.post<{ token: string; expires_at: string; user: SessionRecord["user"] }>(
    "/auth/register",
    {
      wallet_address: walletAddress,
      signature,
      nonce: challenge.nonce,
      role: params.role,
      email: params.email || null,
      full_name: params.fullName?.trim() || null,
    },
  );
  const session: SessionRecord = { token: resp.token, expires_at: resp.expires_at, user: resp.user };
  writeSession(session);
  await refreshMe();
  return getSession() ?? session;
}

export async function refreshMe(): Promise<SessionRecord["user"] | null> {
  const session = getSession();
  if (!session) return null;
  try {
    const me = await api.get<SessionRecord["user"]>("/auth/me");
    const merged = mergeSessionUser(session.user, me);
    writeSession({ ...session, user: merged });
    return merged;
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      clearSession();
    }
    return null;
  }
}

export async function logout({ silent = false }: { silent?: boolean } = {}) {
  try {
    await api.post("/auth/logout");
  } catch {
    /* ignore */
  }
  clearSession();
  if (!silent && typeof window !== "undefined") {
    window.location.href = "/";
  }
}

export async function getEthBalance(address: string): Promise<number> {
  ensureMetaMask();
  try {
    const provider = new BrowserProvider(window.ethereum);
    const balance = await provider.getBalance(address);
    return Number(balance) / 1e18;
  } catch {
    return 0;
  }
}
