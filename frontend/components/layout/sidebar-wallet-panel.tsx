"use client";

import { useEffect, useState } from "react";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { Button } from "@/components/ui/button";
import { getSession, type SessionRecord } from "@/lib/api";
import { logout } from "@/lib/auth";
import { shortAddress } from "@/lib/utils";

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

  const wallet = session?.user?.wallet_address ?? "";

  return (
    <div className="mt-auto rounded-2xl border border-border/70 bg-background/70 p-3 shadow-sm">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        <MetaMaskIcon size={15} />
        MetaMask
      </div>
      {wallet ? (
        <>
          <div className="mt-2 font-mono text-xs text-foreground" title={wallet}>
            {shortAddress(wallet, 8, 6)}
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
