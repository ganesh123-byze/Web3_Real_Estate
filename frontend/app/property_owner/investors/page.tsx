"use client";

import { AdminTopbar } from "@/components/layout/topbar";
import { InvestorsTable } from "@/components/investors/investors-table";
import { useOwnerInvestors } from "@/lib/queries";

export default function InvestorsPage() {
  const investors = useOwnerInvestors();
  return (
    <>
      <AdminTopbar
        title="Investors"
        subtitle="Token holders with real on-chain positions in your properties"
      />
      <main className="flex-1 space-y-4 p-4 lg:p-6">
        <InvestorsTable
          investors={investors.data ?? []}
          loading={investors.isLoading}
        />
      </main>
    </>
  );
}
