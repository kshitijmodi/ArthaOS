"use client";
import { useMemo, useEffect, useState } from "react";
import {
  ArrowUpRight, ArrowDownRight,
  Building2, CreditCard, BarChart3, PiggyBank, Scale, Car,
} from "lucide-react";
import { Transaction, getAccountsSummary, AccountsSummary } from "@/lib/api";
import { KPIDrillType } from "@/components/KPIDrillPanel";
import { formatCurrency, cn } from "@/lib/utils";

interface Props {
  transactions: Transaction[];
  allTxns: Transaction[];
  onDrillDown: (label: string, txns: Transaction[]) => void;
  onKPIDrillDown: (type: KPIDrillType) => void;
  /** End-of-period ISO date — only used for income/expenses context, NOT for balances */
  asOf?: string;
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

function Card({
  label, value, sub, icon, iconBg, border, accent,
  sparkData, sparkColor, onClick, loading,
}: {
  label: string; value: string; sub: string;
  icon: React.ReactNode; iconBg: string; border: string; accent: string;
  sparkData?: number[]; sparkColor?: string;
  onClick?: () => void; loading?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group rounded-2xl border bg-surface p-4 text-left transition-all duration-200",
        "hover:shadow-lg hover:-translate-y-0.5",
        border
      )}
    >
      <div className="flex items-start justify-between mb-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-tx-2 truncate">{label}</span>
        <span className={cn("w-7 h-7 rounded-xl flex items-center justify-center shrink-0 ml-1", iconBg)}>
          {icon}
        </span>
      </div>
      {loading ? (
        <div className="h-6 w-20 bg-elevated rounded animate-pulse mb-1" />
      ) : (
        <p className="text-xl font-bold text-tx tracking-tight leading-none mb-1">{value}</p>
      )}
      <p className={cn("text-[11px] mb-2", accent)}>{sub}</p>
      {sparkData && sparkColor && (
        <div className="flex items-end justify-between">
          <p className="text-[10px] text-tx-3 opacity-0 group-hover:opacity-100 transition-opacity">Tap →</p>
          <Sparkline data={sparkData} color={sparkColor} />
        </div>
      )}
    </button>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-widest text-tx-3">{children}</span>
      <div className="flex-1 h-px bg-border/50" />
    </div>
  );
}

export default function KPICards({ transactions, allTxns, onDrillDown, onKPIDrillDown, asOf }: Props) {
  const [accounts, setAccounts] = useState<AccountsSummary | null>(null);
  const [acctLoading, setAcctLoading] = useState(true);

  useEffect(() => {
    // Always fetch current balances — period filter only applies to income/expenses
    setAcctLoading(true);
    getAccountsSummary()
      .then(setAccounts)
      .catch(() => setAccounts(null))
      .finally(() => setAcctLoading(false));
  }, []);

  const NON_EXPENSE_CATS = new Set(["Income", "Investments", "Transfer", "Fees & Interest"]);

  const m = useMemo(() => {
    const incomes = transactions.filter(t => t.category === "Income");
    const debits  = transactions.filter(t => t.transaction_type === "debit" && !NON_EXPENSE_CATS.has(t.category));
    return {
      incomes, debits,
      income:   incomes.reduce((s, t) => s + t.amount, 0),
      expenses: debits.reduce((s, t)  => s + t.amount, 0),
    };
  }, [transactions]);

  const weekly = useMemo(() => {
    const now = new Date();
    return Array.from({ length: 5 }, (_, i) => {
      const end = new Date(now); end.setDate(now.getDate() - i * 7);
      const start = new Date(end); start.setDate(end.getDate() - 7);
      const week = allTxns.filter(t => { const d = new Date(t.date); return d >= start && d < end; });
      return {
        income:   week.filter(t => t.category === "Income").reduce((s, t) => s + t.amount, 0),
        expenses: week.filter(t => t.transaction_type === "debit" && !NON_EXPENSE_CATS.has(t.category)).reduce((s, t) => s + t.amount, 0),
      };
    }).reverse();
  }, [allTxns]);

  const nw = accounts?.net_worth ?? 0;
  const ccOwed = Math.abs(accounts?.cc_balance ?? 0);
  const ccHigh = ccOwed > 5000;
  const hasLoans = (accounts?.loan_balance ?? 0) < 0;  // loan_balance is negative when owing
  const isPeriod = !!asOf;

  return (
    <div className="space-y-3">
      {/* Row 1 — period-filtered: Income, Expenses, Bank Balance, CC Balance */}
      <SectionLabel>This period</SectionLabel>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card
          label="Income" value={formatCurrency(m.income)}
          sub={`${m.incomes.length} direct deposit${m.incomes.length !== 1 ? "s" : ""}`}
          icon={<ArrowUpRight size={14} className="text-income" />}
          iconBg="bg-income/10" border="border-income/20 hover:border-income/40" accent="text-income"
          sparkData={weekly.map(w => w.income)} sparkColor="var(--color-income, #22c55e)"
          onClick={() => onDrillDown("Income", m.incomes)}
        />
        <Card
          label="Expenses" value={formatCurrency(m.expenses)}
          sub={`${m.debits.length} debit${m.debits.length !== 1 ? "s" : ""}`}
          icon={<ArrowDownRight size={14} className="text-expense" />}
          iconBg="bg-expense/10" border="border-expense/20 hover:border-expense/40" accent="text-expense"
          sparkData={weekly.map(w => w.expenses)} sparkColor="var(--color-expense, #ef4444)"
          onClick={() => onDrillDown("Expenses", m.debits)}
        />
        <Card
          label="Bank Balance"
          value={accounts ? formatCurrency(accounts.bank_balance) : "—"}
          sub="current"
          icon={<Building2 size={14} className="text-accent" />}
          iconBg="bg-accent/10" border="border-accent/20 hover:border-accent/40" accent="text-accent"
          loading={acctLoading}
          onClick={() => onKPIDrillDown("bank")}
        />
        <Card
          label="CC Balance"
          value={accounts ? formatCurrency(accounts.cc_balance) : "—"}
          sub="total owed"
          icon={<CreditCard size={14} className={ccHigh ? "text-expense" : "text-warn"} />}
          iconBg={ccHigh ? "bg-expense/10" : "bg-warn/10"}
          border={ccHigh ? "border-expense/20 hover:border-expense/40" : "border-warn/20 hover:border-warn/40"}
          accent={ccHigh ? "text-expense" : "text-warn"}
          loading={acctLoading}
          onClick={() => onKPIDrillDown("cc")}
        />
      </div>

      {/* Loans row — only shown when a loan account is connected */}
      {hasLoans && (
        <>
          <SectionLabel>Liabilities</SectionLabel>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Card
              label="Loans Outstanding"
              value={accounts ? formatCurrency(accounts.loan_balance) : "—"}
              sub="auto · mortgage · personal"
              icon={<Car size={14} className="text-expense" />}
              iconBg="bg-expense/10" border="border-expense/20 hover:border-expense/40" accent="text-expense"
              loading={acctLoading}
            />
          </div>
        </>
      )}

      {/* Row 2 — portfolio snapshot (not period-filtered) */}
      <SectionLabel>Portfolio snapshot</SectionLabel>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card
          label="401K · Fidelity" value={accounts ? formatCurrency(accounts.portfolio_401k) : "—"}
          sub="retirement · latest"
          icon={<PiggyBank size={14} className="text-income" />}
          iconBg="bg-income/10" border="border-income/20 hover:border-income/40" accent="text-income"
          loading={acctLoading}
          onClick={() => onKPIDrillDown("401k")}
        />
        <Card
          label="Stocks" value={accounts ? formatCurrency(accounts.portfolio_stocks) : "—"}
          sub="Robinhood · Schwab · latest"
          icon={<BarChart3 size={14} className="text-savings" />}
          iconBg="bg-savings/10" border="border-savings/20 hover:border-savings/40" accent="text-savings"
          loading={acctLoading}
          onClick={() => onKPIDrillDown("stocks")}
        />
        <Card
          label="Net Worth" value={accounts ? formatCurrency(Math.abs(nw)) : "—"}
          sub={nw >= 0 ? "assets – liabilities" : "net negative"}
          icon={<Scale size={14} className={nw >= 0 ? "text-income" : "text-expense"} />}
          iconBg={nw >= 0 ? "bg-income/10" : "bg-expense/10"}
          border={nw >= 0 ? "border-income/20 hover:border-income/40" : "border-expense/20 hover:border-expense/40"}
          accent={nw >= 0 ? "text-income" : "text-expense"}
          loading={acctLoading}
          onClick={() => onKPIDrillDown("networth")}
        />
      </div>
    </div>
  );
}
