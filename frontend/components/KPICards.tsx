"use client";
import { useMemo, useEffect, useState } from "react";
import {
  ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown,
  Building2, CreditCard, BarChart3, PiggyBank, Scale,
} from "lucide-react";
import { Transaction, getAccountsSummary, AccountsSummary } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface Props {
  transactions: Transaction[];
  allTxns: Transaction[];
  onDrillDown: (label: string, txns: Transaction[]) => void;
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const w = 56, h = 24, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v / max) * (h - pad * 2));
    return `${x},${y}`;
  }).join(" ");
  const last = pts.split(" ").at(-1)!.split(",");
  return (
    <svg width={w} height={h} className="shrink-0 opacity-60">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
    </svg>
  );
}

function KPICard({
  label, value, sub, icon, iconBg, border, accent, sparkData, sparkColor, onClick, isLoading,
}: {
  label: string; value: string; sub: string;
  icon: React.ReactNode; iconBg: string; border: string; accent: string;
  sparkData?: number[]; sparkColor?: string;
  onClick?: () => void; isLoading?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group rounded-2xl border bg-surface p-4 text-left transition-all duration-200",
        "hover:shadow-xl hover:-translate-y-0.5",
        border
      )}
    >
      <div className="flex items-start justify-between mb-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-tx-2">{label}</span>
        <span className={cn("w-7 h-7 rounded-xl flex items-center justify-center shrink-0", iconBg)}>
          {icon}
        </span>
      </div>
      {isLoading ? (
        <div className="h-7 w-24 bg-elevated rounded animate-pulse mb-1" />
      ) : (
        <p className="text-xl font-bold text-tx tracking-tight leading-none mb-1">{value}</p>
      )}
      <p className={cn("text-[11px] mb-2", accent)}>{sub}</p>
      {sparkData && sparkColor && (
        <div className="flex items-end justify-between">
          <p className="text-[10px] text-tx-3 opacity-0 group-hover:opacity-100 transition-opacity">
            Tap to explore →
          </p>
          <Sparkline data={sparkData} color={sparkColor} />
        </div>
      )}
    </button>
  );
}

export default function KPICards({ transactions, allTxns, onDrillDown }: Props) {
  const [accounts, setAccounts] = useState<AccountsSummary | null>(null);
  const [acctLoading, setAcctLoading] = useState(true);

  useEffect(() => {
    setAcctLoading(true);
    getAccountsSummary()
      .then(setAccounts)
      .catch(() => setAccounts(null))
      .finally(() => setAcctLoading(false));
  }, []);

  const m = useMemo(() => {
    const credits = transactions.filter(t => t.transaction_type === "credit");
    const debits  = transactions.filter(t => t.transaction_type === "debit");
    const income   = credits.reduce((s, t) => s + t.amount, 0);
    const expenses = debits.reduce((s, t)  => s + t.amount, 0);
    return { credits, debits, income, expenses };
  }, [transactions]);

  // Weekly sparklines from allTxns
  const weekly = useMemo(() => {
    const now = new Date();
    return Array.from({ length: 5 }, (_, i) => {
      const end = new Date(now); end.setDate(now.getDate() - i * 7);
      const start = new Date(end); start.setDate(end.getDate() - 7);
      const week = allTxns.filter(t => { const d = new Date(t.date); return d >= start && d < end; });
      return {
        income:   week.filter(t => t.transaction_type === "credit").reduce((s, t) => s + t.amount, 0),
        expenses: week.filter(t => t.transaction_type === "debit").reduce((s, t) => s + t.amount, 0),
      };
    }).reverse();
  }, [allTxns]);

  const expSparkline = weekly.map(w => w.expenses);
  const incSparkline = weekly.map(w => w.income);

  const nw = accounts?.net_worth ?? 0;
  const nwPositive = nw >= 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
      {/* Income */}
      <KPICard
        label="Income"
        value={formatCurrency(m.income)}
        sub={`${m.credits.length} credit${m.credits.length !== 1 ? "s" : ""}`}
        icon={<ArrowUpRight size={14} className="text-income" />}
        iconBg="bg-income/10"
        border="border-income/20 hover:border-income/40"
        accent="text-income"
        sparkData={incSparkline}
        sparkColor="var(--color-income, #22c55e)"
        onClick={() => onDrillDown("Income", m.credits)}
      />

      {/* Expenses */}
      <KPICard
        label="Expenses"
        value={formatCurrency(m.expenses)}
        sub={`${m.debits.length} debit${m.debits.length !== 1 ? "s" : ""}`}
        icon={<ArrowDownRight size={14} className="text-expense" />}
        iconBg="bg-expense/10"
        border="border-expense/20 hover:border-expense/40"
        accent="text-expense"
        sparkData={expSparkline}
        sparkColor="var(--color-expense, #ef4444)"
        onClick={() => onDrillDown("Expenses", m.debits)}
      />

      {/* Bank Balance */}
      <KPICard
        label="Bank Balance"
        value={accounts ? formatCurrency(accounts.bank_balance) : "—"}
        sub="checking + savings"
        icon={<Building2 size={14} className="text-accent" />}
        iconBg="bg-accent/10"
        border="border-accent/20 hover:border-accent/40"
        accent="text-accent"
        isLoading={acctLoading}
        onClick={() => {}}
      />

      {/* CC Balance */}
      <KPICard
        label="CC Balance"
        value={accounts ? formatCurrency(accounts.cc_balance) : "—"}
        sub="total owed"
        icon={<CreditCard size={14} className={accounts && accounts.cc_balance > 5000 ? "text-expense" : "text-warn"} />}
        iconBg={accounts && accounts.cc_balance > 5000 ? "bg-expense/10" : "bg-warn/10"}
        border={accounts && accounts.cc_balance > 5000 ? "border-expense/20 hover:border-expense/40" : "border-warn/20 hover:border-warn/40"}
        accent={accounts && accounts.cc_balance > 5000 ? "text-expense" : "text-warn"}
        isLoading={acctLoading}
        onClick={() => {}}
      />

      {/* 401K */}
      <KPICard
        label="401K (Fidelity)"
        value={accounts ? formatCurrency(accounts.portfolio_401k) : "—"}
        sub="retirement"
        icon={<PiggyBank size={14} className="text-income" />}
        iconBg="bg-income/10"
        border="border-income/20 hover:border-income/40"
        accent="text-income"
        isLoading={acctLoading}
        onClick={() => {}}
      />

      {/* Stocks */}
      <KPICard
        label="Stocks"
        value={accounts ? formatCurrency(accounts.portfolio_stocks) : "—"}
        sub="Robinhood · Schwab"
        icon={<BarChart3 size={14} className="text-accent" />}
        iconBg="bg-accent/10"
        border="border-accent/20 hover:border-accent/40"
        accent="text-accent"
        isLoading={acctLoading}
        onClick={() => {}}
      />

      {/* Net Worth */}
      <KPICard
        label="Net Worth"
        value={accounts ? formatCurrency(Math.abs(nw)) : "—"}
        sub={nwPositive ? "bank + investments" : "net negative"}
        icon={nwPositive
          ? <TrendingUp size={14} className="text-income" />
          : <TrendingDown size={14} className="text-expense" />
        }
        iconBg={nwPositive ? "bg-income/10" : "bg-expense/10"}
        border={nwPositive ? "border-income/20 hover:border-income/40" : "border-expense/20 hover:border-expense/40"}
        accent={nwPositive ? "text-income" : "text-expense"}
        isLoading={acctLoading}
        onClick={() => {}}
      />
    </div>
  );
}
