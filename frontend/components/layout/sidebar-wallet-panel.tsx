"use client";

import { useEffect, useState } from "react";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { Button } from "@/components/ui/button";
import { getSession, type SessionRecord } from "@/lib/api";
import { logout } from "@/lib/auth";

export function SidebarWalletPanel() {
  const [session, setSession] = useState<SessionRecord | null>(null);

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

  const accountLabel =
    (session?.user as (SessionRecord["user"] & { name?: string | null; full_name?: string | null }) | undefined)
      ?.name?.trim() ||
    (session?.user as (SessionRecord["user"] & { name?: string | null; full_name?: string | null }) | undefined)
      ?.full_name?.trim() ||
    session?.user?.email?.trim() ||
    "MetaMask account";

  return (
    <div className="mt-auto rounded-2xl border border-border/70 bg-background/70 p-3 shadow-sm">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        <MetaMaskIcon size={15} />
        MetaMask
      </div>
      {session ? (
        <>
          <div className="mt-2 truncate text-xs font-medium text-foreground" title={accountLabel}>
            {accountLabel}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3 w-full justify-center rounded-xl"
            onClick={() => logout()}
          >
            Logout with MetaMask
          </Button>
        </>
      ) : (
        <Button asChild size="sm" className="mt-3 w-full justify-center rounded-xl">
          <a href="/">Login with MetaMask</a>
        </Button>
      )}
    </div>
  );
}
