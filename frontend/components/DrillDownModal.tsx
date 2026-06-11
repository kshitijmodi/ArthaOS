"use client";
import { useEffect, useMemo } from "react";
import { X, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Transaction } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";

interface Props {
  label: string;
  transactions: Transaction[];
  onClose: () => void;
}

export default function DrillDownModal({ label, transactions, onClose }: Props) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  const { credits, debits, creditTotal, debitTotal } = useMemo(() => {
    const cr = transactions.filter(t => t.transaction_type === "credit");
    const db = transactions.filter(t => t.transaction_type === "debit");
    return {
      credits: cr,
      debits: db,
      creditTotal: cr.reduce((s, t) => s + t.amount, 0),
      debitTotal:  db.reduce((s, t) => s + t.amount, 0),
    };
  }, [transactions]);

  const sorted = [...transactions].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 animate-fade-in"
        onClick={onClose}
      />
      <aside className="fixed right-0 top-0 h-full w-full max-w-md bg-surface border-l border-border shadow-2xl z-50 flex flex-col animate-slide-right">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border shrink-0">
          <div>
            <h2 className="font-bold text-tx text-lg">{label}</h2>
            <p className="text-xs text-tx-2 mt-0.5">
              {transactions.length} transaction{transactions.length !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl hover:bg-elevated flex items-center justify-center text-tx-2 hover:text-tx transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Summary pills */}
        {(credits.length > 0 || debits.length > 0) && (
          <div className="flex flex-wrap gap-2 px-6 py-4 border-b border-border shrink-0">
            {credits.length > 0 && (
              <div className="flex items-center gap-1.5 bg-income/10 text-income px-3 py-1.5 rounded-full text-xs font-semibold">
                <ArrowUpRight size={12} />
                In: {formatCurrency(creditTotal)}
              </div>
            )}
            {debits.length > 0 && (
              <div className="flex items-center gap-1.5 bg-expense/10 text-expense px-3 py-1.5 rounded-full text-xs font-semibold">
                <ArrowDownRight size={12} />
                Out: {formatCurrency(debitTotal)}
              </div>
            )}
          </div>
        )}

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-sm text-tx-2">
              No transactions
            </div>
          ) : (
            <ul className="divide-y divide-border/40">
              {sorted.map(t => (
                <li key={t.id} className="flex items-center gap-4 px-6 py-4 hover:bg-elevated transition-colors">
                  <div className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center shrink-0 font-bold text-sm",
                    t.transaction_type === "credit" ? "bg-income/10 text-income" : "bg-expense/10 text-expense"
                  )}>
                    {t.transaction_type === "credit" ? "+" : "−"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-tx truncate">{t.description}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-tx-3">{formatDate(t.date)}</span>
                      {t.category && (
                        <span className="text-[10px] bg-elevated text-tx-2 px-1.5 py-0.5 rounded-full border border-border/50">
                          {t.category}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className={cn(
                    "font-semibold text-sm tabular-nums shrink-0",
                    t.transaction_type === "credit" ? "text-income" : "text-expense"
                  )}>
                    {t.transaction_type === "credit" ? "+" : "−"}{formatCurrency(t.amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
