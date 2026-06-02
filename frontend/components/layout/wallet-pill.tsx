"use client";

import { ChevronDown, LogOut } from "lucide-react";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { logout } from "@/lib/auth";
import { AccountWalletCopy } from "@/components/layout/account-wallet-copy";
import { accountPrimaryLabel, accountRoleLabel, identityFromSessionUser } from "@/lib/identity";
import { useSessionAccount } from "@/lib/hooks/use-session-account";
import { cn } from "@/lib/utils";

export function WalletPill({ className }: { className?: string }) {
  const session = useSessionAccount();
  const identity = identityFromSessionUser(session?.user);
  const primary = accountPrimaryLabel(identity);
  const role = accountRoleLabel(identity);

  if (!session) {
    return (
      <Button asChild size="sm" variant="outline" className={cn("gap-2 px-3", className)}>
        <a href="/">
          <MetaMaskIcon size={16} />
          Login with MetaMask
        </a>
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex max-w-[11rem] items-center gap-2 rounded-full border border-transparent bg-transparent px-2.5 py-1.5 text-left text-xs font-medium text-foreground/90 transition-colors hover:bg-muted/60",
            className,
          )}
          aria-label={`Account menu for ${primary}`}
        >
          <MetaMaskIcon size={16} className="shrink-0" />
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate tracking-tight">{primary}</span>
            <span className="block truncate text-[10px] font-normal text-muted-foreground">
              {role}
            </span>
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="font-medium text-foreground">{primary}</div>
          <div className="text-[11px] font-normal text-muted-foreground">{role}</div>
        </DropdownMenuLabel>
        {identity?.wallet_address ? (
          <>
            <div className="px-1 pb-1">
              <AccountWalletCopy user={identity} />
            </div>
            <DropdownMenuSeparator />
          </>
        ) : null}
        <DropdownMenuItem onClick={() => logout()} className="text-destructive focus:text-destructive">
          <LogOut className="h-4 w-4" />
          Logout with MetaMask
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
