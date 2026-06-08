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
        "ml-auto inline-flex w-fit shrink-0 rounded-full bg-muted/45 p-0.5",
        className,
      )}
    >
      {VIEW_OPTIONS.map(({ value: optionValue, label, icon: Icon }) => {
        const active = value === optionValue;

        return (
          <button
            key={optionValue}
            type="button"
            aria-label={`${label} view`}
            aria-pressed={active}
            title={`${label} view`}
            onClick={() => onChange(optionValue)}
            className={cn(
              "relative grid h-7 w-7 place-items-center rounded-full transition-colors",
              active ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {active ? (
              <motion.span
                layoutId={`${id}-active-view-mode`}
                className="absolute inset-0 rounded-full bg-primary"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : null}
            <motion.span
              className="relative z-10 inline-flex items-center"
              animate={active ? { scale: 1.04, y: -1 } : { scale: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 22 }}
            >
              <Icon className="h-3.5 w-3.5" />
            </motion.span>
          </button>
        );
      })}
    </div>
  );
}
