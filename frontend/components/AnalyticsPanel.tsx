"use client";
import { useEffect, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { apiFetch } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

const CHART_COLORS = [
  "#3b82f6", "#8b5cf6", "#10b981", "#f59e0b",
  "#ef4444", "#06b6d4", "#ec4899", "#84cc16",
  "#f97316", "#6366f1", "#14b8a6", "#e879f9",
];

function CurrencyTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg px-3 py-2 text-xs">
      <p className="text-white/60 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

export default function AnalyticsPanel() {
  const [trend, setTrend] = useState<any[]>([]);
  const [breakdown, setBreakdown] = useState<any[]>([]);
  const [comparison, setComparison] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiFetch<{ data: any[] }>("/analytics/monthly-trend"),
      apiFetch<{ data: any[] }>("/analytics/category-breakdown"),
      apiFetch<{ data: any[] }>("/analytics/month-comparison"),
    ]).then(([t, b, c]) => {
      setTrend(t.data);
      setBreakdown(b.data);
      setComparison(c.data.slice(0, 8));
    }).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) return <AnalyticsSkeleton />;

  return (
    <section className="space-y-6">
      {/* Monthly spend trend */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h3 className="font-semibold text-white mb-4">Monthly Spend Trend</h3>
        {trend.length === 0 ? (
          <EmptyState />
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trend} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={{ fill: "#ffffff60", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#ffffff60", fontSize: 11 }} axisLine={false} tickLine={false}
                tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
              <Tooltip content={<CurrencyTooltip />} />
              <Area type="monotone" dataKey="total" name="Spend"
                stroke="#3b82f6" fill="url(#trendGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category breakdown donut */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-5">
          <h3 className="font-semibold text-white mb-4">This Month by Category</h3>
          {breakdown.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="flex gap-4 items-center">
              <ResponsiveContainer width="50%" height={200}>
                <PieChart>
                  <Pie data={breakdown} dataKey="total" nameKey="category"
                    cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {breakdown.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CurrencyTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <ul className="flex-1 space-y-1.5 text-xs">
                {breakdown.map((item, i) => (
                  <li key={item.category} className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                    <span className="text-white/60 truncate flex-1">{item.category}</span>
                    <span className="text-white/80 tabular-nums">{formatCurrency(item.total)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Month-over-month comparison bar */}
        <div className="rounded-xl border border-white/10 bg-white/5 p-5">
          <h3 className="font-semibold text-white mb-4">This vs Last Month</h3>
          {comparison.length === 0 ? (
            <EmptyState />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={comparison} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap="30%">
                <XAxis dataKey="category" tick={{ fill: "#ffffff60", fontSize: 10 }}
                  axisLine={false} tickLine={false} interval={0}
                  angle={-30} textAnchor="end" height={40} />
                <YAxis tick={{ fill: "#ffffff60", fontSize: 10 }} axisLine={false} tickLine={false}
                  tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip content={<CurrencyTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: "#ffffff80" }} />
                <Bar dataKey="last_month" name="Last month" fill="#6366f1" radius={[3,3,0,0]} />
                <Bar dataKey="this_month" name="This month" fill="#3b82f6" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </section>
  );
}

function EmptyState() {
  return <p className="text-sm text-white/30 py-8 text-center">No data yet — ingest some statements first</p>;
}

function AnalyticsSkeleton() {
  return (
    <section className="space-y-6 animate-pulse">
      <div className="rounded-xl border border-white/10 bg-white/5 p-5 h-64" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-white/10 bg-white/5 p-5 h-56" />
        <div className="rounded-xl border border-white/10 bg-white/5 p-5 h-56" />
      </div>
    </section>
  );
}
