"use client";
import { useState, useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, AlertCircle, Search, ArrowUpDown } from "lucide-react";
import { getTransactions, updateCategory, Transaction } from "@/lib/api";
import { CATEGORIES, formatCurrency, formatDate, cn } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function TransactionTable() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getTransactions({
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        sort_by: "date",
        sort_dir: sortDir,
      });
      setTransactions(res.transactions);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, categoryFilter, sortDir]);

  useEffect(() => { load(); }, [load]);

  const handleCategoryChange = async (id: number, category: string) => {
    await updateCategory(id, category);
    setTransactions(prev => prev.map(t => t.id === id ? { ...t, category, category_source: "user" } : t));
    setEditingId(null);
  };

  const filtered = search
    ? transactions.filter(t => t.description.toLowerCase().includes(search.toLowerCase()))
    : transactions;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="rounded-2xl border border-border bg-surface overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2 bg-bg border border-border rounded-xl px-3 py-2 flex-1 min-w-[200px] max-w-xs">
          <Search size={13} className="text-tx-3 shrink-0" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search transactions…"
            className="bg-transparent text-sm text-tx placeholder:text-tx-3 outline-none w-full"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={e => { setCategoryFilter(e.target.value); setPage(1); }}
          className="bg-bg border border-border rounded-xl text-sm text-tx-2 px-3 py-2 focus:outline-none focus:border-accent/50 cursor-pointer"
        >
          <option value="">All categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <button
          onClick={() => setSortDir(d => d === "desc" ? "asc" : "desc")}
          className="flex items-center gap-1.5 px-3 py-2 bg-bg border border-border rounded-xl text-sm text-tx-2 hover:text-tx transition-colors"
        >
          <ArrowUpDown size={13} />
          {sortDir === "desc" ? "Newest first" : "Oldest first"}
        </button>
        <span className="ml-auto text-xs text-tx-3">{total} transactions</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-3 px-5 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Date</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Description</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Category</th>
              <th className="text-right py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Amount</th>
              <th className="text-center py-3 px-5 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Flag</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50 animate-pulse">
                    {[80, 200, 100, 70, 30].map((w, j) => (
                      <td key={j} className={cn("py-3.5", j === 0 ? "px-5" : j === 4 ? "px-5" : "px-4")}>
                        <div className="h-3 bg-elevated rounded" style={{ width: w }} />
                      </td>
                    ))}
                  </tr>
                ))
              : filtered.map(tx => (
                  <tr key={tx.id} className="border-b border-border/40 hover:bg-elevated transition-colors group">
                    <td className="py-3.5 px-5 text-tx-3 whitespace-nowrap text-xs">{formatDate(tx.date)}</td>
                    <td className="py-3.5 px-4 text-tx max-w-[240px]">
                      <span className="truncate block" title={tx.description}>{tx.description}</span>
                    </td>
                    <td className="py-3.5 px-4">
                      {editingId === tx.id ? (
                        <select
                          autoFocus
                          defaultValue={tx.category}
                          onBlur={() => setEditingId(null)}
                          onChange={e => handleCategoryChange(tx.id, e.target.value)}
                          className="bg-bg border border-accent/50 rounded-lg px-2 py-1 text-xs text-tx focus:outline-none"
                        >
                          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingId(tx.id)}
                          className={cn(
                            "text-xs px-2.5 py-1 rounded-full border transition-all",
                            tx.category_source === "user"
                              ? "border-accent/40 text-accent bg-accent/10 hover:bg-accent/20"
                              : "border-border text-tx-2 hover:border-accent/40 hover:text-tx"
                          )}
                        >
                          {tx.category || "Uncategorised"}
                        </button>
                      )}
                    </td>
                    <td className={cn(
                      "py-3.5 px-4 text-right font-semibold tabular-nums",
                      tx.transaction_type === "credit" ? "text-income" : "text-tx"
                    )}>
                      {tx.transaction_type === "credit" ? "+" : "−"}
                      {formatCurrency(tx.amount)}
                    </td>
                    <td className="py-3.5 px-5 text-center">
                      {tx.confidence_score < 0.7 && (
                        <span title="Low confidence parse">
                          <AlertCircle size={14} className="text-warn inline" />
                        </span>
                      )}
                    </td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-border">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="flex items-center gap-1.5 text-sm text-tx-2 hover:text-tx disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft size={16} /> Previous
          </button>
          <span className="text-xs text-tx-3">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="flex items-center gap-1.5 text-sm text-tx-2 hover:text-tx disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Next <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
