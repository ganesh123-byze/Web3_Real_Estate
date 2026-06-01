"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export const MOBILE_SIDEBAR_EVENT = "estatechain:mobile-sidebar-open";

export function openMobileSidebar() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(MOBILE_SIDEBAR_EVENT));
}

export function MobileSidebarDrawer({ children }: { children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const openDrawer = () => setOpen(true);
    window.addEventListener(MOBILE_SIDEBAR_EVENT, openDrawer);
    return () => window.removeEventListener(MOBILE_SIDEBAR_EVENT, openDrawer);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;

  const close = () => setOpen(false);

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        type="button"
        className="absolute inset-0 bg-background/70 backdrop-blur-sm"
        aria-label="Close navigation"
        onClick={close}
      />
      <div className="absolute inset-y-0 left-0 w-[min(82vw,18rem)] overflow-y-auto border-r border-border bg-background shadow-[10px_0_30px_-24px_hsl(var(--foreground)/0.55)]">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute right-2 top-2 z-10 rounded-full"
          aria-label="Close navigation"
          onClick={close}
        >
          <X className="h-4 w-4" />
        </Button>
        {children(close)}
      </div>
    </div>
  );
}
