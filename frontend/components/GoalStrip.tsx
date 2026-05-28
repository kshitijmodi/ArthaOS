"use client";
import { useState, useEffect } from "react";
import { Target } from "lucide-react";
import { getGoals, Goal } from "@/lib/api";
import { cn } from "@/lib/utils";

function miniColor(goal: Goal) {
  if (goal.goal_type === "spend_limit") {
    if (goal.progress_pct >= 100) return { bar: "bg-expense", text: "text-expense" };
    if (goal.progress_pct >= 75)  return { bar: "bg-warn",    text: "text-warn"   };
    return { bar: "bg-income", text: "text-income" };
  }
  if (goal.progress_pct >= 100) return { bar: "bg-income", text: "text-income" };
  if (goal.progress_pct >= 60)  return { bar: "bg-accent",  text: "text-accent" };
  return { bar: "bg-warn", text: "text-warn" };
}

export default function GoalStrip({ onNavigate }: { onNavigate: (v: "goals") => void }) {
  const [goals, setGoals] = useState<Goal[]>([]);

  useEffect(() => {
    getGoals().then(r => setGoals(r.goals.filter(g => g.status === "active").slice(0, 4)));
  }, []);

  if (goals.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target size={14} className="text-accent" />
          <h2 className="font-semibold text-tx text-sm">Goals</h2>
        </div>
        <button
          onClick={() => onNavigate("goals")}
          className="text-xs text-accent hover:text-accent-h transition-colors font-medium"
        >
          Manage →
        </button>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {goals.map(goal => {
          const { bar, text } = miniColor(goal);
          const barWidth = Math.min(goal.progress_pct, 100);
          return (
            <div
              key={goal.id}
              className="bg-surface border border-border rounded-xl p-3 cursor-pointer hover:border-accent/40 transition-colors"
              onClick={() => onNavigate("goals")}
            >
              <p className="text-xs font-medium text-tx truncate mb-2">{goal.name}</p>
              <div className="h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden mb-1.5">
                <div className={cn("h-full rounded-full transition-all", bar)} style={{ width: `${barWidth}%` }} />
              </div>
              <div className="flex items-center justify-between">
                <span className={cn("text-[10px] font-semibold", text)}>{goal.progress_pct.toFixed(0)}%</span>
                {goal.days_left !== null && (
                  <span className="text-[10px] text-tx-3">{goal.days_left}d left</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
