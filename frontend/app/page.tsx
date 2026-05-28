"use client";
import { useState, useEffect, useMemo, useCallback } from "react";
import Sidebar, { View } from "@/components/Sidebar";
import FilterBar, { FilterState, defaultFilters } from "@/components/FilterBar";
import { Menu, Zap } from "lucide-react";
import KPICards from "@/components/KPICards";
import CategoryDonut from "@/components/CategoryDonut";
import DrillDownModal from "@/components/DrillDownModal";
import TransactionTable from "@/components/TransactionTable";
import AnalyticsPanel from "@/components/AnalyticsPanel";
import AlertsPanel from "@/components/AlertsPanel";
import GoalsPanel from "@/components/GoalsPanel";
import GoalStrip from "@/components/GoalStrip";
import UpcomingCharges from "@/components/UpcomingCharges";
import InvestmentsPanel from "@/components/InvestmentsPanel";
import InsightsPanel from "@/components/InsightsPanel";
import IngestionStatus from "@/components/IngestionStatus";
import CategoryManager from "@/components/CategoryManager";
import TellerConnect from "@/components/TellerConnect";
import { getTransactions, Transaction } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import FloatingChat from "@/components/FloatingChat";

/** End-of-period ISO date for /dashboard/accounts-summary ?as_of= */
function periodEndDate(f: FilterState): string | undefined {
  if (f.mode === "monthly") {
    const [y, m] = f.selectedMonth.split("-").map(Number);
    const lastDay = new Date(y, m, 0); // day 0 of next month = last day of this month
    return lastDay.toISOString().slice(0, 10);
  }
  if (f.mode === "weekly") {
    const now = new Date();
    const dayOfWeek = now.getDay();
    const monday = new Date(now);
    monday.setDate(now.getDate() - ((dayOfWeek + 6) % 7) - f.weekOffset * 7);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    return sunday.toISOString().slice(0, 10);
  }
  if (f.mode === "custom" && f.dateTo) return f.dateTo;
  return undefined;
}

function applyFilters(txns: Transaction[], f: FilterState): Transaction[] {
  return txns.filter(t => {
    const date = new Date(t.date);
    const now = new Date();

    if (f.mode === "monthly") {
      // selectedMonth is "YYYY-MM"
      const [y, m] = f.selectedMonth.split("-").map(Number);
      if (date.getFullYear() !== y || date.getMonth() + 1 !== m) return false;
    } else if (f.mode === "weekly") {
      // weekOffset: 0 = this week (Mon–Sun), 1 = last week, etc.
      const dayOfWeek = now.getDay(); // 0=Sun
      const monday = new Date(now);
      monday.setDate(now.getDate() - ((dayOfWeek + 6) % 7) - f.weekOffset * 7);
      monday.setHours(0, 0, 0, 0);
      const sunday = new Date(monday);
      sunday.setDate(monday.getDate() + 7);
      if (date < monday || date >= sunday) return false;
    } else if (f.mode === "custom") {
      if (f.dateFrom && t.date < f.dateFrom) return false;
      if (f.dateTo   && t.date > f.dateTo)   return false;
    }

    if (f.categories.length > 0 && !f.categories.includes(t.category)) return false;
    if (f.amountMin > 0 && t.amount < f.amountMin) return false;
    if (f.amountMax > 0 && t.amount > f.amountMax) return false;
    return true;
  });
}

export default function Page() {
  const [activeView, setActiveView] = useState<View>("dashboard");
  const [allTxns, setAllTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [drillDown, setDrillDown] = useState<{ label: string; txns: Transaction[] } | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    getTransactions({ page: 1, page_size: 1000, sort_by: "date", sort_dir: "desc" })
      .then(r => setAllTxns(r.transactions))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const filteredTxns = useMemo(() => applyFilters(allTxns, filters), [allTxns, filters]);

  const maxAmount = useMemo(() =>
    Math.ceil(Math.max(...allTxns.map(t => t.amount), 1000) / 100) * 100,
    [allTxns]
  );

  const openDrill = useCallback((label: string, txns: Transaction[]) => {
    setDrillDown({ label, txns });
  }, []);

  const asOf = useMemo(() => periodEndDate(filters), [filters]);

  const navigate = useCallback((v: View) => {
    setActiveView(v);
    setMobileNavOpen(false);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* Mobile backdrop */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      {/* Sidebar — always in flow on desktop, overlay on mobile */}
      <div className={cn(
        "md:flex md:relative md:z-auto shrink-0",
        mobileNavOpen ? "flex fixed inset-y-0 left-0 z-50" : "hidden"
      )}>
        <Sidebar activeView={activeView} onNavigate={navigate} />
      </div>

      <main className="flex-1 overflow-y-auto min-w-0">
        {/* Mobile top bar */}
        <div className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-border bg-surface sticky top-0 z-30">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="p-1.5 rounded-lg text-tx-2 hover:text-tx hover:bg-elevated transition-colors"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-accent flex items-center justify-center">
              <Zap size={11} className="text-white" />
            </div>
            <span className="font-bold text-sm text-tx">ArthaOS</span>
          </div>
        </div>

        {activeView === "dashboard" && (
          <DashboardView
            filters={filters}
            onFiltersChange={setFilters}
            allTxns={allTxns}
            filteredTxns={filteredTxns}
            loading={loading}
            maxAmount={maxAmount}
            onDrillDown={openDrill}
            onNavigate={navigate}
            asOf={asOf}
          />
        )}
        {activeView === "transactions" && (
          <div className="p-4 md:p-6 max-w-[1200px] mx-auto">
            <div className="mb-6">
              <h1 className="text-xl font-bold text-tx">Transactions</h1>
              <p className="text-sm text-tx-2 mt-1">Full history with search, star, and category editing</p>
            </div>
            <TransactionTable />
          </div>
        )}
        {activeView === "investments" && (
          <div className="p-4 md:p-6 max-w-[1200px] mx-auto">
            <div className="mb-6">
              <h1 className="text-xl font-bold text-tx">Investments</h1>
              <p className="text-sm text-tx-2 mt-1">Robinhood · Schwab · Fidelity 401K</p>
            </div>
            <InvestmentsPanel />
          </div>
        )}
        {activeView === "alerts" && (
          <div className="p-4 md:p-6 max-w-[900px] mx-auto">
            <div className="mb-6">
              <h1 className="text-xl font-bold text-tx">Alerts</h1>
              <p className="text-sm text-tx-2 mt-1">Anomalies, overspends, duplicates and upcoming charges</p>
            </div>
            <AlertsPanel />
          </div>
        )}
        {activeView === "goals" && (
          <div className="p-4 md:p-6 max-w-[900px] mx-auto">
            <div className="mb-6">
              <h1 className="text-xl font-bold text-tx">Goals</h1>
              <p className="text-sm text-tx-2 mt-1">Spend limits, savings targets and investment milestones</p>
            </div>
            <GoalsPanel />
          </div>
        )}
        {activeView === "settings" && (
          <div className="p-4 md:p-6 max-w-[900px] mx-auto space-y-8">
            <div>
              <h1 className="text-xl font-bold text-tx">Settings</h1>
              <p className="text-sm text-tx-2 mt-1">Email ingestion, categories and system configuration</p>
            </div>
            <TellerConnect />
            <IngestionStatus />
            <InsightsPanel />
            <CategoryManager />
          </div>
        )}
      </main>

      {drillDown && (
        <DrillDownModal
          label={drillDown.label}
          transactions={drillDown.txns}
          onClose={() => setDrillDown(null)}
        />
      )}

      {/* Global floating chat — always visible */}
      <FloatingChat />
    </div>
  );
}

interface DashboardProps {
  filters: FilterState;
  onFiltersChange: (f: FilterState) => void;
  allTxns: Transaction[];
  filteredTxns: Transaction[];
  loading: boolean;
  maxAmount: number;
  onDrillDown: (label: string, txns: Transaction[]) => void;
  onNavigate: (v: View) => void;
  asOf?: string;
}

function DashboardView({
  filters, onFiltersChange, allTxns, filteredTxns,
  loading, maxAmount, onDrillDown, onNavigate, asOf,
}: DashboardProps) {
  const recentTxns = filteredTxns.slice(0, 8);

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[1400px] mx-auto">
      {/* Header — hidden on mobile (top bar in page.tsx covers it) */}
      <div className="hidden md:flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-tx">Financial Overview</h1>
          <p className="text-sm text-tx-2 mt-1">
            {new Date().toLocaleDateString("en-US", {
              weekday: "long", month: "long", day: "numeric", year: "numeric",
            })}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-tx-3 bg-surface border border-border px-3 py-1.5 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-income" />
          Live
        </div>
      </div>

      <FilterBar filters={filters} onChange={onFiltersChange} maxAmount={maxAmount} />

      <KPICards transactions={filteredTxns} allTxns={allTxns} onDrillDown={onDrillDown} asOf={asOf} />

      {/* Charts — inline analytics */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        {/* Category Donut */}
        <div className="lg:col-span-2 bg-surface border border-border rounded-2xl p-5">
          <h2 className="font-semibold text-tx">Spending by Category</h2>
          <p className="text-xs text-tx-2 mb-5 mt-0.5">Click any segment to drill down</p>
          <CategoryDonut transactions={filteredTxns} onDrillDown={onDrillDown} />
        </div>
        {/* Monthly trend inline */}
        <div className="lg:col-span-3 bg-surface border border-border rounded-2xl p-5">
          <h2 className="font-semibold text-tx">Monthly Trends</h2>
          <p className="text-xs text-tx-2 mb-4 mt-0.5">Category breakdown · last 12 months</p>
          <AnalyticsPanel compact />
        </div>
      </div>

      {/* Goals strip */}
      <GoalStrip onNavigate={onNavigate as (v: "goals") => void} />

      {/* Recent Transactions */}
      <div className="bg-surface border border-border rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <h2 className="font-semibold text-tx">Recent Transactions</h2>
            <p className="text-xs text-tx-2 mt-0.5">{filteredTxns.length} in selected period</p>
          </div>
          <button
            onClick={() => onNavigate("transactions")}
            className="text-xs text-accent hover:text-accent-h transition-colors font-medium"
          >
            View all →
          </button>
        </div>
        {loading ? (
          <div className="p-5 space-y-3 animate-pulse">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <div className="w-9 h-9 bg-elevated rounded-full shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 bg-elevated rounded w-48" />
                  <div className="h-2.5 bg-elevated rounded w-24" />
                </div>
                <div className="h-4 bg-elevated rounded w-20" />
              </div>
            ))}
          </div>
        ) : recentTxns.length === 0 ? (
          <div className="py-12 text-center text-sm text-tx-2">
            No transactions for selected filters
          </div>
        ) : (
          <ul className="divide-y divide-border/40">
            {recentTxns.map(t => (
              <li key={t.id} className="flex items-center gap-4 py-3.5 px-5 hover:bg-elevated transition-colors">
                <div className={cn(
                  "w-9 h-9 rounded-full flex items-center justify-center shrink-0 text-sm font-bold",
                  t.transaction_type === "credit" ? "bg-income/10 text-income" : "bg-expense/10 text-expense"
                )}>
                  {t.transaction_type === "credit" ? "↑" : "↓"}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-tx truncate">{t.description}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-tx-3">
                      {new Date(t.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                    {t.institution && (
                      <span className="text-[10px] text-tx-3">{t.institution}</span>
                    )}
                    {t.category && (
                      <span className="text-[10px] bg-elevated text-tx-2 px-1.5 py-0.5 rounded-full border border-border/50">
                        {t.category}
                      </span>
                    )}
                  </div>
                </div>
                <span className={cn(
                  "font-semibold text-sm tabular-nums shrink-0",
                  t.transaction_type === "credit" ? "text-income" : "text-tx"
                )}>
                  {t.transaction_type === "credit" ? "+" : "−"}{formatCurrency(t.amount)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Upcoming Charges */}
      <UpcomingCharges allTxns={allTxns} />
    </div>
  );
}
