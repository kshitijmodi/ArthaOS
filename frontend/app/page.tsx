"use client";
import { useState } from "react";
import AlertsPanel from "@/components/AlertsPanel";
import SummaryCards from "@/components/SummaryCards";
import QueryInterface from "@/components/QueryInterface";
import TransactionTable from "@/components/TransactionTable";
import IngestionStatus from "@/components/IngestionStatus";
import AnalyticsPanel from "@/components/AnalyticsPanel";
import InsightsPanel from "@/components/InsightsPanel";
import CategoryManager from "@/components/CategoryManager";
import { cn } from "@/lib/utils";

const TABS = ["Overview", "Analytics", "Transactions", "Insights", "Settings"] as const;
type Tab = typeof TABS[number];

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("Overview");

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center gap-4">
        <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-xs font-bold text-white">A</div>
        <span className="font-semibold tracking-tight text-white">ArthaOS</span>
        <span className="text-xs text-white/30">Personal Financial Intelligence</span>

        {/* Tab nav */}
        <nav className="ml-auto flex gap-1">
          {TABS.map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-4 py-1.5 rounded-lg text-sm transition-colors",
                tab === t
                  ? "bg-white/10 text-white"
                  : "text-white/40 hover:text-white/70"
              )}
            >
              {t}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {/* Alerts always visible */}
        <AlertsPanel />

        {tab === "Overview" && (
          <>
            <SummaryCards />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <QueryInterface />
              </div>
              <div>
                <IngestionStatus />
              </div>
            </div>
          </>
        )}

        {tab === "Analytics" && <AnalyticsPanel />}

        {tab === "Transactions" && <TransactionTable />}

        {tab === "Insights" && <InsightsPanel />}

        {tab === "Settings" && <CategoryManager />}
      </main>
    </div>
  );
}
