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
  positive: "border-green-500/30 bg-green-500/10 text-green-300",
  warning:  "border-amber-500/30 bg-amber-500/10 text-amber-300",
  neutral:  "border-white/10 bg-white/5 text-white/70",
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

  // Affordability tool
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
    } catch (e) {
      console.error(e);
    } finally {
      setChecking(false);
    }
  };

  if (loading) return <InsightsSkeleton />;

  return (
    <section className="space-y-6">
      {/* Recommendations */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h3 className="font-semibold text-white mb-4">Financial Health</h3>
        <div className="space-y-3">
          {recs.map((rec, i) => (
            <div key={i} className={cn("rounded-lg border p-4 flex gap-3", SEV_STYLES[rec.severity])}>
              <span className="shrink-0 mt-0.5">{SEV_ICON[rec.severity]}</span>
              <div>
                <p className="font-medium text-sm mb-1">{rec.title}</p>
                <p className="text-sm opacity-80 leading-relaxed">{rec.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Affordability tool */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Calculator size={16} className="text-blue-400" />
          <h3 className="font-semibold text-white">Affordability Check</h3>
        </div>
        <div className="flex gap-3 mb-4">
          <div className="flex-1 relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">₹</span>
            <input
              type="text"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              onKeyDown={e => e.key === "Enter" && checkAffordability()}
              placeholder="Enter amount…"
              className="w-full bg-white/10 border border-white/10 rounded-lg pl-8 pr-4 py-2.5 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
            />
          </div>
          <button
            onClick={checkAffordability}
            disabled={checking || !amount}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg text-sm text-white transition-colors flex items-center gap-2"
          >
            {checking && <RefreshCw size={13} className="animate-spin" />}
            Check
          </button>
        </div>

        {affordResult && (
          <div className={cn(
            "rounded-lg border p-4",
            affordResult.affordable
              ? "border-green-500/30 bg-green-500/10"
              : "border-amber-500/30 bg-amber-500/10"
          )}>
            <div className="flex items-center gap-2 mb-2">
              {affordResult.affordable
                ? <CheckCircle size={16} className="text-green-400" />
                : <AlertTriangle size={16} className="text-amber-400" />}
              <span className={cn("font-semibold text-sm", affordResult.affordable ? "text-green-300" : "text-amber-300")}>
                {affordResult.affordable ? "Affordable" : "May be a stretch"}
              </span>
              <span className="ml-auto text-xs text-white/40">Confidence: {affordResult.confidence}</span>
            </div>
            <p className="text-sm text-white/80 leading-relaxed">{affordResult.explanation}</p>
            <div className="grid grid-cols-3 gap-4 mt-3 pt-3 border-t border-white/10">
              <Stat label="Monthly income" value={formatCurrency(affordResult.avg_monthly_income)} />
              <Stat label="Spent this month" value={formatCurrency(affordResult.this_month_spend)} />
              <Stat label="Available" value={formatCurrency(affordResult.remaining_budget)} />
            </div>
          </div>
        )}
      </div>

      {/* Spend optimisation */}
      {suggestions.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown size={16} className="text-purple-400" />
            <h3 className="font-semibold text-white">Optimisation Opportunities</h3>
            <span className="ml-auto text-xs text-white/40">
              Potential saving: {formatCurrency(suggestions.reduce((a, s) => a + s.potential_saving, 0))}/mo
            </span>
          </div>
          <div className="space-y-3">
            {suggestions.map(s => (
              <div key={s.category} className="rounded-lg border border-white/10 bg-white/5 p-4">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <span className="font-medium text-white text-sm">{s.category}</span>
                    <span className="ml-2 text-xs text-white/40">
                      Avg ₹{s.current_avg.toLocaleString("en-IN")} → target ₹{s.suggested_target.toLocaleString("en-IN")}
                    </span>
                  </div>
                  <span className="text-green-400 text-sm font-medium whitespace-nowrap shrink-0">
                    Save {formatCurrency(s.potential_saving)}/mo
                  </span>
                </div>
                {/* Progress bar */}
                <div className="h-1.5 bg-white/10 rounded-full mb-3">
                  <div
                    className="h-full bg-purple-500 rounded-full"
                    style={{ width: `${Math.min(100, (s.suggested_target / s.current_avg) * 100)}%` }}
                  />
                </div>
                <p className="text-xs text-white/50">{s.tip}</p>
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
      <p className="text-xs text-white/40 mb-0.5">{label}</p>
      <p className="text-sm font-medium text-white">{value}</p>
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <section className="space-y-6 animate-pulse">
      {[1, 2, 3].map(i => (
        <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-5 h-40" />
      ))}
    </section>
  );
}
