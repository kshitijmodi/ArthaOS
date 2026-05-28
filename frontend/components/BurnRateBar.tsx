"use client";
import { useMemo } from "react";
import { Flame } from "lucide-react";
import { Transaction } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface Props { allTxns: Transaction[] }

export default function BurnRateBar({ allTxns }: Props) {
  const info = useMemo(() => {
    const now = new Date();
    const day = now.getDate();
    if (day < 3) return null;

    const monthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const lastMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastMonthStr = `${lastMonthDate.getFullYear()}-${String(lastMonthDate.getMonth() + 1).padStart(2, "0")}`;

    const mtdExpenses = allTxns
      .filter(t => t.transaction_type === "debit" && t.date.startsWith(monthStr))
      .reduce((s, t) => s + t.amount, 0);

    const lastMonthExpenses = allTxns
      .filter(t => t.transaction_type === "debit" && t.date.startsWith(lastMonthStr))
      .reduce((s, t) => s + t.amount, 0);

    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const dailyRate = mtdExpenses / day;
    const projected = dailyRate * daysInMonth;
    const daysLeft = daysInMonth - day;

    let vsLastMonth: number | null = null;
    if (lastMonthExpenses > 0) vsLastMonth = ((projected / lastMonthExpenses) - 1) * 100;

    return { mtdExpenses, projected, dailyRate, daysLeft, vsLastMonth, day, daysInMonth };
  }, [allTxns]);

  if (!info) return null;

  const { projected, dailyRate, daysLeft, vsLastMonth } = info;
  const isOver = vsLastMonth !== null && vsLastMonth > 10;
  const isUnder = vsLastMonth !== null && vsLastMonth < -5;

  return (
    <div className={cn(
      "flex items-center gap-3 px-4 py-3 rounded-2xl border text-sm",
      isOver  ? "bg-expense/5 border-expense/20" :
      isUnder ? "bg-income/5 border-income/20"   :
                "bg-surface border-border"
    )}>
      <Flame size={15} className={cn(isOver ? "text-expense" : isUnder ? "text-income" : "text-warn")} />
      <span className="text-tx-2">
        At <span className="font-semibold text-tx">{formatCurrency(dailyRate)}/day</span> you&apos;re on pace for{" "}
        <span className={cn("font-semibold", isOver ? "text-expense" : isUnder ? "text-income" : "text-tx")}>
          {formatCurrency(projected)}
        </span>{" "}
        this month
        {vsLastMonth !== null && (
          <span className={cn("ml-1 text-xs", isOver ? "text-expense" : isUnder ? "text-income" : "text-tx-3")}>
            ({vsLastMonth > 0 ? "+" : ""}{vsLastMonth.toFixed(0)}% vs last month)
          </span>
        )}
      </span>
      <span className="ml-auto text-xs text-tx-3 shrink-0">{daysLeft}d left</span>
    </div>
  );
}
