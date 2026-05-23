"use client";
import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Clock, RefreshCw } from "lucide-react";
import { getIngestionStatus, apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function IngestionStatus() {
  const [data, setData] = useState<any>(null);
  const [fetching, setFetching] = useState(false);

  const load = async () => {
    try { setData(await getIngestionStatus()); } catch {}
  };

  useEffect(() => { load(); }, []);

  const triggerFetch = async () => {
    setFetching(true);
    try { await apiFetch("/ingest/fetch-email", { method: "POST" }); await load(); }
    finally { setFetching(false); }
  };

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="font-semibold text-white">Ingestion Status</h2>
        <button
          onClick={triggerFetch}
          disabled={fetching}
          className="ml-auto flex items-center gap-1.5 text-xs text-white/50 hover:text-white border border-white/10 hover:border-white/30 rounded-lg px-3 py-1.5 transition-colors"
        >
          <RefreshCw size={12} className={cn(fetching && "animate-spin")} />
          Fetch email now
        </button>
      </div>

      {data ? (
        <div className="space-y-3">
          {data.mailbox_state?.map((m: any) => (
            <div key={m.mailbox} className="flex items-center gap-3 text-sm">
              {m.status === "success"
                ? <CheckCircle size={14} className="text-green-400 shrink-0" />
                : <XCircle size={14} className="text-red-400 shrink-0" />}
              <span className="capitalize text-white/70 w-12">{m.mailbox}</span>
              <span className="text-white/40 text-xs">
                {m.last_fetched_at
                  ? `Last fetched: ${new Date(m.last_fetched_at).toLocaleString("en-IN")}`
                  : "Never fetched"}
              </span>
            </div>
          ))}

          {data.failures?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10">
              <p className="text-xs text-red-400 mb-2">Recent failures:</p>
              {data.failures.map((f: any) => (
                <div key={f.id} className="text-xs text-white/50 flex gap-2">
                  <XCircle size={12} className="text-red-400 shrink-0 mt-0.5" />
                  <span>{f.filename}: {f.failure_reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2 animate-pulse">
          {[1,2].map(i => <div key={i} className="h-4 bg-white/10 rounded w-3/4" />)}
        </div>
      )}
    </section>
  );
}
