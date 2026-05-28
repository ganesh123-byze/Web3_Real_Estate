"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = mounted ? resolvedTheme === "dark" : true;

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "relative inline-flex h-8 w-14 items-center rounded-full border transition-colors",
        isDark
          ? "border-primary/25 bg-primary/15 hover:bg-primary/20"
          : "border-border bg-white hover:bg-white",
        className,
      )}
    >
      <Sun className={cn("absolute left-1.5 h-3.5 w-3.5", isDark ? "text-muted-foreground/60" : "text-warning")} />
      <Moon className={cn("absolute right-1.5 h-3.5 w-3.5", isDark ? "text-primary" : "text-muted-foreground/60")} />
      <span
        className={cn(
          "z-10 inline-block h-6 w-6 rounded-full bg-background shadow-md ring-1 ring-border transition-transform duration-200",
          isDark ? "translate-x-[30px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}
