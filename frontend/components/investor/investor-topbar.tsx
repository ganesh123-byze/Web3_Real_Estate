"use client";

import { cn } from "@/lib/utils";
import { AdminTopbar } from "@/components/layout/topbar";
import { ThemeToggle } from "@/components/layout/theme-toggle";

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
          <ThemeToggle className="h-8 w-8 shrink-0 rounded-xl" />
        </div>
      }
    />
  );
}
