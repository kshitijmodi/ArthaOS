"use client";
import { useState, useEffect, useRef } from "react";
import { TrendingUp, PieChart, ArrowUpRight, ArrowDownRight, Upload, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Account { broker: string; account: string; total_value: number; as_of_date: string; positions: number; }
interface Summary { portfolio_value: number; total_invested: number; total_dividends: number; accounts: Account[]; recent_transactions: InvestmentTx[]; }
interface InvestmentTx { id: number; date: string; ticker: string | null; name: string | null; transaction_type: string; quantity: number | null; price_per_unit: number | null; total_value: number; account: string; broker: string; }
interface Holding { id: number; as_of_date: string; ticker: string | null; name: string; quantity: number | null; price: number | null; total_value: number; gain_loss: number | null; gain_loss_pct: number | null; account: string; broker: string; }

const BROKER_LABELS: Record<string, string> = { robinhood: "Robinhood", schwab: "Schwab / ToS", fidelity: "Fidelity 401K" };
const BROKER_ACCENT: Record<string, string> = { robinhood: "text-income", schwab: "text-savings", fidelity: "text-accent" };
const BROKER_BAR: Record<string, string> = { robinhood: "bg-income", schwab: "bg-savings", fidelity: "bg-accent" };
const TX_COLORS: Record<string, string> = { buy: "text-income", sell: "text-expense", dividend: "text-warn", contribution: "text-savings", transfer: "text-tx-2", deposit: "text-income", withdrawal: "text-expense", fee: "text-warn", other: "text-tx-3" };

function fmt(n: number) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n); }
function fmtPct(n: number) { return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`; }

export default function InvestmentsPanel() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [selectedBroker, setSelectedBroker] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
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

  const filteredHoldings = selectedBroker ? holdings.filter(h => h.broker === selectedBroker) : holdings;
  const unrealizedGain = holdings.reduce((acc, h) => acc + (h.gain_loss ?? 0), 0);
  const gainPositive = unrealizedGain >= 0;

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
          <button
            onClick={load}
            className="p-2 text-tx-3 hover:text-tx-2 transition-colors rounded-xl hover:bg-elevated"
          >
            <RefreshCw size={14} />
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
          {/* KPI cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: "Portfolio Value", value: fmt(summary!.portfolio_value), color: "text-tx" },
              { label: "Total Invested",  value: fmt(summary!.total_invested),  color: "text-tx" },
              {
                label: "Unrealized G/L",
                value: fmt(Math.abs(unrealizedGain)),
                color: gainPositive ? "text-income" : "text-expense",
                icon: gainPositive
                  ? <ArrowUpRight size={14} className="text-income" />
                  : <ArrowDownRight size={14} className="text-expense" />,
              },
              { label: "Dividends", value: fmt(summary!.total_dividends), color: "text-warn" },
            ].map(c => (
              <div key={c.label} className="rounded-2xl border border-border bg-surface p-4">
                <p className="text-xs text-tx-3 mb-2">{c.label}</p>
                <div className="flex items-center gap-1">
                  {c.icon}
                  <p className={cn("text-xl font-bold", c.color)}>{c.value}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Account breakdown */}
          {summary!.accounts.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <div className="flex items-center gap-2 mb-4">
                <PieChart size={14} className="text-savings" />
                <h3 className="font-semibold text-tx text-sm">By Account</h3>
              </div>
              <div className="space-y-3">
                {summary!.accounts.map((acc, i) => {
                  const pct = summary!.portfolio_value > 0 ? (acc.total_value / summary!.portfolio_value) * 100 : 0;
                  return (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setSelectedBroker(selectedBroker === acc.broker ? null : acc.broker)}
                            className={cn("text-xs font-semibold transition-colors hover:underline", BROKER_ACCENT[acc.broker] ?? "text-tx-2")}
                          >
                            {BROKER_LABELS[acc.broker] ?? acc.broker}
                          </button>
                          <span className="text-xs text-tx-3">{acc.positions} positions</span>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-semibold text-tx">{fmt(acc.total_value)}</span>
                          <span className="text-xs text-tx-3 ml-2">{pct.toFixed(1)}%</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-elevated rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all", BROKER_BAR[acc.broker] ?? "bg-accent")}
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
                    <span className={cn("text-xs ml-2", BROKER_ACCENT[selectedBroker])}>
                      · {BROKER_LABELS[selectedBroker] ?? selectedBroker}
                    </span>
                  )}
                </h3>
                {selectedBroker && (
                  <button onClick={() => setSelectedBroker(null)} className="text-xs text-tx-3 hover:text-tx-2">
                    Show all
                  </button>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {["Ticker", "Name", "Qty", "Price", "Value", "Gain/Loss"].map((h, i) => (
                        <th key={h} className={cn("py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3", i > 1 ? "text-right" : "text-left")}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {filteredHoldings.map(h => (
                      <tr key={h.id} className="hover:bg-elevated transition-colors">
                        <td className="py-3 px-4 font-mono text-xs text-savings">{h.ticker ?? "—"}</td>
                        <td className="py-3 px-4 text-tx-2 max-w-[180px] truncate">{h.name}</td>
                        <td className="py-3 px-4 text-right text-tx-3 text-xs">{h.quantity != null ? h.quantity.toLocaleString() : "—"}</td>
                        <td className="py-3 px-4 text-right text-tx-3 text-xs">{h.price != null ? fmt(h.price) : "—"}</td>
                        <td className="py-3 px-4 text-right font-semibold text-tx">{fmt(h.total_value)}</td>
                        <td className="py-3 px-4 text-right">
                          {h.gain_loss != null ? (
                            <span className={h.gain_loss >= 0 ? "text-income" : "text-expense"}>
                              {fmt(h.gain_loss)}
                              {h.gain_loss_pct != null && <span className="text-xs ml-1 opacity-70">({fmtPct(h.gain_loss_pct)})</span>}
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
          {summary!.recent_transactions.length > 0 && (
            <div className="rounded-2xl border border-border bg-surface p-5">
              <h3 className="font-semibold text-tx text-sm mb-4">Recent Activity</h3>
              <div className="divide-y divide-border/40">
                {summary!.recent_transactions.map(tx => (
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
                        <p className="text-xs text-tx-3">{tx.date} · {BROKER_LABELS[tx.broker] ?? tx.broker}</p>
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
