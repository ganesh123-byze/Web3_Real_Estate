"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  Coins,
  LayoutDashboard,
  Receipt,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

const NAV: NavItem[] = [
  { href: "/property_owner/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/property_owner/properties", label: "Properties", icon: Building2 },
  { href: "/property_owner/transactions", label: "Transactions", icon: Receipt },
  { href: "/property_owner/investors", label: "Investors", icon: Users },
  { href: "/property_owner/rent", label: "Rent Management", icon: Coins },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border/60 bg-[#F9FAFF] px-4 py-5 shadow-[16px_0_60px_-48px_hsl(var(--foreground)/0.6)] dark:bg-card/[0.35] lg:flex">
      <Link href="/property_owner/dashboard" className="mb-9 flex items-center gap-3 px-1">
        <div className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-primary via-chart-3 to-chart-2 font-bold text-primary-foreground shadow-lg shadow-primary/20">
          E
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">EstateChain</span>
          <span className="text-[11px] text-muted-foreground">Admin Panel</span>
        </div>
      </Link>

      <div className="mb-4 px-1 text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
        Menu
      </div>

      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative -mx-4 flex items-center gap-3 px-7 py-3 text-sm transition-all",
                active
                  ? "bg-gradient-to-r from-primary/[0.13] via-primary/[0.08] to-transparent text-primary shadow-none ring-0"
                  : "text-muted-foreground hover:bg-primary/[0.08] hover:text-primary",
              )}
            >
              {active ? <span className="absolute inset-y-0 left-0 w-1 bg-primary" /> : null}
              <Icon className="h-4 w-4" />
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
