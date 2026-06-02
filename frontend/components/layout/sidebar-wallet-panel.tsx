"use client";

import { useEffect, useState } from "react";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { Button } from "@/components/ui/button";
import { getSession, type SessionRecord } from "@/lib/api";
import { logout } from "@/lib/auth";
import { cacheEnsName, identityDisplayName } from "@/lib/identity";

export function SidebarWalletPanel() {
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setSession(getSession());
    const handler = () => setSession(getSession());
    window.addEventListener("estatechain:session-changed", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("estatechain:session-changed", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  useEffect(() => {
    void cacheEnsName(session?.user?.wallet_address).then((ens) => {
      if (ens) setSession(getSession());
    });
  }, [session?.user?.wallet_address]);

  const accountLabel = identityDisplayName(session?.user);

  return (
    <div className="mt-auto rounded-2xl border border-border/70 bg-background/70 p-2 shadow-none transition-shadow hover:shadow-sm">
      {session ? (
        <>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted/60"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
          >
            <MetaMaskIcon size={18} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-foreground" title={accountLabel}>
                {accountLabel}
              </span>
            </span>
          </button>
          {open ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2 w-full justify-center rounded-xl"
              onClick={() => logout()}
            >
              Logout with MetaMask
            </Button>
          ) : null}
        </>
      ) : (
        <Button asChild size="sm" className="mt-3 w-full justify-center rounded-xl">
          <a href="/">Login with MetaMask</a>
        </Button>
      )}
    </div>
  );
}
