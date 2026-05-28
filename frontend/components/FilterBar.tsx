"use client";
import { useState, useRef, useEffect } from "react";
import { ChevronDown, SlidersHorizontal, X, Calendar } from "lucide-react";
import { cn, CATEGORIES } from "@/lib/utils";

export interface FilterState {
  period: "day" | "week" | "month" | "year" | "all" | "custom";
  dateFrom: string;
  dateTo: string;
  categories: string[];
  amountMin: number;
  amountMax: number;
}

export const defaultFilters: FilterState = {
  period: "month",
  dateFrom: "",
  dateTo: "",
  categories: [],
  amountMin: 0,
  amountMax: 50000,
};

const PERIODS: { key: FilterState["period"]; label: string }[] = [
  { key: "day",    label: "Today"  },
  { key: "week",   label: "7D"     },
  { key: "month",  label: "MTD"    },
  { key: "year",   label: "YTD"    },
  { key: "all",    label: "All"    },
  { key: "custom", label: "Custom" },
];

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  maxAmount?: number;
}

export default function FilterBar({ filters, onChange, maxAmount = 50000 }: Props) {
  const [catOpen, setCatOpen] = useState(false);
  const catRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (catRef.current && !catRef.current.contains(e.target as Node)) setCatOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const toggleCat = (cat: string) => {
    const next = filters.categories.includes(cat)
      ? filters.categories.filter(c => c !== cat)
      : [...filters.categories, cat];
    onChange({ ...filters, categories: next });
  };

  const hasActive =
    filters.period !== "month" ||
    filters.categories.length > 0 ||
    filters.amountMin > 0 ||
    filters.amountMax < maxAmount;

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Period pills */}
      <div className="flex items-center gap-0.5 bg-elevated rounded-xl p-1 border border-border/50">
        {PERIODS.map(p => (
          <button
            key={p.key}
            onClick={() => onChange({ ...filters, period: p.key })}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150",
              filters.period === p.key
                ? "bg-accent text-white shadow-sm"
                : "text-tx-2 hover:text-tx hover:bg-surface"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Custom date range */}
      {filters.period === "custom" && (
        <div className="flex items-center gap-2 bg-surface border border-accent/40 rounded-xl px-3 py-1.5 animate-fade-in">
          <Calendar size={12} className="text-accent shrink-0" />
          <input
            type="date"
            value={filters.dateFrom}
            onChange={e => onChange({ ...filters, dateFrom: e.target.value })}
            className="text-xs bg-transparent text-tx outline-none w-28"
          />
          <span className="text-tx-3 text-xs">→</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={e => onChange({ ...filters, dateTo: e.target.value })}
            className="text-xs bg-transparent text-tx outline-none w-28"
          />
        </div>
      )}

      {/* Category dropdown */}
      <div className="relative" ref={catRef}>
        <button
          onClick={() => setCatOpen(o => !o)}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-medium transition-all",
            filters.categories.length > 0
              ? "border-accent/50 bg-accent/10 text-accent"
              : "border-border bg-surface text-tx-2 hover:text-tx hover:border-border/80"
          )}
        >
          <span>
            {filters.categories.length === 0 ? "All Categories" : `${filters.categories.length} selected`}
          </span>
          <ChevronDown size={12} className={cn("transition-transform", catOpen && "rotate-180")} />
        </button>

        {catOpen && (
          <div className="absolute top-full left-0 mt-1.5 w-52 bg-surface border border-border rounded-xl shadow-2xl z-50 animate-fade-in overflow-hidden">
            <div className="p-1.5 max-h-60 overflow-y-auto">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  onClick={() => toggleCat(cat)}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-left transition-colors",
                    filters.categories.includes(cat)
                      ? "bg-accent/10 text-accent"
                      : "text-tx-2 hover:text-tx hover:bg-elevated"
                  )}
                >
                  <span className={cn(
                    "w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors",
                    filters.categories.includes(cat) ? "bg-accent border-accent" : "border-border"
                  )}>
                    {filters.categories.includes(cat) && (
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path d="M1 4L3 6L7 2" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    )}
                  </span>
                  {cat}
                </button>
              ))}
            </div>
            {filters.categories.length > 0 && (
              <div className="border-t border-border p-1.5">
                <button
                  onClick={() => { onChange({ ...filters, categories: [] }); setCatOpen(false); }}
                  className="w-full text-xs text-expense hover:bg-expense/10 px-3 py-1.5 rounded-lg transition-colors"
                >
                  Clear selection
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Amount range */}
      <div className="flex items-center gap-2 bg-surface border border-border rounded-xl px-3 py-2">
        <SlidersHorizontal size={12} className="text-tx-3 shrink-0" />
        <span className="text-xs text-tx-3">$</span>
        <input
          type="number"
          value={filters.amountMin || ""}
          onChange={e => onChange({ ...filters, amountMin: Math.max(0, +(e.target.value || 0)) })}
          className="w-16 text-xs bg-transparent text-tx outline-none placeholder:text-tx-3"
          placeholder="Min"
          min={0}
        />
        <span className="text-tx-3 text-xs">–</span>
        <input
          type="number"
          value={filters.amountMax || ""}
          onChange={e => onChange({ ...filters, amountMax: Math.max(filters.amountMin, +(e.target.value || 0)) })}
          className="w-20 text-xs bg-transparent text-tx outline-none placeholder:text-tx-3"
          placeholder="Max"
          min={0}
        />
      </div>

      {hasActive && (
        <button
          onClick={() => onChange({ ...defaultFilters, amountMax: maxAmount })}
          className="flex items-center gap-1.5 px-2.5 py-2 rounded-xl text-xs text-tx-2 hover:text-tx hover:bg-elevated transition-all animate-fade-in"
        >
          <X size={12} />
          Reset
        </button>
      )}
    </div>
  );
}
