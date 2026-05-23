import AlertsPanel from "@/components/AlertsPanel";
import SummaryCards from "@/components/SummaryCards";
import QueryInterface from "@/components/QueryInterface";
import TransactionTable from "@/components/TransactionTable";
import IngestionStatus from "@/components/IngestionStatus";

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-xs font-bold">A</div>
        <span className="font-semibold tracking-tight">ArthaOS</span>
        <span className="text-xs text-white/30 ml-1">Personal Financial Intelligence</span>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {/* Alerts — prominent at top */}
        <AlertsPanel />

        {/* Summary cards */}
        <SummaryCards />

        {/* Query + Ingestion Status side by side on large screens */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <QueryInterface />
          </div>
          <div>
            <IngestionStatus />
          </div>
        </div>

        {/* Transaction table */}
        <TransactionTable />
      </main>
    </div>
  );
}
