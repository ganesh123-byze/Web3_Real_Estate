"use client";

import { useMemo } from "react";
import { AdminTopbar } from "@/components/layout/topbar";
import { InvestorsTable } from "@/components/investors/investors-table";
import { useOwnerInvestors, useProperties, useTransactions } from "@/lib/queries";
import { ownerInvestorsWithTransactionFallback } from "@/lib/ownership";

export default function InvestorsPage() {
  const investors = useOwnerInvestors();
  const properties = useProperties();
  const transactions = useTransactions();
  const visibleInvestors = useMemo(
    () => ownerInvestorsWithTransactionFallback(investors.data, properties.data, transactions.data),
    [investors.data, properties.data, transactions.data],
  );
  return (
    <>
      <AdminTopbar
        title="Investors"
        subtitle="Token holders with real on-chain positions in your properties"
      />
      <main className="flex-1 space-y-4 p-4 lg:p-6">
        <InvestorsTable
          investors={visibleInvestors}
          loading={investors.isLoading || properties.isLoading || transactions.isLoading}
        />
      </main>
    </>
  );
}
