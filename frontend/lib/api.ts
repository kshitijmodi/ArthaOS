const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
  starred: number;
  institution: string | null;
  account_name: string | null;
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
  starred?: boolean; charges_only?: boolean; query?: string;
}) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
  return apiFetch<{ total: number; transactions: Transaction[] }>(`/transactions?${q}`);
};

export const starTransaction = (id: number) =>
  apiFetch<{ starred: boolean }>(`/transactions/${id}/star`, { method: "PATCH" });

export const updateCategory = (id: number, category: string) =>
  apiFetch(`/transactions/${id}/category`, {
    method: "PATCH",
    body: JSON.stringify({ category }),
  });

export const getSummary = () => apiFetch<DashboardSummary>("/dashboard/summary");

export const sendQuery = (query: string, history: { role: string; content: string }[] = []) =>
  apiFetch<QueryResponse>("/query", { method: "POST", body: JSON.stringify({ query, history }) });

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

export const recategorizeAll = () =>
  apiFetch<{ updated: number }>("/categorizer/recategorize-all", { method: "POST" });

// Teller
export interface TellerAccount {
  account_id: string;
  name: string;
  type: string;
  subtype: string;
  currency: string;
  balance_available: number | null;
  balance_ledger: number | null;
  last_synced_at: string | null;
}

export interface TellerEnrollment {
  enrollment_id: string;
  institution: string;
  status: string;
  created_at: string;
  last_synced_at: string | null;
  accounts: TellerAccount[];
}

export const getTellerEnrollments = () =>
  apiFetch<{ enrollments: TellerEnrollment[] }>("/teller/enrollments");

export const tellerEnroll = (enrollment_id: string, access_token: string, institution: string) =>
  apiFetch("/teller/enroll", {
    method: "POST",
    body: JSON.stringify({ enrollment_id, access_token, institution }),
  });

export const tellerDisconnect = (enrollment_id: string) =>
  apiFetch(`/teller/enrollments/${enrollment_id}`, { method: "DELETE" });

export const tellerSyncNow = () =>
  apiFetch("/teller/sync", { method: "POST" });

// Goals
export interface Goal {
  id: number;
  name: string;
  goal_type: "spend_limit" | "savings" | "investment" | "custom";
  category: string | null;
  target_amount: number;
  current_amount: number;
  target_date: string | null;
  period: "monthly" | "yearly" | "one_time";
  status: "active" | "completed" | "paused" | "abandoned";
  notes: string | null;
  progress_pct: number;
  days_left: number | null;
  on_track: boolean;
  created_at: string;
}

export const getGoals = () =>
  apiFetch<{ goals: Goal[] }>("/goals");

export const createGoal = (data: {
  name: string; goal_type: string; category?: string;
  target_amount: number; target_date?: string; period?: string; notes?: string;
}) => apiFetch<Goal>("/goals", { method: "POST", body: JSON.stringify(data) });

export const updateGoal = (id: number, data: Partial<{
  name: string; target_amount: number; target_date: string;
  period: string; status: string; notes: string;
}>) => apiFetch<Goal>(`/goals/${id}`, { method: "PATCH", body: JSON.stringify(data) });

export const deleteGoal = (id: number) =>
  apiFetch(`/goals/${id}`, { method: "DELETE" });

// Accounts summary (bank balance, CC, investments, net worth)
export interface AccountsSummary {
  bank_balance: number;
  cc_balance: number;
  loan_balance: number;
  portfolio_401k: number;
  portfolio_stocks: number;
  net_worth: number;
}

export const getAccountsSummary = (as_of?: string) =>
  apiFetch<AccountsSummary>(`/dashboard/accounts-summary${as_of ? `?as_of=${as_of}` : ""}`);

export interface AccountDetail {
  institution: string; name: string; type: string; subtype: string; balance: number;
}
export interface AccountsDetail {
  bank_accounts: AccountDetail[];
  cc_accounts: AccountDetail[];
  loan_accounts: AccountDetail[];
  recent_transactions: {
    date: string; description: string; amount: number;
    transaction_type: string; category: string; institution: string | null;
  }[];
}
export const getAccountsDetail = () => apiFetch<AccountsDetail>("/dashboard/accounts-detail");

// Plaid
export interface PlaidAccount {
  account_id: string;
  name: string;
  official_name: string | null;
  type: string;
  subtype: string | null;
  currency: string;
  balance_available: number | null;
  balance_current: number | null;
  balance_limit: number | null;
  last_synced_at: string | null;
}

export interface PlaidItem {
  item_id: string;
  institution: string;
  status: string;
  created_at: string;
  last_synced_at: string | null;
  accounts: PlaidAccount[];
}

export const getPlaidLinkToken = () =>
  apiFetch<{ link_token: string }>("/plaid/link-token");

export const plaidExchange = (public_token: string, institution_id: string, institution: string) =>
  apiFetch("/plaid/exchange", {
    method: "POST",
    body: JSON.stringify({ public_token, institution_id, institution }),
  });

export const getPlaidItems = () =>
  apiFetch<{ items: PlaidItem[] }>("/plaid/items");

export const plaidDisconnect = (item_id: string) =>
  apiFetch(`/plaid/items/${item_id}`, { method: "DELETE" });

export const plaidSyncNow = () =>
  apiFetch("/plaid/sync", { method: "POST" });

export const plaidResync = () =>
  apiFetch("/plaid/resync", { method: "POST" });
