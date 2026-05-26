"use client";
import { useMemo } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { Transaction } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface Props { transactions: Transaction[] }

interface Bucket { month: string; income: number; expenses: number; savings: number }

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface border border-border rounded-xl px-4 py-3 shadow-2xl text-xs space-y-1.5 min-w-[160px]">
      <p className="font-semibold text-tx mb-2 pb-2 border-b border-border">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
            <span className="text-tx-2 capitalize">{p.name}</span>
          </div>
          <span className="font-semibold text-tx tabular-nums">{formatCurrency(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function CashFlowChart({ transactions }: Props) {
  const data = useMemo<Bucket[]>(() => {
    const map = new Map<string, { income: number; expenses: number }>();
    transactions.forEach(t => {
      const month = t.date.slice(0, 7);
      if (!map.has(month)) map.set(month, { income: 0, expenses: 0 });
      const e = map.get(month)!;
      if (t.transaction_type === "credit") e.income += t.amount;
      else e.expenses += t.amount;
    });
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-6)
      .map(([month, v]) => ({
        month: new Date(month + "-01").toLocaleDateString("en-US", { month: "short", year: "2-digit" }),
        income:   Math.round(v.income),
        expenses: Math.round(v.expenses),
        savings:  Math.round(v.income - v.expenses),
      }));
  }, [transactions]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-52 text-sm text-tx-2">
        No data yet — ingest some statements first
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="gIncome" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gExpense" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#f43f5e" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gSavings" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgb(var(--c-border))" strokeOpacity={0.35} vertical={false} />
        <XAxis dataKey="month" tick={{ fill: "rgb(var(--c-text2))", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis
          tick={{ fill: "rgb(var(--c-text2))", fontSize: 11 }}
          axisLine={false} tickLine={false}
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          width={42}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "rgb(var(--c-text2))", paddingTop: "10px" }}
          formatter={v => <span style={{ textTransform: "capitalize" }}>{v}</span>}
        />
        <Area type="monotone" dataKey="income"   name="income"   stroke="#10b981" fill="url(#gIncome)"  strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="expenses" name="expenses" stroke="#f43f5e" fill="url(#gExpense)" strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="savings"  name="savings"  stroke="#3b82f6" fill="url(#gSavings)" strokeWidth={2} dot={false} strokeDasharray="4 2" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
