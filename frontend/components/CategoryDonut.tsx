"use client";
import { useMemo, useState, useCallback } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { Transaction } from "@/lib/api";
import { formatCurrency, CHART_COLORS, cn } from "@/lib/utils";

interface Props {
  transactions: Transaction[];
  onDrillDown: (label: string, txns: Transaction[]) => void;
}

interface CatData { category: string; total: number; count: number; color: string; pct: number }

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as CatData;
  return (
    <div className="bg-surface border border-border rounded-xl px-4 py-3 shadow-2xl text-xs">
      <p className="font-semibold text-tx mb-1">{d.category}</p>
      <p className="text-tx-2">{formatCurrency(d.total)}</p>
      <p className="text-tx-3 mt-0.5">{d.count} transactions · {d.pct.toFixed(1)}%</p>
    </div>
  );
}

export default function CategoryDonut({ transactions, onDrillDown }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);

  const data = useMemo<CatData[]>(() => {
    const debits = transactions.filter(t => t.transaction_type === "debit");
    const map = new Map<string, { total: number; count: number }>();
    debits.forEach(t => {
      const cat = t.category || "Other";
      if (!map.has(cat)) map.set(cat, { total: 0, count: 0 });
      const e = map.get(cat)!;
      e.total += t.amount;
      e.count += 1;
    });
    const total = Array.from(map.values()).reduce((s, v) => s + v.total, 0);
    return Array.from(map.entries())
      .sort(([, a], [, b]) => b.total - a.total)
      .slice(0, 8)
      .map(([category, v], i) => ({
        category,
        ...v,
        color: CHART_COLORS[i % CHART_COLORS.length],
        pct: total > 0 ? (v.total / total) * 100 : 0,
      }));
  }, [transactions]);

  const total = data.reduce((s, d) => s + d.total, 0);

  const drill = useCallback((cat: CatData) => {
    const txns = transactions.filter(
      t => t.transaction_type === "debit" && (t.category || "Other") === cat.category
    );
    onDrillDown(cat.category, txns);
  }, [transactions, onDrillDown]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-tx-2">
        No expense data for period
      </div>
    );
  }

  return (
    <div className="flex gap-4 items-center">
      {/* Donut */}
      <div className="relative shrink-0" style={{ width: 150, height: 150 }}>
        <ResponsiveContainer width={150} height={150}>
          <PieChart>
            <Pie
              data={data}
              dataKey="total"
              nameKey="category"
              cx="50%" cy="50%"
              innerRadius={44}
              outerRadius={68}
              paddingAngle={2}
              onClick={(_, index) => {
                const cat = data[index];
                if (cat) drill(cat);
              }}
              onMouseEnter={(_, index) => setHovered(data[index]?.category ?? null)}
              onMouseLeave={() => setHovered(null)}
            >
              {data.map(d => (
                <Cell
                  key={d.category}
                  fill={d.color}
                  opacity={hovered === null || hovered === d.category ? 1 : 0.35}
                  style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-[10px] text-tx-3">Spend</span>
          <span className="text-sm font-bold text-tx">{formatCurrency(total)}</span>
        </div>
      </div>

      {/* Legend */}
      <ul className="flex-1 space-y-1.5 min-w-0">
        {data.map(d => (
          <li key={d.category}>
            <button
              className={cn(
                "w-full flex items-center gap-2 text-xs text-left rounded-lg px-2 py-1.5 transition-all",
                hovered === d.category ? "bg-elevated" : "hover:bg-elevated"
              )}
              onClick={() => drill(d)}
              onMouseEnter={() => setHovered(d.category)}
              onMouseLeave={() => setHovered(null)}
            >
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
              <span className={cn("truncate flex-1 transition-colors", hovered === d.category ? "text-tx" : "text-tx-2")}>
                {d.category}
              </span>
              <span className="text-tx font-semibold tabular-nums shrink-0">{formatCurrency(d.total)}</span>
              <span className="text-tx-3 tabular-nums w-8 text-right shrink-0">{d.pct.toFixed(0)}%</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
