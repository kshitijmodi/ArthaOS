"use client";
import { useState, useEffect, useCallback } from "react";
import { usePlaidLink } from "react-plaid-link";
import {
  Landmark, RefreshCw, Trash2, Plus, CheckCircle,
  AlertCircle, Loader2, RotateCcw, ChevronDown,
} from "lucide-react";
import {
  getPlaidLinkToken, plaidExchange, getPlaidItems, plaidDisconnect,
  plaidSyncNow, plaidResync, PlaidItem, PlaidAccount,
} from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

function AccountRow({ account }: { account: PlaidAccount }) {
  const balance = account.balance_available ?? account.balance_current;
  const isLoan   = account.type === "loan";
  const isCredit = account.type === "credit";
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-elevated transition-colors">
      <div>
        <p className="text-sm font-medium text-tx">{account.name}</p>
        <p className="text-xs text-tx-3 capitalize">
          {account.type}{account.subtype ? ` · ${account.subtype}` : ""}
        </p>
      </div>
      <div className="text-right">
        {balance != null ? (
          <p className={cn("text-sm font-semibold",
            isLoan || isCredit ? "text-expense" : "text-tx"
          )}>
            {isLoan || isCredit ? "−" : ""}{formatCurrency(balance)}
          </p>
        ) : (
          <p className="text-xs text-tx-3">—</p>
        )}
      </div>
    </div>
  );
}

function ItemCard({
  item, onDisconnect, onSync,
}: {
  item: PlaidItem;
  onDisconnect: (id: string) => void;
  onSync: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const totalBalance = item.accounts.reduce((s, a) => {
    const b = a.balance_available ?? a.balance_current ?? 0;
    return s + (a.type === "loan" || a.type === "credit" ? -Math.abs(b) : Math.abs(b));
  }, 0);

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-elevated transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center shrink-0">
          <Landmark size={14} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-tx">{item.institution}</p>
          <p className="text-xs text-tx-3">
            {item.accounts.length} account{item.accounts.length !== 1 ? "s" : ""}
            {item.last_synced_at && (
              <> · last synced {new Date(item.last_synced_at).toLocaleDateString()}</>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("text-sm font-semibold", totalBalance < 0 ? "text-expense" : "text-tx")}>
            {totalBalance < 0 ? "−" : ""}{formatCurrency(Math.abs(totalBalance))}
          </span>
          <span className={cn("w-2 h-2 rounded-full",
            item.status === "active" ? "bg-income" : "bg-tx-3"
          )} />
          <ChevronDown size={14} className={cn("text-tx-3 transition-transform", expanded && "rotate-180")} />
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-1">
          {item.accounts.map(a => <AccountRow key={a.account_id} account={a} />)}
          <div className="flex items-center gap-2 pt-2 mt-1 border-t border-border/50">
            <button
              onClick={onSync}
              className="flex items-center gap-1.5 text-xs text-tx-2 hover:text-tx px-2 py-1.5 rounded-lg hover:bg-elevated transition-colors"
            >
              <RefreshCw size={12} /> Sync now
            </button>
            <button
              onClick={() => onDisconnect(item.item_id)}
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

function PlaidLinkButton({
  onSuccess,
  disabled,
}: {
  onSuccess: (publicToken: string, institutionId: string, institutionName: string) => void;
  disabled?: boolean;
}) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);

  const fetchToken = useCallback(async () => {
    setFetching(true);
    try {
      const { link_token } = await getPlaidLinkToken();
      setLinkToken(link_token);
    } catch {
      setLinkToken(null);
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => { fetchToken(); }, [fetchToken]);

  const { open, ready } = usePlaidLink({
    token: linkToken ?? "",
    onSuccess: (public_token, metadata) => {
      const inst = metadata.institution;
      onSuccess(public_token, inst?.institution_id ?? "", inst?.name ?? "Unknown");
    },
  });

  return (
    <button
      onClick={() => open()}
      disabled={disabled || !ready || fetching || !linkToken}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs bg-accent hover:bg-accent-h text-white transition-all disabled:opacity-50"
    >
      {fetching ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
      Connect via Plaid
    </button>
  );
}

export default function PlaidConnect() {
  const [items, setItems]     = useState<PlaidItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [msg, setMsg]         = useState<{ text: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getPlaidItems();
      setItems(data.items.filter(i => i.status === "active"));
    } catch { /* no items yet */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSuccess = async (publicToken: string, institutionId: string, institutionName: string) => {
    try {
      await plaidExchange(publicToken, institutionId, institutionName);
      setMsg({ text: `${institutionName} connected — syncing now…`, ok: true });
      setTimeout(load, 4000);
    } catch {
      setMsg({ text: "Failed to save connection — try again.", ok: false });
    }
  };

  const handleDisconnect = async (itemId: string) => {
    if (!confirm("Disconnect this institution? Existing transactions stay but no new data will sync.")) return;
    try {
      await plaidDisconnect(itemId);
      setItems(prev => prev.filter(i => i.item_id !== itemId));
      setMsg({ text: "Institution disconnected.", ok: true });
    } catch {
      setMsg({ text: "Disconnect failed — check backend logs.", ok: false });
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await plaidSyncNow() as { new_transactions: number };
      setMsg({ text: `Sync complete — ${result.new_transactions} new transactions.`, ok: true });
      load();
    } catch {
      setMsg({ text: "Sync failed — check backend logs.", ok: false });
    } finally { setSyncing(false); }
  };

  const handleResync = async () => {
    if (!confirm("Re-sync from scratch? This deletes all Plaid transactions and re-imports them fresh.")) return;
    setSyncing(true);
    try {
      const result = await plaidResync() as { deleted: number; new_transactions: number };
      setMsg({ text: `Re-sync complete — deleted ${result.deleted}, imported ${result.new_transactions}.`, ok: true });
      load();
    } catch {
      setMsg({ text: "Re-sync failed — check backend logs.", ok: false });
    } finally { setSyncing(false); }
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Landmark size={16} className="text-accent" />
          <h2 className="font-semibold text-tx">Plaid Connections</h2>
          {items.length > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">
              {items.length} linked
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {items.length > 0 && (
            <>
              <button
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-tx-2 hover:text-tx hover:bg-elevated border border-border transition-all disabled:opacity-50"
              >
                {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                Sync all
              </button>
              <button
                onClick={handleResync}
                disabled={syncing}
                title="Delete all Plaid transactions and re-import from scratch"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-tx-2 hover:text-tx hover:bg-elevated border border-border transition-all disabled:opacity-50"
              >
                <RotateCcw size={12} />
                Re-sync
              </button>
            </>
          )}
          <PlaidLinkButton onSuccess={handleSuccess} disabled={syncing} />
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
      ) : items.length === 0 ? (
        <div className="text-center py-8">
          <Landmark size={28} className="text-tx-3 mx-auto mb-3" />
          <p className="text-sm text-tx-2 font-medium">No Plaid accounts connected yet</p>
          <p className="text-xs text-tx-3 mt-1">Click "Connect via Plaid" to link Bilt, Fidelity, Schwab, Robinhood, and more</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <ItemCard
              key={item.item_id}
              item={item}
              onDisconnect={handleDisconnect}
              onSync={handleSync}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-tx-3 border-t border-border/50 pt-3">
        Powered by Plaid · Read-only access · Investments + loans supported · Syncs every 30 min
      </p>
    </section>
  );
}
