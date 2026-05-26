"use client";
import { useState, useEffect, useCallback } from "react";
import { Building2, RefreshCw, Trash2, Plus, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import {
  getTellerEnrollments, tellerEnroll, tellerDisconnect, tellerSyncNow,
  TellerEnrollment,
} from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

const TELLER_APP_ID = process.env.NEXT_PUBLIC_TELLER_APP_ID ?? "";
const TELLER_ENV    = (process.env.NEXT_PUBLIC_TELLER_ENV ?? "sandbox") as "sandbox" | "development" | "production";

declare global {
  interface Window {
    TellerConnect?: {
      setup: (cfg: object) => { open: () => void };
    };
  }
}

function useTellerScript() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (window.TellerConnect) { setReady(true); return; }
    const s = document.createElement("script");
    s.src = "https://cdn.teller.io/connect/connect.js";
    s.async = true;
    s.onload = () => setReady(true);
    document.head.appendChild(s);
  }, []);
  return ready;
}

function AccountRow({ account }: { account: TellerEnrollment["accounts"][0] }) {
  const balance = account.balance_ledger ?? account.balance_available;
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-elevated transition-colors">
      <div>
        <p className="text-sm font-medium text-tx">{account.name}</p>
        <p className="text-xs text-tx-3 capitalize">{account.type} · {account.subtype ?? "—"}</p>
      </div>
      <div className="text-right">
        {balance != null ? (
          <p className="text-sm font-semibold text-tx">{formatCurrency(balance)}</p>
        ) : (
          <p className="text-xs text-tx-3">—</p>
        )}
      </div>
    </div>
  );
}

function EnrollmentCard({
  enrollment,
  onDisconnect,
  onSync,
}: {
  enrollment: TellerEnrollment;
  onDisconnect: (id: string) => void;
  onSync: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const totalBalance = enrollment.accounts.reduce(
    (sum, a) => sum + (a.balance_ledger ?? a.balance_available ?? 0), 0
  );

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-elevated transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center shrink-0">
          <Building2 size={14} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-tx">{enrollment.institution}</p>
          <p className="text-xs text-tx-3">
            {enrollment.accounts.length} account{enrollment.accounts.length !== 1 ? "s" : ""}
            {enrollment.last_synced_at && (
              <> · last synced {new Date(enrollment.last_synced_at).toLocaleDateString()}</>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-sm font-semibold text-tx">{formatCurrency(totalBalance)}</span>
          <span className={cn(
            "w-2 h-2 rounded-full",
            enrollment.status === "active" ? "bg-income" : "bg-tx-3"
          )} />
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-1">
          {enrollment.accounts.map(a => (
            <AccountRow key={a.account_id} account={a} />
          ))}
          <div className="flex items-center gap-2 pt-2 mt-1 border-t border-border/50">
            <button
              onClick={onSync}
              className="flex items-center gap-1.5 text-xs text-tx-2 hover:text-tx px-2 py-1.5 rounded-lg hover:bg-elevated transition-colors"
            >
              <RefreshCw size={12} /> Sync now
            </button>
            <button
              onClick={() => onDisconnect(enrollment.enrollment_id)}
              className="flex items-center gap-1.5 text-xs text-expense hover:bg-expense/10 px-2 py-1.5 rounded-lg transition-colors ml-auto"
            >
              <Trash2 size={12} /> Disconnect
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TellerConnect() {
  const [enrollments, setEnrollments] = useState<TellerEnrollment[]>([]);
  const [loading, setLoading]   = useState(true);
  const [syncing, setSyncing]   = useState(false);
  const [msg, setMsg]           = useState<{ text: string; ok: boolean } | null>(null);
  const scriptReady = useTellerScript();

  const load = useCallback(async () => {
    try {
      const data = await getTellerEnrollments();
      setEnrollments(data.enrollments.filter(e => e.status === "active"));
    } catch { /* backend may not have enrollments yet */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openTellerLink = () => {
    if (!window.TellerConnect) return;
    const tc = window.TellerConnect.setup({
      applicationId: TELLER_APP_ID,
      environment:   TELLER_ENV,
      onSuccess: async (enrollment: { accessToken: string; enrollment: { id: string; institution: { name: string } } }) => {
        try {
          await tellerEnroll(
            enrollment.enrollment.id,
            enrollment.accessToken,
            enrollment.enrollment.institution.name,
          );
          setMsg({ text: `${enrollment.enrollment.institution.name} connected — syncing now…`, ok: true });
          setTimeout(load, 3000);
        } catch {
          setMsg({ text: "Failed to save enrollment — try again.", ok: false });
        }
      },
      onExit: () => {},
    });
    tc.open();
  };

  const handleDisconnect = async (id: string) => {
    await tellerDisconnect(id);
    setEnrollments(prev => prev.filter(e => e.enrollment_id !== id));
    setMsg({ text: "Institution disconnected.", ok: true });
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      const result = await tellerSyncNow() as { new_transactions: number };
      setMsg({ text: `Sync complete — ${result.new_transactions} new transactions pulled.`, ok: true });
      load();
    } catch {
      setMsg({ text: "Sync failed — check backend logs.", ok: false });
    } finally { setSyncing(false); }
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-accent" />
          <h2 className="font-semibold text-tx">Connected Accounts</h2>
          {enrollments.length > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">
              {enrollments.length} linked
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {enrollments.length > 0 && (
            <button
              onClick={handleSyncNow}
              disabled={syncing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-tx-2 hover:text-tx hover:bg-elevated border border-border transition-all disabled:opacity-50"
            >
              {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Sync all
            </button>
          )}
          <button
            onClick={openTellerLink}
            disabled={!scriptReady}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs bg-accent hover:bg-accent-h text-white transition-all disabled:opacity-50"
          >
            <Plus size={12} />
            Connect bank
          </button>
        </div>
      </div>

      {msg && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm border",
          msg.ok
            ? "bg-income/10 border-income/30 text-income"
            : "bg-expense/10 border-expense/30 text-expense"
        )}>
          {msg.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
          {msg.text}
          <button onClick={() => setMsg(null)} className="ml-auto text-xs opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2].map(i => <div key={i} className="h-14 bg-elevated rounded-xl" />)}
        </div>
      ) : enrollments.length === 0 ? (
        <div className="text-center py-8">
          <Building2 size={28} className="text-tx-3 mx-auto mb-3" />
          <p className="text-sm text-tx-2 font-medium">No accounts connected yet</p>
          <p className="text-xs text-tx-3 mt-1">Click "Connect bank" to link your first institution</p>
        </div>
      ) : (
        <div className="space-y-2">
          {enrollments.map(e => (
            <EnrollmentCard
              key={e.enrollment_id}
              enrollment={e}
              onDisconnect={handleDisconnect}
              onSync={handleSyncNow}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-tx-3 border-t border-border/50 pt-3">
        Powered by Teller · Read-only access · Transactions sync daily at 1 PM ET
      </p>
    </section>
  );
}
