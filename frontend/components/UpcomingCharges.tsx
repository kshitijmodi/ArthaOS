"use client";
import { useMemo } from "react";
import { CalendarClock } from "lucide-react";
import { Transaction } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const RECURRING_CATS = new Set(["EMIs", "Subscriptions", "Insurance", "Rent", "Utilities"]);

interface Props { allTxns: Transaction[] }

export default function UpcomingCharges({ allTxns }: Props) {
  const upcoming = useMemo(() => {
    const now = new Date();
    const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const lastMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastMonth = `${lastMonthDate.getFullYear()}-${String(lastMonthDate.getMonth() + 1).padStart(2, "0")}`;

    // Find recurring merchants from last month
    const lastMonthMap = new Map<string, { amount: number; category: string }>();
    for (const t of allTxns) {
      if (t.transaction_type === "debit" && RECURRING_CATS.has(t.category) && t.date.startsWith(lastMonth)) {
        if (!lastMonthMap.has(t.description) || lastMonthMap.get(t.description)!.amount < t.amount) {
          lastMonthMap.set(t.description, { amount: t.amount, category: t.category });
        }
      }
    }

    // Find which ones haven't appeared this month yet
    const thisMonthSeen = new Set(
      allTxns
        .filter(t => t.transaction_type === "debit" && t.date.startsWith(thisMonth))
        .map(t => t.description)
    );

    return Array.from(lastMonthMap.entries())
      .filter(([desc]) => !thisMonthSeen.has(desc))
      .map(([desc, info]) => ({ description: desc, ...info }))
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 5);
  }, [allTxns]);

  if (upcoming.length === 0) return null;

  const CAT_COLORS: Record<string, string> = {
    EMIs: "text-expense bg-expense/10",
    Subscriptions: "text-accent bg-accent/10",
    Insurance: "text-warn bg-warn/10",
    Rent: "text-tx-2 bg-elevated",
    Utilities: "text-tx-2 bg-elevated",
  };

  return (
    <div className="bg-surface border border-border rounded-2xl overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-border">
        <CalendarClock size={14} className="text-warn" />
        <h2 className="font-semibold text-tx">Upcoming Charges</h2>
        <span className="text-xs text-tx-3 ml-1">— not yet billed this month</span>
      </div>
      <ul className="divide-y divide-border/40">
        {upcoming.map((item, i) => (
          <li key={i} className="flex items-center gap-3 px-5 py-3">
            <span className={cn(
              "text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0",
              CAT_COLORS[item.category] ?? "text-tx-2 bg-elevated"
            )}>
              {item.category}
            </span>
            <span className="text-sm text-tx truncate flex-1">{item.description}</span>
            <span className="text-sm font-semibold text-tx tabular-nums shrink-0">
              {formatCurrency(item.amount)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
