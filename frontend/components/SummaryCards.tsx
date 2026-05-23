"use client";
import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, Tag, Hash, CalendarClock } from "lucide-react";
import { getSummary, DashboardSummary } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

export default function SummaryCards() {
  const [data, setData] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    getSummary().then(setData).catch(console.error);
  }, []);

  if (!data) return <CardSkeleton />;

  const isUp = data.delta >= 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        icon={isUp ? <TrendingUp size={16} className="text-red-400" /> : <TrendingDown size={16} className="text-green-400" />}
        label="This Month"
        value={formatCurrency(data.this_month_spend)}
        sub={`${isUp ? "+" : ""}${data.delta_pct}% vs last month`}
        subColor={isUp ? "text-red-400" : "text-green-400"}
      />
      <Card
        icon={<Tag size={16} className="text-purple-400" />}
        label="Top Category"
        value={data.top_category ?? "—"}
        sub="highest spend"
        subColor="text-white/40"
      />
      <Card
        icon={<Hash size={16} className="text-blue-400" />}
        label="Transactions"
        value={String(data.transaction_count)}
        sub="this month"
        subColor="text-white/40"
      />
      <Card
        icon={<CalendarClock size={16} className="text-amber-400" />}
        label="Upcoming"
        value={`${data.upcoming_charges.length} charges`}
        sub={data.upcoming_charges[0]?.description ?? ""}
        subColor="text-white/40"
      />
    </div>
  );
}

function Card({ icon, label, value, sub, subColor }: {
  icon: React.ReactNode; label: string; value: string; sub: string; subColor: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-white/50 uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-xl font-bold text-white truncate">{value}</p>
      <p className={cn("text-xs mt-1 truncate", subColor)}>{sub}</p>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {[1,2,3,4].map(i => (
        <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4 animate-pulse">
          <div className="h-3 bg-white/10 rounded w-16 mb-3" />
          <div className="h-6 bg-white/10 rounded w-24 mb-2" />
          <div className="h-3 bg-white/10 rounded w-20" />
        </div>
      ))}
    </div>
  );
}
