"use client";

import { useId } from "react";
import { LayoutGrid, Table2 } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export type ViewMode = "cards" | "table";

const VIEW_OPTIONS: Array<{ value: ViewMode; label: string; icon: typeof LayoutGrid }> = [
  { value: "cards", label: "Card", icon: LayoutGrid },
  { value: "table", label: "Table", icon: Table2 },
];

export function ViewModeToggle({
  value,
  onChange,
  ariaLabel,
  className,
}: {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
  ariaLabel: string;
  className?: string;
}) {
  const id = useId();

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex w-full rounded-xl border border-border bg-muted/40 p-1 shadow-sm sm:w-auto",
        className,
      )}
    >
      {VIEW_OPTIONS.map(({ value: optionValue, label, icon: Icon }) => {
        const active = value === optionValue;

        return (
          <button
            key={optionValue}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(optionValue)}
            className={cn(
              "relative flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-colors sm:flex-none",
              active ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {active ? (
              <motion.span
                layoutId={`${id}-active-view-mode`}
                className="absolute inset-0 rounded-lg bg-primary"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : null}
            <motion.span
              className="relative z-10 inline-flex items-center gap-1.5"
              animate={active ? { scale: 1.04, y: -1 } : { scale: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 22 }}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{label}</span>
            </motion.span>
          </button>
        );
      })}
    </div>
  );
}
