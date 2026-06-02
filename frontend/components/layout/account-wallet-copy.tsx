"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { accountWalletLine, type IdentityLike } from "@/lib/identity";

export function AccountWalletCopy({ user }: { user?: IdentityLike | null }) {
  const full = (user?.wallet_address || "").trim();
  const display = accountWalletLine(user);
  const [copied, setCopied] = useState(false);

  if (!full || !display) return null;

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(full);
      setCopied(true);
      toast.success("Wallet address copied");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy address");
    }
  }

  return (
    <div className="flex items-center gap-0.5 px-1">
      <button
        type="button"
        className="min-w-0 flex-1 truncate rounded-md px-1 py-1 text-left font-mono text-[11px] text-muted-foreground transition-colors hover:bg-muted/60"
        title={`${full} — click to copy`}
        onClick={() => void copyAddress()}
      >
        {display}
      </button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7 shrink-0"
        aria-label="Copy wallet address"
        onClick={() => void copyAddress()}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </div>
  );
}
