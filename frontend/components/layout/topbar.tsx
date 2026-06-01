"use client";

import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./theme-toggle";
import { openMobileSidebar } from "./mobile-sidebar-drawer";
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
        "sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border/60 bg-card/85 px-3 shadow-none backdrop-blur-2xl dark:bg-background/70 sm:px-4 lg:px-6",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="rounded-2xl lg:hidden"
          onClick={onMenuClick ?? openMobileSidebar}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <div className="min-w-0 flex flex-col leading-tight">
          <h1 className="truncate text-base font-semibold tracking-tight md:text-lg">{title}</h1>
          {subtitle ? <span className="truncate text-xs text-muted-foreground">{subtitle}</span> : null}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {actions ?? (
          <>
            <ThemeToggle />
          </>
        )}
      </div>
    </header>
  );
}
