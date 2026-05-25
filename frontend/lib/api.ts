const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ---- Types ----------------------------------------------------------------

export interface Transaction {
  id: number;
  date: string;
  description: string;
  amount: number;
  currency: string;
  transaction_type: "debit" | "credit";
  category: string;
  category_source: "auto" | "user";
  source_file: string;
  confidence_score: number;
  created_at: string;
}

export interface Alert {
  id: number;
  alert_type: string;
  severity: "low" | "medium" | "high";
  description: string;
  related_transactions: string | null;
  created_at: string;
  status: "unread" | "dismissed" | "snoozed";
  whatsapp_sent: number;
}

export interface DashboardSummary {
  this_month_spend: number;
  last_month_spend: number;
  delta: number;
  delta_pct: number;
  top_category: string | null;
  transaction_count: number;
  upcoming_charges: { description: string; amount: number }[];
  unread_alerts: number;
}

export interface QueryResponse {
  answer: string;
  low_confidence: boolean;
  sources: { source: string; score: number }[];
}

// ---- API calls ------------------------------------------------------------

export const getAlerts = (status?: string) =>
  apiFetch<{ alerts: Alert[] }>(`/alerts${status ? `?status=${status}` : ""}`);

export const dismissAlert = (id: number) =>
  apiFetch(`/alerts/${id}/dismiss`, { method: "POST" });

export const snoozeAlert = (id: number, days = 3) =>
  apiFetch(`/alerts/${id}/snooze`, { method: "POST", body: JSON.stringify({ days }) });

export const getTransactions = (params: {
  page?: number; page_size?: number; category?: string; sort_by?: string; sort_dir?: string;
}) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
  return apiFetch<{ total: number; transactions: Transaction[] }>(`/transactions?${q}`);
};

export const updateCategory = (id: number, category: string) =>
  apiFetch(`/transactions/${id}/category`, {
    method: "PATCH",
    body: JSON.stringify({ category }),
  });

export const getSummary = () => apiFetch<DashboardSummary>("/dashboard/summary");

export const sendQuery = (query: string) =>
  apiFetch<QueryResponse>("/query", { method: "POST", body: JSON.stringify({ query }) });

export async function sendFinanceCommand(args: string): Promise<QueryResponse> {
  console.debug("[api] sendFinanceCommand → POST /finance, args:", JSON.stringify(args));
  const res = await apiFetch<QueryResponse>("/finance", {
    method: "POST",
    body: JSON.stringify({ query: args }),
  });
  console.debug("[api] sendFinanceCommand ← response:", {
    answer_length: res.answer?.length,
    low_confidence: res.low_confidence,
    sources_count: res.sources?.length ?? 0,
  });
  return res;
}

export const getIngestionStatus = () => apiFetch("/ingestion/status");
