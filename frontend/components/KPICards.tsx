"use client";
import { useMemo } from "react";
import { ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown, Percent } from "lucide-react";
import { Transaction } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface Props {
  transactions: Transaction[];
  allTxns: Transaction[];
  onDrillDown: (label: string, txns: Transaction[]) => void;
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const w = 60, h = 28, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v / max) * (h - pad * 2));
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={w} height={h} className="shrink-0 opacity-60">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts.split(" ").at(-1)!.split(",")[0]} cy={pts.split(" ").at(-1)!.split(",")[1]} r="2" fill={color} />
    </svg>
  );
}

export default function KPICards({ transactions, allTxns, onDrillDown }: Props) {
  const m = useMemo(() => {
    const credits = transactions.filter(t => t.transaction_type === "credit");
    const debits  = transactions.filter(t => t.transaction_type === "debit");
    const income   = credits.reduce((s, t) => s + t.amount, 0);
    const expenses = debits.reduce((s, t)  => s + t.amount, 0);
    const savings  = income - expenses;
    const rate     = income > 0 ? (savings / income) * 100 : 0;
    return { credits, debits, income, expenses, savings, rate, all: transactions };
  }, [transactions]);

  // Weekly totals for sparklines — last 5 weeks from allTxns
  const weekly = useMemo(() => {
    const now = new Date();
    return Array.from({ length: 5 }, (_, i) => {
      const end = new Date(now); end.setDate(now.getDate() - i * 7);
      const start = new Date(end); start.setDate(end.getDate() - 7);
      const week = allTxns.filter(t => { const d = new Date(t.date); return d >= start && d < end; });
      return {
        income:   week.filter(t => t.transaction_type === "credit").reduce((s, t) => s + t.amount, 0),
        expenses: week.filter(t => t.transaction_type === "debit").reduce((s,  t) => s + t.amount, 0),
      };
    }).reverse();
  }, [allTxns]);

  if (transactions.length === 0) return <KPISkeleton />;

  const expSparkline  = weekly.map(w => w.expenses);
  const incSparkline  = weekly.map(w => w.income);
  const savSparkline  = weekly.map(w => Math.max(w.income - w.expenses, 0));
  const rateSparkline = weekly.map(w => w.income > 0 ? (Math.max(w.income - w.expenses, 0) / w.income) * 100 : 0);

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
      sparkData: incSparkline,
      sparkColor: "var(--color-income, #22c55e)",
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
      sparkData: expSparkline,
      sparkColor: "var(--color-expense, #ef4444)",
    },
    {
      label: "Net Savings",
      value: formatCurrency(Math.abs(m.savings)),
      sub: m.savings >= 0 ? "net surplus" : "net deficit",
      icon: m.savings >= 0
        ? <TrendingUp size={16} className="text-savings" />
        : <TrendingDown size={16} className="text-expense" />,
      iconBg: m.savings >= 0 ? "bg-savings/10" : "bg-expense/10",
      border: m.savings >= 0 ? "border-savings/20 hover:border-savings/40" : "border-expense/20 hover:border-expense/40",
      accent: m.savings >= 0 ? "text-savings" : "text-expense",
      txns: m.all,
      sparkData: savSparkline,
      sparkColor: "var(--color-savings, #3b82f6)",
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
      sparkData: rateSparkline,
      sparkColor: m.rate >= 20 ? "var(--color-income, #22c55e)" : "var(--color-warn, #f59e0b)",
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
          <div className="flex items-start justify-between mb-3">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-tx-2">{c.label}</span>
            <span className={cn("w-8 h-8 rounded-xl flex items-center justify-center shrink-0", c.iconBg)}>
              {c.icon}
            </span>
          </div>
          <p className="text-2xl font-bold text-tx tracking-tight leading-none mb-1">{c.value}</p>
          <p className={cn("text-xs mb-3", c.accent)}>{c.sub}</p>
          <div className="flex items-end justify-between">
            <p className="text-[10px] text-tx-3 opacity-0 group-hover:opacity-100 transition-opacity">
              Tap to explore →
            </p>
            <Sparkline data={c.sparkData} color={c.sparkColor} />
          </div>
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
