"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { Button } from "@/components/ui/button";
import { logout } from "@/lib/auth";
import { AccountSetNameForm } from "@/components/layout/account-set-name-form";
import { AccountWalletCopy } from "@/components/layout/account-wallet-copy";
import {
  accountPrimaryLabel,
  accountRoleLabel,
  identityFromSessionUser,
} from "@/lib/identity";
import { useSessionAccount } from "@/lib/hooks/use-session-account";
import { cn } from "@/lib/utils";

export function SidebarWalletPanel() {
  const session = useSessionAccount();
  const [open, setOpen] = useState(false);
  const identity = identityFromSessionUser(session?.user);
  const primary = accountPrimaryLabel(identity);
  const role = accountRoleLabel(identity);

  return (
    <div className="mt-auto rounded-2xl border border-border/70 bg-background/70 p-2 shadow-none transition-shadow hover:shadow-sm">
      {session ? (
        <>
          <button
            type="button"
            className="flex w-full items-start gap-2 rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted/60"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-label={`Account menu for ${primary}`}
          >
            <MetaMaskIcon size={18} className="mt-0.5 shrink-0" />
            <span className="min-w-0 flex-1">
              <span
                className="block truncate text-sm font-semibold text-foreground"
                title={primary}
              >
                {primary}
              </span>
              <span className="mt-0.5 block truncate text-[11px] font-normal text-muted-foreground">
                {role}
              </span>
            </span>
            <ChevronDown
              className={cn(
                "mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                open && "rotate-180",
              )}
            />
          </button>
          {open ? (
            <div className="mt-2 space-y-2 border-t border-border/60 pt-2">
              {identity?.wallet_address ? <AccountWalletCopy user={identity} /> : null}
              {!identity?.full_name?.trim() ? <AccountSetNameForm /> : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full justify-center rounded-xl"
                onClick={() => logout()}
              >
                Logout with MetaMask
              </Button>
            </div>
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
