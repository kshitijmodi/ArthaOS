import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, _currency?: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.abs(amount));
}

/** Like formatCurrency but preserves the sign — use for balances that can be negative (CC, loans, net worth). */
export function formatSigned(amount: number): string {
  const abs = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.abs(amount));
  return amount < 0 ? `-${abs}` : `+${abs}`;
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateShort(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export const CATEGORIES = [
  "Dining", "Education", "EMIs", "Fees & Interest", "Groceries",
  "Healthcare", "Income", "Insurance", "Investments", "Miscellaneous",
  "Rent", "Shopping", "Subscriptions", "Transfer", "Travel", "Utilities",
] as const;

export const SEVERITY_COLORS: Record<string, string> = {
  high: "text-expense bg-expense/10 border-expense/20",
  medium: "text-warn bg-warn/10 border-warn/20",
  low: "text-income bg-income/10 border-income/20",
};

export const CHART_COLORS = [
  "#6366f1", "#10b981", "#f43f5e", "#f59e0b",
  "#3b82f6", "#8b5cf6", "#06b6d4", "#ec4899",
  "#84cc16", "#f97316", "#14b8a6", "#e879f9",
];
