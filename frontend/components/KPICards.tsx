"use client";
import { useMemo } from "react";
import { ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown, Percent } from "lucide-react";
import { Transaction } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface Props {
  transactions: Transaction[];
  onDrillDown: (label: string, txns: Transaction[]) => void;
}

export default function KPICards({ transactions, onDrillDown }: Props) {
  const m = useMemo(() => {
    const credits = transactions.filter(t => t.transaction_type === "credit");
    const debits  = transactions.filter(t => t.transaction_type === "debit");
    const income   = credits.reduce((s, t) => s + t.amount, 0);
    const expenses = debits.reduce((s, t) => s + t.amount, 0);
    const savings  = income - expenses;
    const rate     = income > 0 ? (savings / income) * 100 : 0;
    return { credits, debits, income, expenses, savings, rate, all: transactions };
  }, [transactions]);

  if (transactions.length === 0) return <KPISkeleton />;

  const cards = [
    {
      label: "Income",
      value: formatCurrency(m.income),
      sub: `${m.credits.length} credit${m.credits.length !== 1 ? "s" : ""}`,
      icon: <ArrowUpRight size={16} className="text-income" />,
      iconBg: "bg-income/10",
      border: "border-income/20 hover:border-income/40",
      accent: "text-income",
      txns: m.credits,
    },
    {
      label: "Expenses",
      value: formatCurrency(m.expenses),
      sub: `${m.debits.length} debit${m.debits.length !== 1 ? "s" : ""}`,
      icon: <ArrowDownRight size={16} className="text-expense" />,
      iconBg: "bg-expense/10",
      border: "border-expense/20 hover:border-expense/40",
      accent: "text-expense",
      txns: m.debits,
    },
    {
      label: "Savings",
      value: formatCurrency(Math.abs(m.savings)),
      sub: m.savings >= 0 ? "net surplus" : "net deficit",
      icon: m.savings >= 0
        ? <TrendingUp size={16} className="text-savings" />
        : <TrendingDown size={16} className="text-expense" />,
      iconBg: m.savings >= 0 ? "bg-savings/10" : "bg-expense/10",
      border: m.savings >= 0 ? "border-savings/20 hover:border-savings/40" : "border-expense/20 hover:border-expense/40",
      accent: m.savings >= 0 ? "text-savings" : "text-expense",
      txns: m.all,
    },
    {
      label: "Savings Rate",
      value: `${Math.abs(m.rate).toFixed(1)}%`,
      sub: m.rate >= 20 ? "healthy rate" : m.rate >= 0 ? "room to improve" : "deficit",
      icon: <Percent size={16} className={m.rate >= 20 ? "text-income" : m.rate >= 0 ? "text-warn" : "text-expense"} />,
      iconBg: m.rate >= 20 ? "bg-income/10" : m.rate >= 0 ? "bg-warn/10" : "bg-expense/10",
      border: m.rate >= 20 ? "border-income/20 hover:border-income/40" : "border-warn/20 hover:border-warn/40",
      accent: m.rate >= 20 ? "text-income" : m.rate >= 0 ? "text-warn" : "text-expense",
      txns: m.all,
    },
  ];

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      {cards.map(c => (
        <button
          key={c.label}
          onClick={() => onDrillDown(c.label, c.txns)}
          className={cn(
            "group rounded-2xl border bg-surface p-5 text-left transition-all duration-200",
            "hover:shadow-xl hover:-translate-y-0.5",
            c.border
          )}
        >
          <div className="flex items-start justify-between mb-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-tx-2">{c.label}</span>
            <span className={cn("w-8 h-8 rounded-xl flex items-center justify-center", c.iconBg)}>
              {c.icon}
            </span>
          </div>
          <p className="text-2xl font-bold text-tx tracking-tight leading-none mb-2">{c.value}</p>
          <p className={cn("text-xs", c.accent)}>{c.sub}</p>
          <p className="text-[10px] text-tx-3 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
            Tap to explore →
          </p>
        </button>
      ))}
    </div>
  );
}

function KPISkeleton() {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="rounded-2xl border border-border bg-surface p-5 animate-pulse">
          <div className="flex justify-between mb-4">
            <div className="h-3 w-20 bg-elevated rounded" />
            <div className="w-8 h-8 bg-elevated rounded-xl" />
          </div>
          <div className="h-7 w-28 bg-elevated rounded mb-2" />
          <div className="h-3 w-24 bg-elevated rounded" />
        </div>
      ))}
    </div>
  );
}
