"use client";
import { useState, useEffect, useRef } from "react";
import { TrendingUp, PieChart, ArrowUpRight, ArrowDownRight, Upload, RefreshCw, RotateCcw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Account {
  broker: string;
  account: string;
  total_value: number;
  as_of_date: string;
  positions: number;
  gain_loss: number;
  gain_loss_day: number;
}
interface Summary {
  portfolio_value: number;
  total_invested: number;
  total_dividends: number;
  accounts: Account[];
  recent_transactions: InvestmentTx[];
}
interface InvestmentTx {
  id: number; date: string; ticker: string | null; name: string | null;
  transaction_type: string; quantity: number | null; price_per_unit: number | null;
  total_value: number; account: string; broker: string;
}
interface Holding {
  id: number; as_of_date: string; ticker: string | null; name: string;
  quantity: number | null; price: number | null; total_value: number;
  cost_basis: number | null;
  gain_loss: number | null; gain_loss_pct: number | null;
  gain_loss_day: number | null;
  account: string; broker: string;
}

const BROKER_LABELS: Record<string, string> = {
  robinhood: "Robinhood",
  schwab: "Schwab / ToS",
  "charles schwab": "Schwab / ToS",
  charlesschwab: "Schwab / ToS",
  fidelity: "Fidelity 401K",
  "fidelity investments": "Fidelity 401K",
};
const BROKER_ACCENT: Record<string, string> = {
  robinhood: "text-income",
  schwab: "text-savings",
  "charles schwab": "text-savings",
  charlesschwab: "text-savings",
  fidelity: "text-accent",
  "fidelity investments": "text-accent",
};
const BROKER_BAR: Record<string, string> = {
  robinhood: "bg-income",
  schwab: "bg-savings",
  "charles schwab": "bg-savings",
  charlesschwab: "bg-savings",
  fidelity: "bg-accent",
  "fidelity investments": "bg-accent",
};

function brokerKey(broker: string): string {
  return broker.toLowerCase().replace(/\s+/g, " ").trim();
}
const TX_COLORS: Record<string, string> = {
  buy: "text-income", sell: "text-expense", dividend: "text-warn",
  contribution: "text-savings", transfer: "text-tx-2", deposit: "text-income",
  withdrawal: "text-expense", fee: "text-warn", other: "text-tx-3",
};

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}
function fmtPct(n: number) { return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`; }
function fmtPL(n: number | null, pct?: number | null) {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${fmt(n)}${pct != null ? ` (${fmtPct(pct)})` : ""}`;
}

function KPICard({
  label, value, sub, color, icon,
}: {
  label: string; value: string; sub?: string;
  color?: string; icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-tx-3 mb-2">{label}</p>
      <div className="flex items-center gap-1">
        {icon}
        <p className={cn("text-lg font-bold leading-none", color ?? "text-tx")}>{value}</p>
      </div>
      {sub && <p className="text-[11px] text-tx-3 mt-1">{sub}</p>}
    </div>
  );
}

export default function InvestmentsPanel() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [selectedBroker, setSelectedBroker] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [reingesting, setReingesting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, h] = await Promise.all([
        apiFetch<Summary>("/investments/summary"),
        apiFetch<{ holdings: Holding[] }>("/investments/holdings"),
      ]);
      setSummary(s); setHoldings(h.holdings);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/investments/upload`, { method: "POST", body: form });
      const data = await res.json();
      if (data.status === "success") {
        setUploadMsg(`Imported ${data.transactions_stored} transactions, ${data.holdings_stored} holdings from ${data.broker}`);
        load();
      } else {
        setUploadMsg(`Import failed: ${data.reason}`);
      }
    } catch { setUploadMsg("Upload failed — check backend connection."); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const handleReingest = async () => {
    setReingesting(true);
    setUploadMsg(null);
    try {
      const data = await apiFetch<{ reingested: number; results: { broker?: string; holdings_stored?: number }[] }>("/investments/reingest", { method: "POST" });
      const total = data.results.reduce((s, r) => s + (r.holdings_stored ?? 0), 0);
      setUploadMsg(`Re-imported ${data.reingested} file(s), ${total} holdings updated`);
      load();
    } catch { setUploadMsg("Re-import failed — check backend connection."); }
    finally { setReingesting(false); }
  };

  // Two broker names can map to the same canonical label (e.g. "Fidelity" and
  // "Fidelity Investments" both → "Fidelity 401K"). Group them together so only
  // one tab appears and filtering shows holdings from both variants.
  function sameGroup(b1: string, b2: string): boolean {
    const label = (b: string) => BROKER_LABELS[brokerKey(b)] ?? b;
    return label(b1) === label(b2);
  }

  const filteredHoldings = selectedBroker ? holdings.filter(h => sameGroup(h.broker, selectedBroker)) : holdings;
  const filteredRecentTxns = selectedBroker
    ? (summary?.recent_transactions ?? []).filter(tx => sameGroup(tx.broker, selectedBroker))
    : (summary?.recent_transactions ?? []);

  // Deduplicate tabs by canonical label — keeps first broker name per group
  const availableBrokers = Array.from(
    new Map((summary?.accounts ?? []).map(a => [BROKER_LABELS[brokerKey(a.broker)] ?? a.broker, a.broker])).values()
  );

  // Broker totals for top KPI bar — broker names are lowercased in DB (PDF parser)
  // but Plaid may store as "Robinhood" (capital). Normalise to lowercase for matching.
  const normalize = (b: string) => b.toLowerCase().replace(/\s+/g, "");
  const rhAcc  = summary?.accounts.find(a => normalize(a.broker) === "robinhood");
  const csAcc  = summary?.accounts.find(a => normalize(a.broker).startsWith("schwab") || normalize(a.broker).startsWith("charlesschwab"));
  const stockAccounts = (summary?.accounts ?? []).filter(a => normalize(a.broker) === "robinhood" || normalize(a.broker).startsWith("schwab") || normalize(a.broker).startsWith("charlesschwab"));
  const totalStocks   = stockAccounts.reduce((s, a) => s + a.total_value, 0);
  const totalPLOpen   = stockAccounts.reduce((s, a) => s + (a.gain_loss ?? 0), 0);
  const totalPLDay    = stockAccounts.reduce((s, a) => s + (a.gain_loss_day ?? 0), 0);
  const hasPLOpen     = stockAccounts.some(a => a.gain_loss != null);
  const hasPLDay      = stockAccounts.some(a => a.gain_loss_day !== 0);

  if (loading) return (
    <div className="space-y-4">
      {[1, 2, 3].map(i => <div key={i} className="rounded-2xl border border-border bg-surface p-5 animate-pulse h-32" />)}
    </div>
  );

  const hasData = summary && (summary.portfolio_value > 0 || summary.accounts.length > 0);

  return (
    <section className="space-y-5">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp size={18} className="text-savings" />
          <h2 className="font-semibold text-tx text-lg">Investment Portfolio</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-2 text-tx-3 hover:text-tx-2 transition-colors rounded-xl hover:bg-elevated">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={handleReingest}
            disabled={reingesting}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs transition-colors",
              reingesting ? "bg-savings/50 text-white/50 cursor-not-allowed" : "bg-savings/20 hover:bg-savings/30 text-savings"
            )}
            title="Re-parse all uploaded statements and update P/L data"
          >
            <RotateCcw size={13} />
            {reingesting ? "Re-importing…" : "Re-import"}
          </button>
          <label className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs transition-colors cursor-pointer",
            uploading ? "bg-accent/50 text-white/50" : "bg-accent hover:bg-accent-h text-white"
          )}>
            <Upload size={13} />
            {uploading ? "Uploading…" : "Upload Statement"}
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleUpload} disabled={uploading} />
          </label>
        </div>
      </div>

      {uploadMsg && (
        <div className={cn(
          "rounded-xl px-4 py-3 text-sm border",
          uploadMsg.includes("failed") || uploadMsg.includes("Failed")
            ? "bg-expense/10 border-expense/30 text-expense"
            : "bg-income/10 border-income/30 text-income"
        )}>
          {uploadMsg}
        </div>
      )}

      {!hasData ? (
        <div className="rounded-2xl border border-border bg-surface p-12 text-center">
          <TrendingUp size={32} className="text-tx-3 mx-auto mb-3" />
          <p className="text-tx-2 text-sm">No investment data yet.</p>
          <p className="text-tx-3 text-xs mt-1">Upload a Robinhood, Schwab, or Fidelity statement to get started.</p>
        </div>
      ) : (
        <>
          {/* ── Top KPI bar: RH, CS, Total, P/L Day, P/L Open ── */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <KPICard
              label="Robinhood"
              value={rhAcc ? fmt(rhAcc.total_value) : "—"}
              sub={rhAcc ? `${rhAcc.positions} positions` : "not connected"}
              color="text-income"
            />
            <KPICard
              label="Charles Schwab"
              value={csAcc ? fmt(csAcc.total_value) : "—"}
              sub={csAcc ? `${csAcc.positions} positions` : "not connected"}
              color="text-savings"
            />
            <KPICard
              label="Total (RH + CS)"
              value={fmt(totalStocks)}
              sub="combined stocks"
              color="text-tx"
            />
            <KPICard
              label="P/L Day"
              value={hasPLDay ? (totalPLDay >= 0 ? `+${fmt(totalPLDay)}` : fmt(totalPLDay)) : "—"}
              sub={hasPLDay ? "today vs yesterday" : "live data unavailable"}
              color={hasPLDay ? (totalPLDay >= 0 ? "text-income" : "text-expense") : "text-tx-3"}
              icon={hasPLDay && totalPLDay !== 0
                ? (totalPLDay >= 0
                  ? <ArrowUpRight size={14} className="text-income" />
                  : <ArrowDownRight size={14} className="text-expense" />)
                : undefined}
            />
            <KPICard
              label="P/L Open"
              value={hasPLOpen ? (totalPLOpen >= 0 ? `+${fmt(totalPLOpen)}` : fmt(totalPLOpen)) : "—"}
              sub={hasPLOpen ? "unrealized since purchase" : "upload statement with cost basis"}
              color={hasPLOpen ? (totalPLOpen >= 0 ? "text-income" : "text-expense") : "text-tx-3"}
              icon={hasPLOpen && totalPLOpen !== 0
                ? (totalPLOpen >= 0
                  ? <ArrowUpRight size={14} className="text-income" />
                  : <ArrowDownRight size={14} className="text-expense" />)
                : undefined}
            />
          </div>

          {/* Broker filter tabs */}
          {availableBrokers.length > 1 && (
            <div className="flex items-center gap-1.5 bg-elevated rounded-xl p-1 border border-border/50 w-fit">
              <button
                onClick={() => setSelectedBroker(null)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                  selectedBroker === null ? "bg-surface text-tx shadow-sm" : "text-tx-2 hover:text-tx"
                )}
              >
                All accounts
              </button>
              {availableBrokers.map(broker => (
                <button
                  key={broker}
                  onClick={() => setSelectedBroker(selectedBroker === broker ? null : broker)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                    selectedBroker === broker
                      ? cn("bg-surface shadow-sm", BROKER_ACCENT[brokerKey(broker)] ?? "text-tx")
                      : "text-tx-2 hover:text-tx"
                  )}
                >
                  {BROKER_LABELS[brokerKey(broker)] ?? broker}
                </button>
              ))}
            </div>
          )}

          {/* Account allocation */}
          {summary!.accounts.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <div className="flex items-center gap-2 mb-4">
                <PieChart size={14} className="text-savings" />
                <h3 className="font-semibold text-tx text-sm">Portfolio allocation</h3>
              </div>
              <div className="space-y-3">
                {summary!.accounts
                  .filter(acc => !selectedBroker || brokerKey(acc.broker) === brokerKey(selectedBroker))
                  .map((acc, i) => {
                    const pct = summary!.portfolio_value > 0 ? (acc.total_value / summary!.portfolio_value) * 100 : 0;
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span className={cn("text-xs font-semibold", BROKER_ACCENT[brokerKey(acc.broker)] ?? "text-tx-2")}>
                              {BROKER_LABELS[brokerKey(acc.broker)] ?? acc.broker}
                            </span>
                            <span className="text-xs text-tx-3">{acc.account}</span>
                            <span className="text-xs text-tx-3">· {acc.positions} positions</span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-semibold text-tx">{fmt(acc.total_value)}</span>
                            <span className="text-xs text-tx-3 ml-2">{pct.toFixed(1)}%</span>
                          </div>
                        </div>
                        <div className="h-1.5 bg-elevated rounded-full overflow-hidden">
                          <div
                            className={cn("h-full rounded-full transition-all", BROKER_BAR[brokerKey(acc.broker)] ?? "bg-accent")}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Holdings table */}
          {filteredHoldings.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h3 className="font-semibold text-tx text-sm">
                  Holdings
                  {selectedBroker && (
                    <span className={cn("text-xs ml-2", BROKER_ACCENT[brokerKey(selectedBroker)])}>
                      · {BROKER_LABELS[brokerKey(selectedBroker)] ?? selectedBroker}
                    </span>
                  )}
                  <span className="text-xs text-tx-3 ml-2">({filteredHoldings.length})</span>
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {["Ticker", "Name", "Shares", "Price", "Equity Value", "P/L Day", "P/L Open"].map((h, i) => (
                        <th key={h} className={cn(
                          "py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3",
                          i > 1 ? "text-right" : "text-left"
                        )}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {filteredHoldings.map(h => (
                      <tr key={h.id} className="hover:bg-elevated transition-colors">
                        <td className="py-3 px-4 font-mono text-xs text-savings font-semibold">{h.ticker ?? "—"}</td>
                        <td className="py-3 px-4 text-tx-2 max-w-[160px] truncate text-xs">{h.name}</td>
                        <td className="py-3 px-4 text-right text-tx-3 text-xs tabular-nums">
                          {h.quantity != null ? h.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 }) : "—"}
                        </td>
                        <td className="py-3 px-4 text-right text-tx-3 text-xs tabular-nums">
                          {h.price != null ? fmt(h.price) : "—"}
                        </td>
                        <td className="py-3 px-4 text-right font-semibold text-tx tabular-nums">{fmt(h.total_value)}</td>
                        <td className="py-3 px-4 text-right text-xs tabular-nums">
                          {h.gain_loss_day != null ? (
                            <span className={h.gain_loss_day >= 0 ? "text-income" : "text-expense"}>
                              {h.gain_loss_day >= 0 ? "+" : ""}{fmt(h.gain_loss_day)}
                            </span>
                          ) : (
                            <span className="text-tx-3">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right text-xs tabular-nums">
                          {h.gain_loss != null ? (
                            <span className={h.gain_loss >= 0 ? "text-income" : "text-expense"}>
                              {fmtPL(h.gain_loss, h.gain_loss_pct)}
                            </span>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Recent activity */}
          {filteredRecentTxns.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <h3 className="font-semibold text-tx text-sm mb-4">Recent Activity</h3>
              <div className="divide-y divide-border/40">
                {filteredRecentTxns.map(tx => (
                  <div key={tx.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <span className={cn("text-xs font-semibold uppercase tracking-wide w-20 shrink-0", TX_COLORS[tx.transaction_type] ?? "text-tx-3")}>
                        {tx.transaction_type}
                      </span>
                      <div>
                        <p className="text-sm text-tx">
                          {tx.ticker && <span className="font-mono text-savings mr-1">{tx.ticker}</span>}
                          {tx.name && <span className="text-tx-2">{tx.name}</span>}
                          {!tx.ticker && !tx.name && <span className="text-tx-3">—</span>}
                        </p>
                        <p className="text-xs text-tx-3">{tx.date} · {BROKER_LABELS[brokerKey(tx.broker)] ?? tx.broker}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-tx">{fmt(tx.total_value)}</p>
                      {tx.quantity != null && <p className="text-xs text-tx-3">{tx.quantity} shares</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
