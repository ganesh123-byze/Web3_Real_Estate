"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, Mail, Search, Wallet } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty";
import { api } from "@/lib/api";
import { identityDisplayId, identityDisplayName, identityInitials } from "@/lib/identity";
import { formatNumber } from "@/lib/utils";
import { pickColor } from "@/lib/charts";
import type { OwnerInvestor } from "@/lib/types";

const PAGE_SIZE = 12;

export function InvestorsTable({
  investors,
  loading,
}: {
  investors: OwnerInvestor[];
  loading?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [active, setActive] = useState<OwnerInvestor | null>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return investors;
    const q = search.toLowerCase();
    return investors.filter(
      (it) =>
        it.wallet_address.toLowerCase().includes(q) ||
        identityDisplayName(it, it.wallet_address).toLowerCase().includes(q) ||
        identityDisplayId(it).toLowerCase().includes(q) ||
        it.email?.toLowerCase().includes(q) ||
        it.positions.some((p) => p.property_name.toLowerCase().includes(q)),
    );
  }, [investors, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  if (!loading && investors.length === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-border/60 bg-card/[0.78] p-4 shadow-none backdrop-blur-2xl">
        <EmptyState
          title="No investors yet"
          description="Investors appear here after they purchase tokens in your listed properties."
          className="min-h-[260px] border-0"
        />
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border/60 bg-card/[0.78] shadow-none backdrop-blur-2xl transition-shadow hover:shadow-sm">
      <div className="flex flex-col gap-3 border-b border-border/60 p-4 md:flex-row md:items-center md:justify-between">
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search by wallet, email, or property…"
            className="h-9 rounded-xl pl-8 text-sm"
          />
        </div>
        <span className="text-xs text-muted-foreground">
          {filtered.length} investor{filtered.length === 1 ? "" : "s"} with token holdings
        </span>
      </div>

      {!loading && visible.length === 0 ? (
        <div className="p-4">
          <EmptyState
            title="No investors"
            description="No investors match the current search."
            className="min-h-[240px] border-0"
          />
        </div>
      ) : (
        <>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[28%]">Investor</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>KYC</TableHead>
            <TableHead className="text-right">Properties</TableHead>
            <TableHead className="text-right">Avg ownership</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading && investors.length === 0 ? (
            Array.from({ length: 5 }).map((_, i) => (
              <TableRow key={i} className="hover:bg-transparent">
                <TableCell colSpan={6}>
                  <Skeleton className="h-9 w-full" />
                </TableCell>
              </TableRow>
            ))
          ) : (
            visible.map((it) => {
              const displayName = identityDisplayName(it, it.wallet_address);
              const displayId = identityDisplayId(it);
              return (
                <TableRow
                  key={it.wallet_address}
                  className="cursor-pointer"
                  onClick={() => setActive(it)}
                >
                <TableCell className="w-[28%]">
                  <div className="flex items-center gap-3">
                    <span
                      className="grid h-8 w-8 place-items-center rounded-full text-[10px] font-semibold text-white"
                      style={{ background: pickColor(it.wallet_address.length) }}
                    >
                      {identityInitials(it, it.wallet_address)}
                    </span>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{displayName}</span>
                      <span className="text-xs text-muted-foreground">
                        {displayId}
                      </span>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-sm">
                  {it.email ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell>
                  <KycBadge value={it.kyc_status ?? undefined} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{it.properties_count}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {it.avg_ownership_pct.toFixed(2)}%
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" className="h-7 w-7">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>

      <div className="flex flex-col items-center justify-center gap-1.5 border-t border-border px-4 py-3 text-sm text-muted-foreground">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={safePage <= 1}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="px-2 tabular-nums">{safePage}</span>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={safePage >= totalPages}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
        <span className="text-xs tabular-nums text-muted-foreground">
          Page {safePage} / {totalPages}
        </span>
      </div>
        </>
      )}

      <InvestorDetailsDialog row={active} onClose={() => setActive(null)} />
    </div>
  );
}

function KycBadge({ value, className }: { value?: string; className?: string }) {
  const v = (value || "").toLowerCase();
  if (v === "approved" || v === "verified") return <Badge variant="success" className={className}>Verified</Badge>;
  if (v === "pending") return <Badge variant="warning" className={className}>Pending</Badge>;
  if (v === "rejected") return <Badge variant="destructive" className={className}>Rejected</Badge>;
  return <Badge variant="muted" className={className}>—</Badge>;
}

function InvestorDetailsDialog({
  row,
  onClose,
}: {
  row: OwnerInvestor | null;
  onClose: () => void;
}) {
  const enabled = !!row?.wallet_address;
  const portfolio = useQuery({
    queryKey: ["portfolio", row?.wallet_address],
    queryFn: () =>
      api.get<{ holdings: Array<{ property_id: number; property_name: string; token_amount: string }> }>(
        `/portfolio/${row?.wallet_address}`,
      ),
    enabled,
    retry: false,
  });

  if (!row) return null;
  const displayName = identityDisplayName(row, row.wallet_address);
  const displayId = identityDisplayId(row);

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : null)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <span
              className="grid h-10 w-10 place-items-center rounded-full text-sm font-semibold text-white"
              style={{ background: pickColor(row.wallet_address.length) }}
            >
              {identityInitials(row, row.wallet_address)}
            </span>
            <div>
              <DialogTitle>{displayName}</DialogTitle>
              <DialogDescription>
                {row.properties_count} position{row.properties_count === 1 ? "" : "s"} · avg ownership{" "}
                {row.avg_ownership_pct.toFixed(2)}%
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Pair
            icon={<Wallet className="h-3.5 w-3.5" />}
            label="Profile ID"
            value={<span className="text-sm font-medium">{displayId}</span>}
          />
          <Pair icon={<Mail className="h-3.5 w-3.5" />} label="Email" value={row.email ?? "—"} />
          <Pair label="KYC" value={<KycBadge value={row.kyc_status ?? undefined} className="text-sm" />} />
          <Pair label="Member ID" value={row.user_id ? `#${row.user_id}` : "Unregistered"} />
        </div>
        <div className="rounded-md border border-border">
          <div className="flex items-center justify-between border-b border-border px-3 py-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Positions</span>
            <span>Ownership</span>
          </div>
          <div className="max-h-72 overflow-auto scrollbar-thin">
            {row.positions.map((p) => {
              const holding = portfolio.data?.holdings?.find((h) => h.property_id === p.property_id);
              const tokens = holding ? Number(holding.token_amount) / 1e18 : Number(p.token_amount);
              return (
                <div
                  key={p.property_id}
                  className="flex items-center justify-between gap-3 border-b border-border/60 px-3 py-2 last:border-0"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span
                      className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-sm font-bold text-white"
                      style={{ background: pickColor(p.property_id) }}
                    >
                      {p.token_symbol?.slice(0, 2) || "PR"}
                    </span>
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-medium">{p.property_name}</span>
                      <span className="text-sm text-muted-foreground">
                        {Number.isFinite(tokens) ? `${formatNumber(tokens)} tokens` : "—"}
                      </span>
                    </div>
                  </div>
                  <span className="tabular-nums text-sm font-medium">
                    {p.ownership_percentage.toFixed(2)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Pair({
  label,
  value,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="flex items-center gap-1 text-sm font-medium uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
