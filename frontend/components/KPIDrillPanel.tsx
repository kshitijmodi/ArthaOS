"use client";
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { AccountsSummary, AccountsDetail, getAccountsDetail, getAccountsSummary, apiFetch } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

export type KPIDrillType = "bank" | "cc" | "401k" | "stocks" | "networth";

interface InvestmentAccount {
  broker: string; account: string; total_value: number; positions: number;
  gain_loss: number | null; gain_loss_day: number | null;
}
interface InvestmentTx {
  id: number; date: string; ticker: string | null; name: string | null;
  transaction_type: string; quantity: number | null; price_per_unit: number | null;
  total_value: number; account: string; broker: string;
}
interface InvestmentSummary {
  portfolio_value: number;
  accounts: InvestmentAccount[];
  recent_transactions: InvestmentTx[];
}

interface Props {
  type: KPIDrillType;
  onClose: () => void;
}

function fmt(n: number) {
  return formatCurrency(n);
}

function Row({ label, value, sub, bold }: { label: string; value: string; sub?: string; bold?: boolean }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border/60 last:border-0">
      <div>
        <p className={cn("text-sm text-tx", bold && "font-semibold")}>{label}</p>
        {sub && <p className="text-[11px] text-tx-3 mt-0.5">{sub}</p>}
      </div>
      <p className={cn("text-sm font-semibold tabular-nums", bold && "text-base")}>{value}</p>
    </div>
  );
}

function TxRow({ date, description, amount, type, balance }: {
  date: string; description: string; amount: number;
  type: string; balance: number;
}) {
  const isCredit = type === "credit";
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0 gap-3">
      <div className="shrink-0 w-20 text-[11px] text-tx-3">{date}</div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-tx truncate">{description}</p>
      </div>
      <div className={cn("text-xs font-semibold shrink-0", isCredit ? "text-income" : "text-expense")}>
        {isCredit ? "+" : "-"}{fmt(amount)}
      </div>
      <div className="text-xs text-tx-3 shrink-0 w-24 text-right tabular-nums">{fmt(balance)}</div>
    </div>
  );
}

export default function KPIDrillPanel({ type, onClose }: Props) {
  const [accounts, setAccounts] = useState<AccountsSummary | null>(null);
  const [detail, setDetail] = useState<AccountsDetail | null>(null);
  const [investments, setInvestments] = useState<InvestmentSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  useEffect(() => {
    setLoading(true);
    const fetches: Promise<void>[] = [
      getAccountsSummary().then(setAccounts).catch(() => {}),
      getAccountsDetail().then(setDetail).catch(() => {}),
    ];
    if (type === "401k" || type === "stocks") {
      fetches.push(
        apiFetch<InvestmentSummary>("/investments/summary").then(setInvestments).catch(() => {})
      );
    }
    Promise.all(fetches).finally(() => setLoading(false));
  }, [type]);

  const titles: Record<KPIDrillType, string> = {
    bank: "Bank Balance",
    cc: "Credit Card Balances",
    "401k": "401K · Fidelity",
    stocks: "Stock Accounts",
    networth: "Net Worth Breakdown",
  };

  // Compute running balance for bank transactions (approximate)
  const bankTxnsWithBalance = (() => {
    if (!detail || !accounts) return [];
    const txns = [...detail.recent_transactions].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    let running = accounts.bank_balance;
    return txns.map(t => {
      const bal = running;
      if (t.transaction_type === "debit")  running += t.amount;
      else                                  running -= t.amount;
      return { ...t, balance: bal };
    });
  })();

  return (
    <>
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40" onClick={onClose} />
      <aside className="fixed right-0 top-0 h-full w-full max-w-md bg-surface border-l border-border shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border shrink-0">
          <h2 className="font-bold text-tx text-lg">{titles[type]}</h2>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl hover:bg-elevated flex items-center justify-center text-tx-2 hover:text-tx transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading || !accounts ? (
            <div className="space-y-3 animate-pulse">
              {[1,2,3,4].map(i => <div key={i} className="h-12 bg-elevated rounded-xl" />)}
            </div>
          ) : (
            <>
              {/* BANK */}
              {type === "bank" && detail && (
                <div className="space-y-5">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Accounts</p>
                    {detail.bank_accounts.map((a, i) => (
                      <Row key={i} label={`${a.institution} — ${a.name}`} sub={a.subtype} value={fmt(a.balance)} />
                    ))}
                    <Row label="Total" value={fmt(accounts.bank_balance)} bold />
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Recent transactions</p>
                    <div className="flex items-center justify-between text-[10px] text-tx-3 pb-1 border-b border-border">
                      <span className="w-20">Date</span>
                      <span className="flex-1">Description</span>
                      <span>Amount</span>
                      <span className="w-24 text-right">Balance</span>
                    </div>
                    {bankTxnsWithBalance.map((t, i) => (
                      <TxRow key={i} date={t.date} description={t.description}
                        amount={t.amount} type={t.transaction_type} balance={t.balance} />
                    ))}
                  </div>
                </div>
              )}

              {/* CC */}
              {type === "cc" && detail && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Cards</p>
                  {detail.cc_accounts.map((a, i) => (
                    <Row key={i} label={`${a.institution} — ${a.name}`} sub={a.subtype} value={fmt(a.balance)} />
                  ))}
                  <Row label="Total owed" value={fmt(accounts.cc_balance)} bold />
                </div>
              )}

              {/* 401K */}
              {type === "401k" && investments && (
                <div className="space-y-5">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Account</p>
                    {investments.accounts
                      .filter(a => a.broker.toLowerCase().includes("fidelity"))
                      .map((a, i) => (
                        <Row key={i} label={a.account} sub={a.broker}
                          value={fmt(a.total_value)} />
                      ))}
                    <Row label="Total" value={fmt(accounts.portfolio_401k)} bold />
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Recent activity</p>
                    {investments.recent_transactions
                      .filter(t => t.broker.toLowerCase().includes("fidelity"))
                      .slice(0, 10)
                      .map((t, i) => (
                        <div key={i} className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0 gap-2">
                          <div className="shrink-0 w-20 text-[11px] text-tx-3">{t.date}</div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-tx truncate">{t.name ?? t.ticker ?? "—"}</p>
                            <p className="text-[10px] text-tx-3 capitalize">{t.transaction_type}</p>
                          </div>
                          {t.quantity && (
                            <p className="text-[11px] text-tx-3 shrink-0">{t.quantity} @ {fmt(t.price_per_unit ?? 0)}</p>
                          )}
                          <p className="text-xs font-semibold text-tx shrink-0">{fmt(t.total_value)}</p>
                        </div>
                      ))}
                    {investments.recent_transactions.filter(t => t.broker.toLowerCase().includes("fidelity")).length === 0 && (
                      <p className="text-sm text-tx-3 py-4 text-center">No recent transactions</p>
                    )}
                  </div>
                </div>
              )}

              {/* STOCKS */}
              {type === "stocks" && investments && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-2">Brokerage accounts</p>
                  {investments.accounts
                    .filter(a => !a.broker.toLowerCase().includes("fidelity"))
                    .map((a, i) => (
                      <Row key={i}
                        label={`${a.broker} — ${a.account}`}
                        sub={`${a.positions} position${a.positions !== 1 ? "s" : ""}`}
                        value={fmt(a.total_value)} />
                    ))}
                  <Row label="Total stocks" value={fmt(accounts.portfolio_stocks)} bold />
                </div>
              )}

              {/* NET WORTH */}
              {type === "networth" && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mb-3">Assets</p>
                  <Row label="Bank balance" value={fmt(accounts.bank_balance)} />
                  <Row label="401K (Fidelity)" value={fmt(accounts.portfolio_401k)} />
                  <Row label="Stocks (Robinhood · Schwab)" value={fmt(accounts.portfolio_stocks)} />

                  <p className="text-[11px] font-semibold uppercase tracking-wider text-tx-3 mt-4 mb-3">Liabilities</p>
                  <Row label="Credit cards" value={fmt(accounts.cc_balance)} />
                  {accounts.loan_balance < 0 && (
                    <Row label="Loans" value={fmt(accounts.loan_balance)} />
                  )}

                  <div className="mt-4 pt-4 border-t-2 border-border">
                    <div className="flex items-center justify-between">
                      <p className="font-bold text-tx">Net Worth</p>
                      <p className={cn(
                        "text-lg font-bold tabular-nums",
                        accounts.net_worth >= 0 ? "text-income" : "text-expense"
                      )}>
                        {accounts.net_worth < 0 ? "−" : ""}{fmt(Math.abs(accounts.net_worth))}
                      </p>
                    </div>
                    <p className="text-[11px] text-tx-3 mt-1">
                      {fmt(accounts.bank_balance)} + {fmt(accounts.portfolio_401k)} + {fmt(accounts.portfolio_stocks)} + {fmt(accounts.cc_balance)}{accounts.loan_balance < 0 ? ` + ${fmt(accounts.loan_balance)}` : ""}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
