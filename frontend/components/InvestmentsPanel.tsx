"use client";
import { useState, useEffect, useRef } from "react";
import { TrendingUp, DollarSign, PieChart, ArrowUpRight, ArrowDownRight, Upload, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Account {
  broker: string;
  account: string;
  total_value: number;
  as_of_date: string;
  positions: number;
}

interface Summary {
  portfolio_value: number;
  total_invested: number;
  total_dividends: number;
  accounts: Account[];
  recent_transactions: InvestmentTx[];
}

interface InvestmentTx {
  id: number;
  date: string;
  ticker: string | null;
  name: string | null;
  transaction_type: string;
  quantity: number | null;
  price_per_unit: number | null;
  total_value: number;
  account: string;
  broker: string;
}

interface Holding {
  id: number;
  as_of_date: string;
  ticker: string | null;
  name: string;
  quantity: number | null;
  price: number | null;
  total_value: number;
  gain_loss: number | null;
  gain_loss_pct: number | null;
  account: string;
  broker: string;
}

const BROKER_LABELS: Record<string, string> = {
  robinhood: "Robinhood",
  schwab: "Schwab / ToS",
  fidelity: "Fidelity 401K",
};

const BROKER_COLORS: Record<string, string> = {
  robinhood: "text-green-400",
  schwab: "text-blue-400",
  fidelity: "text-purple-400",
};

const TX_TYPE_COLORS: Record<string, string> = {
  buy: "text-green-400",
  sell: "text-red-400",
  dividend: "text-yellow-400",
  contribution: "text-blue-400",
  transfer: "text-white/50",
  deposit: "text-green-300",
  withdrawal: "text-red-300",
  fee: "text-orange-400",
  other: "text-white/40",
};

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

function fmtPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

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
      setSummary(s);
      setHoldings(h.holdings);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/investments/upload`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (data.status === "success") {
        setUploadMsg(`Imported ${data.transactions_stored} transactions, ${data.holdings_stored} holdings from ${data.broker}`);
        load();
      } else {
        setUploadMsg(`Import failed: ${data.reason}`);
      }
    } catch {
      setUploadMsg("Upload failed — check backend connection.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const filteredHoldings = selectedBroker
    ? holdings.filter(h => h.broker === selectedBroker)
    : holdings;

  const unrealizedGain = holdings.reduce((acc, h) => acc + (h.gain_loss ?? 0), 0);
  const gainPositive = unrealizedGain >= 0;

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-5 animate-pulse h-32" />
        ))}
      </div>
    );
  }

  const hasData = summary && (summary.portfolio_value > 0 || summary.accounts.length > 0);

  return (
    <section className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp size={18} className="text-blue-400" />
          <h2 className="font-semibold text-white text-lg">Investment Portfolio</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="p-2 text-white/40 hover:text-white/70 transition-colors rounded-lg hover:bg-white/10"
          >
            <RefreshCw size={14} />
          </button>
          <label className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors cursor-pointer",
            uploading
              ? "bg-blue-600/50 text-white/50"
              : "bg-blue-600 hover:bg-blue-500 text-white"
          )}>
            <Upload size={13} />
            {uploading ? "Uploading…" : "Upload Statement"}
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {uploadMsg && (
        <div className={cn(
          "rounded-lg px-4 py-3 text-sm border",
          uploadMsg.includes("failed") || uploadMsg.includes("Failed")
            ? "bg-red-500/10 border-red-500/30 text-red-300"
            : "bg-green-500/10 border-green-500/30 text-green-300"
        )}>
          {uploadMsg}
        </div>
      )}

      {!hasData ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-10 text-center">
          <TrendingUp size={32} className="text-white/20 mx-auto mb-3" />
          <p className="text-white/50 text-sm">No investment data yet.</p>
          <p className="text-white/30 text-xs mt-1">Upload a Robinhood, Schwab, or Fidelity statement to get started.</p>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs text-white/40 mb-1">Portfolio Value</p>
              <p className="text-2xl font-bold text-white">{fmt(summary!.portfolio_value)}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs text-white/40 mb-1">Total Invested</p>
              <p className="text-2xl font-bold text-white">{fmt(summary!.total_invested)}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs text-white/40 mb-1">Unrealized Gain/Loss</p>
              <div className="flex items-center gap-1">
                {gainPositive
                  ? <ArrowUpRight size={16} className="text-green-400" />
                  : <ArrowDownRight size={16} className="text-red-400" />}
                <p className={cn("text-2xl font-bold", gainPositive ? "text-green-400" : "text-red-400")}>
                  {fmt(Math.abs(unrealizedGain))}
                </p>
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs text-white/40 mb-1">Dividends Received</p>
              <p className="text-2xl font-bold text-yellow-400">{fmt(summary!.total_dividends)}</p>
            </div>
          </div>

          {/* Account breakdown */}
          {summary!.accounts.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <div className="flex items-center gap-2 mb-4">
                <PieChart size={15} className="text-blue-400" />
                <h3 className="font-semibold text-white text-sm">By Account</h3>
              </div>
              <div className="space-y-3">
                {summary!.accounts.map((acc, i) => {
                  const pct = summary!.portfolio_value > 0
                    ? (acc.total_value / summary!.portfolio_value) * 100
                    : 0;
                  return (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setSelectedBroker(selectedBroker === acc.broker ? null : acc.broker)}
                            className={cn(
                              "text-xs font-medium transition-colors",
                              BROKER_COLORS[acc.broker] ?? "text-white/60",
                              selectedBroker === acc.broker && "underline"
                            )}
                          >
                            {BROKER_LABELS[acc.broker] ?? acc.broker}
                          </button>
                          <span className="text-xs text-white/30">{acc.positions} positions</span>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-medium text-white">{fmt(acc.total_value)}</span>
                          <span className="text-xs text-white/30 ml-2">{pct.toFixed(1)}%</span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all", {
                            "bg-green-500": acc.broker === "robinhood",
                            "bg-blue-500": acc.broker === "schwab",
                            "bg-purple-500": acc.broker === "fidelity",
                          })}
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
            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-white text-sm">
                  Holdings {selectedBroker && (
                    <span className={cn("text-xs ml-1", BROKER_COLORS[selectedBroker])}>
                      · {BROKER_LABELS[selectedBroker] ?? selectedBroker}
                    </span>
                  )}
                </h3>
                {selectedBroker && (
                  <button
                    onClick={() => setSelectedBroker(null)}
                    className="text-xs text-white/30 hover:text-white/60"
                  >
                    Show all
                  </button>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-white/30 border-b border-white/10">
                      <th className="text-left pb-2 font-medium">Ticker</th>
                      <th className="text-left pb-2 font-medium">Name</th>
                      <th className="text-right pb-2 font-medium">Qty</th>
                      <th className="text-right pb-2 font-medium">Price</th>
                      <th className="text-right pb-2 font-medium">Value</th>
                      <th className="text-right pb-2 font-medium">Gain/Loss</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {filteredHoldings.map(h => (
                      <tr key={h.id} className="hover:bg-white/5 transition-colors">
                        <td className="py-2.5 font-mono text-xs text-blue-300">{h.ticker ?? "—"}</td>
                        <td className="py-2.5 text-white/70 max-w-[180px] truncate">{h.name}</td>
                        <td className="py-2.5 text-right text-white/50 text-xs">
                          {h.quantity != null ? h.quantity.toLocaleString() : "—"}
                        </td>
                        <td className="py-2.5 text-right text-white/50 text-xs">
                          {h.price != null ? fmt(h.price) : "—"}
                        </td>
                        <td className="py-2.5 text-right font-medium text-white">{fmt(h.total_value)}</td>
                        <td className="py-2.5 text-right">
                          {h.gain_loss != null ? (
                            <span className={h.gain_loss >= 0 ? "text-green-400" : "text-red-400"}>
                              {fmt(h.gain_loss)}
                              {h.gain_loss_pct != null && (
                                <span className="text-xs ml-1 opacity-70">({fmtPct(h.gain_loss_pct)})</span>
                              )}
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

          {/* Recent transactions */}
          {summary!.recent_transactions.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-white/5 p-5">
              <h3 className="font-semibold text-white text-sm mb-4">Recent Activity</h3>
              <div className="space-y-2">
                {summary!.recent_transactions.map(tx => (
                  <div key={tx.id} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                    <div className="flex items-center gap-3">
                      <span className={cn("text-xs font-medium uppercase tracking-wide w-20",
                        TX_TYPE_COLORS[tx.transaction_type] ?? "text-white/40")}>
                        {tx.transaction_type}
                      </span>
                      <div>
                        <p className="text-sm text-white">
                          {tx.ticker && <span className="font-mono text-blue-300 mr-1">{tx.ticker}</span>}
                          {tx.name && <span className="text-white/70">{tx.name}</span>}
                          {!tx.ticker && !tx.name && <span className="text-white/40">—</span>}
                        </p>
                        <p className="text-xs text-white/30">
                          {tx.date} · {BROKER_LABELS[tx.broker] ?? tx.broker}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-white">{fmt(tx.total_value)}</p>
                      {tx.quantity != null && (
                        <p className="text-xs text-white/30">{tx.quantity} shares</p>
                      )}
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
