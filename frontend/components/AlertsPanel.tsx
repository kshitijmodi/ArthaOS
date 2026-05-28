"use client";
import { useState, useEffect, useCallback } from "react";
import { Bell, X, Clock, Copy, TrendingUp, AlertTriangle, Zap, BarChart2, CreditCard, RefreshCw } from "lucide-react";
import { getAlerts, dismissAlert, snoozeAlert, Alert } from "@/lib/api";
import { SEVERITY_COLORS, formatDate, cn } from "@/lib/utils";
import { useAlertSocket } from "@/hooks/useWebSocket";

const ALERT_TYPE_META: Record<string, { label: string; icon: React.ReactNode }> = {
  overspend:        { label: "Overspend",          icon: <TrendingUp size={13} /> },
  anomaly:          { label: "Anomalies",           icon: <AlertTriangle size={13} /> },
  duplicate:        { label: "Duplicate Charges",   icon: <Copy size={13} /> },
  budget_overrun:   { label: "Budget Overrun",      icon: <BarChart2 size={13} /> },
  card_due:         { label: "Card Payments Due",   icon: <CreditCard size={13} /> },
  missing_charge:   { label: "Missing Charges",     icon: <Zap size={13} /> },
  recurring_change: { label: "Recurring Changes",   icon: <RefreshCw size={13} /> },
};

function groupByType(alerts: Alert[]): [string, Alert[]][] {
  const order = ["anomaly", "duplicate", "overspend", "budget_overrun", "card_due", "missing_charge", "recurring_change"];
  const map = new Map<string, Alert[]>();
  for (const a of alerts) {
    const key = a.alert_type ?? "other";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(a);
  }
  const sorted: [string, Alert[]][] = [];
  for (const k of order) if (map.has(k)) sorted.push([k, map.get(k)!]);
  for (const [k, v] of map) if (!order.includes(k)) sorted.push([k, v]);
  return sorted;
}

interface AlertsPanelProps {
  alertTypes?: string[];
}

export default function AlertsPanel({ alertTypes = [] }: AlertsPanelProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await getAlerts("unread");
      setAlerts(res.alerts);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useAlertSocket(useCallback((newAlert: unknown) => {
    setAlerts(prev => [newAlert as Alert, ...prev]);
  }, []));

  const handleDismiss = async (id: number) => {
    await dismissAlert(id);
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  const handleSnooze = async (id: number) => {
    await snoozeAlert(id, 3);
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  if (loading) return (
    <div className="rounded-2xl border border-border bg-surface p-5 animate-pulse space-y-3">
      <div className="h-4 bg-elevated rounded w-24" />
      {[1, 2, 3].map(i => <div key={i} className="h-14 bg-elevated rounded-xl" />)}
    </div>
  );

  const visibleAlerts = alertTypes.length > 0
    ? alerts.filter(a => alertTypes.includes((a.alert_type ?? "") as never))
    : alerts;
  const groups = groupByType(visibleAlerts);

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2 mb-4">
        <Bell size={16} className="text-warn" />
        <h2 className="font-semibold text-tx">Alerts</h2>
        {visibleAlerts.length > 0 && (
          <span className="ml-auto text-xs font-semibold px-2 py-0.5 rounded-full bg-expense/10 text-expense border border-expense/20">
            {visibleAlerts.length} unread
          </span>
        )}
      </div>

      {visibleAlerts.length === 0 ? (
        <p className="text-sm text-tx-3 py-6 text-center">
          {alerts.length === 0 ? "No unread alerts — all clear" : "No alerts match the selected filter"}
        </p>
      ) : (
        <div className="space-y-4">
          {groups.map(([type, typeAlerts]) => {
            const meta = ALERT_TYPE_META[type];
            return (
              <div key={type}>
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="text-tx-3">{meta?.icon ?? <Bell size={13} />}</span>
                  <span className="text-xs font-semibold uppercase tracking-wide text-tx-3">
                    {meta?.label ?? type}
                  </span>
                  <span className="text-xs text-tx-3 opacity-60">({typeAlerts.length})</span>
                </div>
                <ul className="space-y-2.5">
                  {typeAlerts.map(alert => (
                    <li
                      key={alert.id}
                      className={cn(
                        "rounded-xl border p-3.5 flex gap-3 items-start",
                        SEVERITY_COLORS[alert.severity]
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium leading-snug">{alert.description}</p>
                        <p className="text-xs opacity-60 mt-1">{formatDate(alert.created_at)}</p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button
                          onClick={() => handleSnooze(alert.id)}
                          title="Snooze 3 days"
                          className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                        >
                          <Clock size={13} />
                        </button>
                        <button
                          onClick={() => handleDismiss(alert.id)}
                          title="Dismiss"
                          className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                        >
                          <X size={13} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
