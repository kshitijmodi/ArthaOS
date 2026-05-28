"use client";
import { useState, useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, AlertCircle, Search, ArrowUpDown, Star, DollarSign } from "lucide-react";
import { getTransactions, updateCategory, starTransaction, Transaction } from "@/lib/api";
import { CATEGORIES, formatCurrency, formatDate, cn } from "@/lib/utils";

const PAGE_SIZE = 50;

function detectPaymentMethod(desc: string): string {
  const d = desc.toLowerCase();
  if (/apple pay|google pay|tap to pay|contactless|nfc/.test(d)) return "Tap";
  if (/online|web|e-?comm|digital|app|recurring|subscription|autopay|auto[-\s]?pay|internet/.test(d)) return "Online";
  if (/pos |in.store|swipe|retail|#\d{4}/.test(d)) return "Swipe";
  return "";
}

export default function TransactionTable() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [starredOnly, setStarredOnly] = useState(false);
  const [chargesOnly, setChargesOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getTransactions({
        page,
        page_size: PAGE_SIZE,
        category: categoryFilter || undefined,
        sort_by: "date",
        sort_dir: sortDir,
        starred: starredOnly || undefined,
        charges_only: chargesOnly || undefined,
      });
      setTransactions(res.transactions);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, categoryFilter, sortDir, starredOnly, chargesOnly]);

  useEffect(() => { load(); }, [load]);

  const handleCategoryChange = async (id: number, category: string) => {
    await updateCategory(id, category);
    setTransactions(prev => prev.map(t => t.id === id ? { ...t, category, category_source: "user" } : t));
    setEditingId(null);
  };

  const handleStar = async (id: number, currentStarred: number) => {
    const res = await starTransaction(id);
    setTransactions(prev => prev.map(t => t.id === id ? { ...t, starred: res.starred ? 1 : 0 } : t));
  };

  const filtered = search
    ? transactions.filter(t => t.description.toLowerCase().includes(search.toLowerCase()))
    : transactions;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const filterBtn = (active: boolean, label: string, icon: React.ReactNode, onClick: () => void) => (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition-all",
        active
          ? "border-accent/50 bg-accent/10 text-accent"
          : "border-border bg-surface text-tx-2 hover:text-tx hover:border-border/80"
      )}
    >
      {icon}
      {label}
    </button>
  );

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
        {filterBtn(starredOnly, "Starred", <Star size={12} />, () => { setStarredOnly(s => !s); setPage(1); })}
        {filterBtn(chargesOnly, "Fees & Interest", <DollarSign size={12} />, () => { setChargesOnly(s => !s); setPage(1); })}
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
              <th className="text-center py-3 px-3 text-[11px] font-semibold uppercase tracking-wider text-tx-3 w-8">★</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Date</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Description</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Source</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Method</th>
              <th className="text-left py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Category</th>
              <th className="text-right py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Amount</th>
              <th className="text-center py-3 px-4 text-[11px] font-semibold uppercase tracking-wider text-tx-3">Flag</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50 animate-pulse">
                    {[20, 70, 180, 90, 60, 90, 60, 20].map((w, j) => (
                      <td key={j} className="py-3.5 px-4">
                        <div className="h-3 bg-elevated rounded" style={{ width: w }} />
                      </td>
                    ))}
                  </tr>
                ))
              : filtered.map(tx => {
                  const method = detectPaymentMethod(tx.description);
                  const institution = tx.institution || tx.account_name || "";
                  return (
                    <tr key={tx.id} className="border-b border-border/40 hover:bg-elevated transition-colors group">
                      {/* Star */}
                      <td className="py-3.5 px-3 text-center">
                        <button
                          onClick={() => handleStar(tx.id, tx.starred)}
                          className={cn(
                            "transition-colors",
                            tx.starred ? "text-warn" : "text-border hover:text-tx-3"
                          )}
                          title={tx.starred ? "Unstar" : "Star for later"}
                        >
                          <Star size={13} fill={tx.starred ? "currentColor" : "none"} />
                        </button>
                      </td>
                      <td className="py-3.5 px-4 text-tx-3 whitespace-nowrap text-xs">{formatDate(tx.date)}</td>
                      <td className="py-3.5 px-4 text-tx max-w-[200px]">
                        <span className="truncate block" title={tx.description}>{tx.description}</span>
                      </td>
                      {/* Institution / account */}
                      <td className="py-3.5 px-4 text-tx-3 text-xs max-w-[100px]">
                        {institution ? (
                          <span className="truncate block" title={institution}>{institution}</span>
                        ) : (
                          <span className="text-border">—</span>
                        )}
                      </td>
                      {/* Payment method */}
                      <td className="py-3.5 px-4">
                        {method ? (
                          <span className={cn(
                            "text-[10px] px-2 py-0.5 rounded-full font-medium",
                            method === "Tap"    && "bg-income/10 text-income",
                            method === "Online" && "bg-accent/10 text-accent",
                            method === "Swipe"  && "bg-tx-3/10 text-tx-3",
                          )}>
                            {method}
                          </span>
                        ) : (
                          <span className="text-border text-xs">—</span>
                        )}
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
                              tx.category === "Fees & Interest"
                                ? "border-expense/40 text-expense bg-expense/10 hover:bg-expense/20"
                                : tx.category_source === "user"
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
                      <td className="py-3.5 px-4 text-center">
                        {tx.confidence_score < 0.7 && (
                          <span title="Low confidence parse">
                            <AlertCircle size={13} className="text-warn inline" />
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
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
