"use client";
import { useState, useEffect } from "react";
import { TrendingDown, CheckCircle, AlertTriangle, Info, Calculator, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

interface Suggestion {
  category: string;
  current_avg: number;
  benchmark_pct: number;
  suggested_target: number;
  potential_saving: number;
  tip: string;
}

interface Recommendation {
  type: string;
  title: string;
  body: string;
  severity: "positive" | "neutral" | "warning";
}

interface AffordabilityResult {
  affordable: boolean;
  confidence: string;
  remaining_budget: number;
  avg_monthly_income: number;
  this_month_spend: number;
  explanation: string;
}

const SEV_STYLES = {
  positive: "border-income/30 bg-income/10 text-income",
  warning:  "border-warn/30 bg-warn/10 text-warn",
  neutral:  "border-border bg-elevated text-tx-2",
};

const SEV_ICON = {
  positive: <CheckCircle size={15} />,
  warning:  <AlertTriangle size={15} />,
  neutral:  <Info size={15} />,
};

export default function InsightsPanel() {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState("");
  const [affordResult, setAffordResult] = useState<AffordabilityResult | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch<{ suggestions: Suggestion[] }>("/insights/optimisation"),
      apiFetch<{ recommendations: Recommendation[] }>("/insights/recommendations"),
    ]).then(([o, r]) => {
      setSuggestions(o.suggestions);
      setRecs(r.recommendations);
    }).catch(console.error).finally(() => setLoading(false));
  }, []);

  const checkAffordability = async () => {
    const num = parseFloat(amount.replace(/,/g, ""));
    if (!num || num <= 0) return;
    setChecking(true);
    try {
      const res = await apiFetch<AffordabilityResult>("/insights/affordability", {
        method: "POST",
        body: JSON.stringify({ amount: num }),
      });
      setAffordResult(res);
    } catch (e) { console.error(e); }
    finally { setChecking(false); }
  };

  if (loading) return (
    <section className="space-y-4 animate-pulse">
      {[1, 2, 3].map(i => <div key={i} className="rounded-2xl border border-border bg-surface p-5 h-36" />)}
    </section>
  );

  return (
    <section className="space-y-5">
      {/* Recommendations */}
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h3 className="font-semibold text-tx mb-4">Financial Health</h3>
        <div className="space-y-2.5">
          {recs.map((rec, i) => (
            <div key={i} className={cn("rounded-xl border p-4 flex gap-3", SEV_STYLES[rec.severity])}>
              <span className="shrink-0 mt-0.5">{SEV_ICON[rec.severity]}</span>
              <div>
                <p className="font-semibold text-sm mb-1">{rec.title}</p>
                <p className="text-sm opacity-80 leading-relaxed">{rec.body}</p>
              </div>
            </div>
          ))}
          {recs.length === 0 && (
            <p className="text-sm text-tx-3 text-center py-4">No recommendations yet — ingest more statements</p>
          )}
        </div>
      </div>

      {/* Affordability tool */}
      <div className="rounded-2xl border border-border bg-surface p-5">
        <div className="flex items-center gap-2 mb-4">
          <Calculator size={16} className="text-savings" />
          <h3 className="font-semibold text-tx">Affordability Check</h3>
        </div>
        <div className="flex gap-3 mb-4">
          <div className="flex-1 relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-3 text-sm">$</span>
            <input
              type="text"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              onKeyDown={e => e.key === "Enter" && checkAffordability()}
              placeholder="Enter amount…"
              className="w-full bg-elevated border border-border rounded-xl pl-8 pr-4 py-2.5 text-sm text-tx placeholder:text-tx-3 focus:outline-none focus:border-accent/50"
            />
          </div>
          <button
            onClick={checkAffordability}
            disabled={checking || !amount}
            className="px-4 py-2.5 bg-accent hover:bg-accent-h disabled:opacity-40 rounded-xl text-sm text-white transition-colors flex items-center gap-2"
          >
            {checking && <RefreshCw size={13} className="animate-spin" />}
            Check
          </button>
        </div>

        {affordResult && (
          <div className={cn(
            "rounded-xl border p-4",
            affordResult.affordable ? "border-income/30 bg-income/10" : "border-warn/30 bg-warn/10"
          )}>
            <div className="flex items-center gap-2 mb-2">
              {affordResult.affordable
                ? <CheckCircle size={16} className="text-income" />
                : <AlertTriangle size={16} className="text-warn" />}
              <span className={cn("font-semibold text-sm", affordResult.affordable ? "text-income" : "text-warn")}>
                {affordResult.affordable ? "Affordable" : "May be a stretch"}
              </span>
              <span className="ml-auto text-xs text-tx-3">Confidence: {affordResult.confidence}</span>
            </div>
            <p className="text-sm text-tx leading-relaxed">{affordResult.explanation}</p>
            <div className="grid grid-cols-3 gap-4 mt-3 pt-3 border-t border-border/50">
              <Stat label="Monthly income" value={formatCurrency(affordResult.avg_monthly_income)} />
              <Stat label="Spent this month" value={formatCurrency(affordResult.this_month_spend)} />
              <Stat label="Available" value={formatCurrency(affordResult.remaining_budget)} />
            </div>
          </div>
        )}
      </div>

      {/* Optimisation */}
      {suggestions.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown size={16} className="text-accent" />
            <h3 className="font-semibold text-tx">Optimisation Opportunities</h3>
            <span className="ml-auto text-xs text-tx-3">
              Potential: {formatCurrency(suggestions.reduce((a, s) => a + s.potential_saving, 0))}/mo
            </span>
          </div>
          <div className="space-y-3">
            {suggestions.map(s => (
              <div key={s.category} className="rounded-xl border border-border bg-elevated p-4">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <span className="font-semibold text-tx text-sm">{s.category}</span>
                    <span className="ml-2 text-xs text-tx-3">
                      avg ${s.current_avg.toLocaleString()} → target ${s.suggested_target.toLocaleString()}
                    </span>
                  </div>
                  <span className="text-income text-sm font-semibold whitespace-nowrap shrink-0">
                    Save {formatCurrency(s.potential_saving)}/mo
                  </span>
                </div>
                <div className="h-1.5 bg-border rounded-full mb-3">
                  <div
                    className="h-full bg-accent rounded-full"
                    style={{ width: `${Math.min(100, (s.suggested_target / s.current_avg) * 100)}%` }}
                  />
                </div>
                <p className="text-xs text-tx-2">{s.tip}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-tx-3 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-tx">{value}</p>
    </div>
  );
}
