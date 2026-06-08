"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/common/empty";
import { type ViewMode, ViewModeToggle } from "@/components/common/view-mode-toggle";
import { useClaimHistory, useInvestorDistributions } from "@/lib/queries";
import { formatDateTime, formatEth } from "@/lib/utils";
import { txExplorerUrl } from "@/lib/runtime-config";
import { useCurrentWallet } from "@/components/investor/use-current-wallet";

type EarningsView = ViewMode;
type ClaimHistoryView = ViewMode;

export function InvestorEarningsAndClaimSections() {
  const wallet = useCurrentWallet();
  const distributions = useInvestorDistributions(wallet);
  const history = useClaimHistory(wallet);
  const [earningsView, setEarningsView] = useState<EarningsView>("cards");
  const [claimHistoryView, setClaimHistoryView] = useState<ClaimHistoryView>("cards");
  const earningsRows = distributions.data ?? [];
  const claimRows = history.data ?? [];

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader className="relative pr-24">
          <div>
            <CardTitle>Earnings by Property</CardTitle>
            <CardDescription>Aggregated rental accruals per property.</CardDescription>
          </div>
          <ViewModeToggle
            value={earningsView}
            onChange={setEarningsView}
            ariaLabel="Earnings by property view"
            className="absolute right-5 top-5"
          />
        </CardHeader>
        <CardContent>
          {distributions.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
            </div>
          ) : earningsRows.length === 0 ? (
            <EmptyState title="No earnings yet" />
          ) : earningsView === "cards" ? (
            <div className="max-h-[300px] space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {earningsRows.map((row) => (
                <div
                  key={row.property_id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2"
                >
                  <div className="min-w-0 whitespace-nowrap">
                    <div className="text-sm font-medium">{row.property_name ?? `Property #${row.property_id}`}</div>
                    <div className="text-xs text-muted-foreground">
                      {row.payment_count} payments · {row.current_ownership}% ownership
                    </div>
                  </div>
                  <div className="shrink-0 whitespace-nowrap text-sm font-semibold tabular-nums">{formatEth(row.total_earned_eth)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="max-h-[300px] overflow-y-auto rounded-xl border border-border scrollbar-thin">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="whitespace-nowrap">Property</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Payments</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Ownership</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Earned</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {earningsRows.map((row) => (
                    <TableRow key={row.property_id}>
                      <TableCell className="whitespace-nowrap font-medium">
                        {row.property_name ?? `Property #${row.property_id}`}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{row.payment_count}</TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{row.current_ownership}%</TableCell>
                      <TableCell className="whitespace-nowrap text-right font-semibold tabular-nums">{formatEth(row.total_earned_eth)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="relative pr-24">
          <div>
            <CardTitle>Claim History</CardTitle>
            <CardDescription>Completed withdrawal transactions.</CardDescription>
          </div>
          <ViewModeToggle
            value={claimHistoryView}
            onChange={setClaimHistoryView}
            ariaLabel="Claim history view"
            className="absolute right-5 top-5"
          />
        </CardHeader>
        <CardContent>
          {history.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
            </div>
          ) : claimRows.length === 0 ? (
            <EmptyState title="No claims yet" />
          ) : claimHistoryView === "cards" ? (
            <div className="max-h-[300px] space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {claimRows.map((claim) => (
                <a
                  key={claim.claim_tx_hash}
                  href={txExplorerUrl(claim.claim_tx_hash)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 px-3 py-2 transition-colors hover:bg-muted"
                >
                  <div className="min-w-0 whitespace-nowrap">
                    <div className="text-sm font-medium">{claim.property_name ?? `Property #${claim.property_id}`}</div>
                    <div className="text-xs text-muted-foreground">
                      {claim.payout_count} payout rows · {formatDateTime(claim.claimed_at)} ·{" "}
                      {shortHash(claim.claim_tx_hash)}
                    </div>
                  </div>
                  <div className="shrink-0 whitespace-nowrap text-sm font-semibold tabular-nums text-success">{formatEth(claim.claimed_amount_eth)}</div>
                </a>
              ))}
            </div>
          ) : (
            <div className="max-h-[300px] overflow-y-auto rounded-xl border border-border scrollbar-thin">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="whitespace-nowrap">Property</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Payouts</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Claimed</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Date</TableHead>
                    <TableHead className="whitespace-nowrap">Hash</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {claimRows.map((claim) => (
                    <TableRow key={claim.claim_tx_hash}>
                      <TableCell className="whitespace-nowrap font-medium">
                        {claim.property_name ?? `Property #${claim.property_id}`}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums">{claim.payout_count}</TableCell>
                      <TableCell className="whitespace-nowrap text-right font-semibold tabular-nums text-success">
                        {formatEth(claim.claimed_amount_eth)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right text-muted-foreground">{formatDateTime(claim.claimed_at)}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                        <a
                          href={txExplorerUrl(claim.claim_tx_hash)}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:underline"
                        >
                          {shortHash(claim.claim_tx_hash)}
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function shortHash(hash: string): string {
  return `${hash.slice(0, 3)}...`;
}
