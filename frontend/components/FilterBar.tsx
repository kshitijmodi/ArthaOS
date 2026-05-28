"use client";
import { useState, useRef, useEffect } from "react";
import { ChevronDown, X, Calendar } from "lucide-react";
import { cn, CATEGORIES } from "@/lib/utils";
import { apiFetch } from "@/lib/api";

export interface FilterState {
  mode: "monthly" | "weekly" | "custom";
  selectedMonth: string;  // "2026-05"
  weekOffset: number;     // 0=this week, 1=last week, 2=2 weeks ago…
  dateFrom: string;
  dateTo: string;
  categories: string[];
  amountMin: number;
  amountMax: number;
}

function currentMonthStr() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export const defaultFilters: FilterState = {
  mode: "monthly",
  selectedMonth: currentMonthStr(),
  weekOffset: 0,
  dateFrom: "",
  dateTo: "",
  categories: [],
  amountMin: 0,
  amountMax: 50000,
};

// Last 12 months as { label, value } — most recent first
function getMonthPills() {
  const now = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString("en-US", { month: "short", year: i >= 12 ? "numeric" : "2-digit" });
    return { value, label };
  });
}

// Last 8 weeks as { label, offset } — label shows "Week of May 25" (Monday date)
function getWeekPills() {
  const now = new Date();
  const dayOfWeek = now.getDay(); // 0=Sun
  // Monday of current week
  const thisMonday = new Date(now);
  thisMonday.setDate(now.getDate() - ((dayOfWeek + 6) % 7));
  thisMonday.setHours(0, 0, 0, 0);

  return Array.from({ length: 8 }, (_, offset) => {
    const monday = new Date(thisMonday);
    monday.setDate(thisMonday.getDate() - offset * 7);
    const label = offset === 0
      ? "This week"
      : `Week of ${monday.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
    return { label, offset };
  });
}

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  maxAmount?: number;
}

export default function FilterBar({ filters, onChange, maxAmount = 50000 }: Props) {
  const [catOpen, setCatOpen] = useState(false);
  const catRef = useRef<HTMLDivElement>(null);
  const [categoryList, setCategoryList] = useState<string[]>([...CATEGORIES].sort());

  useEffect(() => {
    apiFetch<{ categories: { name: string }[] }>("/categories")
      .then(r => setCategoryList(r.categories.map(c => c.name).sort()))
      .catch(() => {}); // keep static fallback
  }, []);

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

  const monthPills = getMonthPills();
  const weekPills  = getWeekPills();

  const hasActive =
    filters.categories.length > 0 ||
    filters.amountMin > 0 ||
    filters.amountMax < maxAmount;

  const modeBtn = (m: FilterState["mode"], label: string) => (
    <button
      key={m}
      onClick={() => onChange({ ...filters, mode: m })}
      className={cn(
        "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150",
        filters.mode === m
          ? "bg-accent text-white shadow-sm"
          : "text-tx-2 hover:text-tx hover:bg-surface"
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-2 md:space-y-3">
      {/* Mode selector */}
      <div className="flex items-center gap-2 md:gap-3 flex-wrap">
        <div className="flex items-center gap-0.5 bg-elevated rounded-xl p-1 border border-border/50">
          {modeBtn("monthly", "Monthly")}
          {modeBtn("weekly",  "Weekly")}
          {modeBtn("custom",  "Custom")}
        </div>

        {/* Category filter */}
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
                {categoryList.map(cat => (
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

        {hasActive && (
          <button
            onClick={() => onChange({ ...defaultFilters, amountMax: maxAmount })}
            className="flex items-center gap-1.5 px-2.5 py-2 rounded-xl text-xs text-tx-2 hover:text-tx hover:bg-elevated transition-all"
          >
            <X size={12} /> Reset
          </button>
        )}
      </div>

      {/* Month pills */}
      {filters.mode === "monthly" && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {monthPills.map(p => (
            <button
              key={p.value}
              onClick={() => onChange({ ...filters, selectedMonth: p.value })}
              className={cn(
                "px-3 py-1.5 rounded-xl text-xs font-medium transition-all border shrink-0",
                filters.selectedMonth === p.value
                  ? "bg-accent text-white border-accent shadow-sm"
                  : "border-border text-tx-2 hover:text-tx hover:border-border/80 hover:bg-elevated"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {/* Week pills */}
      {filters.mode === "weekly" && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {weekPills.map(p => (
            <button
              key={p.offset}
              onClick={() => onChange({ ...filters, weekOffset: p.offset })}
              className={cn(
                "px-3 py-1.5 rounded-xl text-xs font-medium transition-all border shrink-0",
                filters.weekOffset === p.offset
                  ? "bg-accent text-white border-accent shadow-sm"
                  : "border-border text-tx-2 hover:text-tx hover:border-border/80 hover:bg-elevated"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {/* Custom date range */}
      {filters.mode === "custom" && (
        <div className="flex items-center gap-2 bg-surface border border-accent/40 rounded-xl px-3 py-2 w-fit">
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
    </div>
  );
}
