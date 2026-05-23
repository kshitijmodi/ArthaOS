"use client";
import { useState, useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import { getTransactions, updateCategory, Transaction } from "@/lib/api";
import { CATEGORIES, formatCurrency, formatDate, cn } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function TransactionTable() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getTransactions({
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        sort_by: "date",
        sort_dir: "desc",
      });
      setTransactions(res.transactions);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, categoryFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCategoryChange = async (id: number, category: string) => {
    await updateCategory(id, category);
    setTransactions(prev =>
      prev.map(t => t.id === id ? { ...t, category, category_source: "user" } : t)
    );
    setEditingId(null);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h2 className="font-semibold text-white">Transactions</h2>
        <span className="text-xs text-white/40">{total} total</span>
        <select
          value={categoryFilter}
          onChange={e => { setCategoryFilter(e.target.value); setPage(1); }}
          className="ml-auto bg-white/10 border border-white/10 rounded-lg text-sm text-white/70 px-3 py-1.5 focus:outline-none"
        >
          <option value="">All categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-white/40 text-xs uppercase tracking-wide border-b border-white/10">
              <th className="text-left pb-3 pr-4">Date</th>
              <th className="text-left pb-3 pr-4">Description</th>
              <th className="text-left pb-3 pr-4">Category</th>
              <th className="text-right pb-3 pr-4">Amount</th>
              <th className="text-right pb-3">Conf.</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b border-white/5 animate-pulse">
                    {[100, 200, 100, 80, 40].map((w, j) => (
                      <td key={j} className="py-3 pr-4">
                        <div className={`h-3 bg-white/10 rounded`} style={{ width: w }} />
                      </td>
                    ))}
                  </tr>
                ))
              : transactions.map(tx => (
                  <tr key={tx.id} className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                    <td className="py-3 pr-4 text-white/60 whitespace-nowrap">{formatDate(tx.date)}</td>
                    <td className="py-3 pr-4 text-white/90 max-w-[220px] truncate" title={tx.description}>
                      {tx.description}
                    </td>
                    <td className="py-3 pr-4">
                      {editingId === tx.id ? (
                        <select
                          autoFocus
                          defaultValue={tx.category}
                          onBlur={() => setEditingId(null)}
                          onChange={e => handleCategoryChange(tx.id, e.target.value)}
                          className="bg-zinc-800 border border-white/20 rounded px-2 py-1 text-xs text-white focus:outline-none"
                        >
                          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingId(tx.id)}
                          className={cn(
                            "text-xs px-2 py-1 rounded-full border transition-colors",
                            tx.category_source === "user"
                              ? "border-purple-500/40 text-purple-300 bg-purple-500/10"
                              : "border-white/10 text-white/60 hover:border-white/30"
                          )}
                        >
                          {tx.category}
                        </button>
                      )}
                    </td>
                    <td className={cn(
                      "py-3 pr-4 text-right font-medium tabular-nums",
                      tx.transaction_type === "credit" ? "text-green-400" : "text-white/90"
                    )}>
                      {tx.transaction_type === "credit" ? "+" : "−"}
                      {formatCurrency(tx.amount, tx.currency)}
                    </td>
                    <td className="py-3 text-right">
                      {tx.confidence_score < 0.7 && (
                        <span title="Low confidence parse"><AlertCircle size={14} className="text-amber-400 inline" /></span>
                      )}
                    </td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-white/50">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="flex items-center gap-1 hover:text-white disabled:opacity-30 transition-colors"
          >
            <ChevronLeft size={16} /> Prev
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="flex items-center gap-1 hover:text-white disabled:opacity-30 transition-colors"
          >
            Next <ChevronRight size={16} />
          </button>
        </div>
      )}
    </section>
  );
}
