"use client";
import { useEffect, useState } from "react";
import { CheckCircle, XCircle, RefreshCw, Tags, RotateCcw } from "lucide-react";
import { getIngestionStatus, recategorizeAll, plaidResync, apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function IngestionStatus() {
  const [data, setData] = useState<any>(null);
  const [fetching, setFetching] = useState(false);
  const [recatMsg, setRecatMsg] = useState<string | null>(null);
  const [recatting, setRecatting] = useState(false);
  const [resyncing, setResyncing] = useState(false);

  const load = async () => {
    try { setData(await getIngestionStatus()); } catch {}
  };

  useEffect(() => { load(); }, []);

  const triggerFetch = async () => {
    setFetching(true);
    try { await apiFetch("/ingest/fetch-email", { method: "POST" }); await load(); }
    finally { setFetching(false); }
  };

  const triggerRecategorize = async () => {
    setRecatting(true);
    setRecatMsg(null);
    try {
      const res = await recategorizeAll();
      setRecatMsg(`Re-categorized ${res.updated} transaction${res.updated !== 1 ? "s" : ""}`);
    } catch {
      setRecatMsg("Re-categorize failed");
    } finally { setRecatting(false); }
  };

  const triggerPlaidResync = async () => {
    setResyncing(true);
    setRecatMsg(null);
    try {
      const res = await plaidResync();
      setRecatMsg(`Plaid reset: deleted ${(res as any).deleted ?? 0} old transactions, imported ${(res as any).new_transactions ?? 0} fresh`);
    } catch {
      setRecatMsg("Plaid reset failed — check backend connection");
    } finally { setResyncing(false); }
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="font-semibold text-tx">Email Ingestion</h2>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={triggerRecategorize}
            disabled={recatting}
            title="Re-run keyword rules on all auto-categorized transactions (fixes Income=0 and other mis-categorizations)"
            className="flex items-center gap-1.5 text-xs text-tx-2 hover:text-tx border border-border hover:border-accent/40 rounded-xl px-3 py-1.5 transition-all disabled:opacity-50"
          >
            <Tags size={12} className={cn(recatting && "animate-pulse")} />
            {recatting ? "Re-categorizing…" : "Re-categorize"}
          </button>
          <button
            onClick={triggerPlaidResync}
            disabled={resyncing}
            title="Delete all Plaid transactions and re-fetch from scratch with corrected Income categorization"
            className="flex items-center gap-1.5 text-xs text-tx-2 hover:text-income border border-border hover:border-income/40 rounded-xl px-3 py-1.5 transition-all disabled:opacity-50"
          >
            <RotateCcw size={12} className={cn(resyncing && "animate-spin")} />
            {resyncing ? "Resyncing Plaid…" : "Plaid Reset"}
          </button>
          <button
            onClick={triggerFetch}
            disabled={fetching}
            className="flex items-center gap-1.5 text-xs text-tx-2 hover:text-tx border border-border hover:border-accent/40 rounded-xl px-3 py-1.5 transition-all"
          >
            <RefreshCw size={12} className={cn(fetching && "animate-spin")} />
            Fetch now
          </button>
        </div>
      </div>
      {recatMsg && (
        <p className={cn("text-xs mb-3", recatMsg.includes("failed") ? "text-expense" : "text-income")}>{recatMsg}</p>
      )}

      {data ? (
        <div className="space-y-3">
          {data.mailbox_state?.map((m: any) => (
            <div key={m.mailbox} className="flex items-center gap-3 text-sm">
              {m.status === "success"
                ? <CheckCircle size={14} className="text-income shrink-0" />
                : <XCircle size={14} className="text-expense shrink-0" />}
              <span className="capitalize text-tx-2 w-14">{m.mailbox}</span>
              <span className="text-tx-3 text-xs">
                {m.last_fetched_at
                  ? `Last fetched: ${new Date(m.last_fetched_at).toLocaleString("en-US")}`
                  : "Never fetched"}
              </span>
            </div>
          ))}

          {data.failures?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border">
              <p className="text-xs text-expense mb-2">Recent failures:</p>
              {data.failures.map((f: any) => (
                <div key={f.id} className="text-xs text-tx-2 flex gap-2">
                  <XCircle size={12} className="text-expense shrink-0 mt-0.5" />
                  <span>{f.filename}: {f.failure_reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2 animate-pulse">
          {[1, 2].map(i => <div key={i} className="h-4 bg-elevated rounded w-3/4" />)}
        </div>
      )}
    </section>
  );
}
