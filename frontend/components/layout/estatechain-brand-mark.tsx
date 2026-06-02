import { cn } from "@/lib/utils";

/** EstateChain "E" logo — shared across admin, investor, and tenant sidebars. */
export function EstateChainBrandMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-primary via-chart-3 to-chart-2 text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20",
        className,
      )}
      aria-hidden
    >
      E
    </div>
  );
}
