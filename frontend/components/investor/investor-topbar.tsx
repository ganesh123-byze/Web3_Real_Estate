"use client";

import { cn } from "@/lib/utils";
import { AmbientSystemPulse } from "@/components/ai/ambient-system-pulse";
import { AdminTopbar } from "@/components/layout/topbar";
import { StatusDot } from "@/components/layout/status-dot";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { WalletPill } from "@/components/layout/wallet-pill";

/** Shared height for all header controls on investor routes. */
export const INVESTOR_TOPBAR_CONTROL_CLASS = "h-9 shrink-0";

export function InvestorTopbar({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <AdminTopbar
      title={title}
      subtitle={subtitle}
      className={cn(
        "border-[#e8ecf4]/90 bg-[#F4F5FB]/95 backdrop-blur-md",
        "dark:border-border/60 dark:bg-background/75",
      )}
      actions={
        <div className="flex min-w-0 items-center justify-end gap-2 overflow-hidden">
          <AmbientSystemPulse
            className="hidden h-8 max-w-[170px] shrink truncate px-2.5 text-xs md:flex"
          />
          <WalletPill className="h-8 shrink-0" />
          <ThemeToggle className="h-8 w-14 shrink-0" />
          <span className="grid h-8 w-5 shrink-0 place-items-center">
            <StatusDot />
          </span>
        </div>
      }
    />
  );
}
