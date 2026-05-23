"use client";
import { useState, useEffect, useCallback } from "react";
import { Bell, X, Clock, ChevronRight } from "lucide-react";
import { getAlerts, dismissAlert, snoozeAlert, Alert } from "@/lib/api";
import { SEVERITY_COLORS, formatDate, cn } from "@/lib/utils";
import { useAlertSocket } from "@/hooks/useWebSocket";

export default function AlertsPanel() {
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

  // Real-time new alerts via WebSocket
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

  if (loading) return <PanelSkeleton />;

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Bell size={18} className="text-amber-400" />
        <h2 className="font-semibold text-white">Alerts</h2>
        {alerts.length > 0 && (
          <span className="ml-auto text-xs font-medium px-2 py-0.5 rounded-full bg-red-500/20 text-red-400">
            {alerts.length} unread
          </span>
        )}
      </div>

      {alerts.length === 0 ? (
        <p className="text-sm text-white/40 py-4 text-center">No unread alerts</p>
      ) : (
        <ul className="space-y-3">
          {alerts.map(alert => (
            <li
              key={alert.id}
              className={cn(
                "rounded-lg border p-3 flex gap-3 items-start",
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
                  className="p-1 rounded hover:bg-white/10 transition-colors"
                >
                  <Clock size={14} />
                </button>
                <button
                  onClick={() => handleDismiss(alert.id)}
                  title="Dismiss"
                  className="p-1 rounded hover:bg-white/10 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PanelSkeleton() {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5 animate-pulse">
      <div className="h-4 bg-white/10 rounded w-24 mb-4" />
      {[1,2,3].map(i => <div key={i} className="h-14 bg-white/10 rounded mb-2" />)}
    </section>
  );
}
