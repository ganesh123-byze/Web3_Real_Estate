"use client";

import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { WalletPill } from "./wallet-pill";
import { StatusDot } from "./status-dot";
import { AmbientSystemPulse } from "@/components/ai/ambient-system-pulse";
import { cn } from "@/lib/utils";

export function AdminTopbar({
  title,
  subtitle,
  onMenuClick,
  className,
  actions,
}: {
  title: string;
  subtitle?: string;
  onMenuClick?: () => void;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-border/60 bg-card/85 px-4 shadow-[0_10px_40px_-28px_hsl(var(--foreground)/0.55)] backdrop-blur-2xl dark:bg-background/70 lg:px-6",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="rounded-2xl lg:hidden"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex flex-col leading-tight">
          <h1 className="text-base font-semibold tracking-tight md:text-lg">{title}</h1>
          {subtitle ? <span className="text-xs text-muted-foreground">{subtitle}</span> : null}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {actions ?? (
          <>
            <AmbientSystemPulse />
            <WalletPill />
            <ThemeToggle />
            <StatusDot />
          </>
        )}
      </div>
    </header>
  );
}
