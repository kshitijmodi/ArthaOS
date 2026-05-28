"use client";
import { useState, useEffect, useCallback } from "react";
import { Target, Plus, Trash2, X, Check, TrendingUp, PiggyBank, CreditCard, Pencil } from "lucide-react";
import { getGoals, createGoal, updateGoal, deleteGoal, Goal } from "@/lib/api";
import { cn, CATEGORIES } from "@/lib/utils";

const GOAL_TYPE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  spend_limit:  { label: "Spend Limit",  icon: <CreditCard size={13} />, color: "text-expense" },
  savings:      { label: "Savings",      icon: <PiggyBank size={13} />,  color: "text-income"  },
  investment:   { label: "Investment",   icon: <TrendingUp size={13} />, color: "text-accent"  },
  custom:       { label: "Custom",       icon: <Target size={13} />,     color: "text-tx-2"    },
};

function progressColor(goal: Goal): string {
  if (goal.goal_type === "spend_limit") {
    if (goal.progress_pct >= 100) return "bg-expense";
    if (goal.progress_pct >= 75)  return "bg-warn";
    return "bg-income";
  }
  if (goal.progress_pct >= 100) return "bg-income";
  if (goal.progress_pct >= 60)  return "bg-accent";
  return "bg-warn";
}

function progressBarBg(goal: Goal): string {
  if (goal.goal_type === "spend_limit") {
    if (goal.progress_pct >= 100) return "bg-expense/15 border-expense/20";
    if (goal.progress_pct >= 75)  return "bg-warn/10 border-warn/20";
    return "bg-income/10 border-income/20";
  }
  if (goal.progress_pct >= 100) return "bg-income/10 border-income/20";
  return "bg-surface border-border";
}

const BLANK_FORM = {
  name: "", goal_type: "spend_limit", category: "",
  target_amount: "", target_date: "", period: "monthly", notes: "",
};

export default function GoalsPanel() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(BLANK_FORM);
  const [saving, setSaving] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await getGoals();
      setGoals(res.goals);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.target_amount) return;
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        goal_type: form.goal_type,
        category: form.category || undefined,
        target_amount: parseFloat(form.target_amount),
        target_date: form.target_date || undefined,
        period: form.period,
        notes: form.notes || undefined,
      };
      if (editId !== null) {
        const updated = await updateGoal(editId, payload);
        setGoals(prev => prev.map(g => g.id === editId ? updated : g));
      } else {
        const created = await createGoal(payload);
        setGoals(prev => [created, ...prev]);
      }
      setForm(BLANK_FORM);
      setShowForm(false);
      setEditId(null);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    await deleteGoal(id);
    setGoals(prev => prev.filter(g => g.id !== id));
  };

  const handleEdit = (goal: Goal) => {
    setForm({
      name: goal.name,
      goal_type: goal.goal_type,
      category: goal.category ?? "",
      target_amount: String(goal.target_amount),
      target_date: goal.target_date ?? "",
      period: goal.period,
      notes: goal.notes ?? "",
    });
    setEditId(goal.id);
    setShowForm(true);
  };

  const handleComplete = async (goal: Goal) => {
    const updated = await updateGoal(goal.id, { status: "completed" });
    setGoals(prev => prev.map(g => g.id === goal.id ? updated : g));
  };

  if (loading) return (
    <div className="space-y-3 animate-pulse">
      {[1, 2].map(i => <div key={i} className="h-24 bg-elevated rounded-2xl border border-border" />)}
    </div>
  );

  const active = goals.filter(g => g.status === "active");
  const completed = goals.filter(g => g.status === "completed");

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target size={16} className="text-accent" />
          <h2 className="font-semibold text-tx">Goals</h2>
          {active.length > 0 && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">
              {active.length} active
            </span>
          )}
        </div>
        <button
          onClick={() => { setShowForm(s => !s); setEditId(null); setForm(BLANK_FORM); }}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-xl bg-accent text-white hover:bg-accent-h transition-colors"
        >
          <Plus size={13} />
          Add Goal
        </button>
      </div>

      {/* Add / Edit Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-2xl p-4 space-y-3">
          <p className="text-sm font-semibold text-tx">{editId ? "Edit Goal" : "New Goal"}</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <input
                className="w-full bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx placeholder:text-tx-3 focus:outline-none focus:border-accent"
                placeholder="Goal name (e.g. Keep dining under $400)"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>
            <select
              className="bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx focus:outline-none focus:border-accent"
              value={form.goal_type}
              onChange={e => setForm(f => ({ ...f, goal_type: e.target.value }))}
            >
              <option value="spend_limit">Spend Limit</option>
              <option value="savings">Savings</option>
              <option value="investment">Investment</option>
              <option value="custom">Custom</option>
            </select>
            <select
              className="bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx focus:outline-none focus:border-accent"
              value={form.period}
              onChange={e => setForm(f => ({ ...f, period: e.target.value }))}
            >
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
              <option value="one_time">One-time</option>
            </select>
            {form.goal_type === "spend_limit" && (
              <select
                className="bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx focus:outline-none focus:border-accent"
                value={form.category}
                onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
              >
                <option value="">All categories</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
            <input
              type="number"
              min="1"
              step="any"
              className="bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx placeholder:text-tx-3 focus:outline-none focus:border-accent"
              placeholder="Target amount ($)"
              value={form.target_amount}
              onChange={e => setForm(f => ({ ...f, target_amount: e.target.value }))}
              required
            />
            {form.period === "one_time" && (
              <input
                type="date"
                className="bg-elevated border border-border rounded-xl px-3 py-2 text-sm text-tx focus:outline-none focus:border-accent"
                value={form.target_date}
                onChange={e => setForm(f => ({ ...f, target_date: e.target.value }))}
              />
            )}
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => { setShowForm(false); setEditId(null); setForm(BLANK_FORM); }}
              className="px-3 py-1.5 text-xs text-tx-2 hover:text-tx rounded-xl hover:bg-elevated transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-1.5 text-xs font-medium bg-accent text-white rounded-xl hover:bg-accent-h disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving…" : editId ? "Save Changes" : "Create Goal"}
            </button>
          </div>
        </form>
      )}

      {/* Active Goals */}
      {active.length === 0 && !showForm ? (
        <div className="text-center py-10 text-sm text-tx-3 bg-surface border border-border rounded-2xl">
          No active goals — click <span className="text-accent font-medium">Add Goal</span> to set one
        </div>
      ) : (
        <div className="space-y-3">
          {active.map(goal => <GoalCard key={goal.id} goal={goal} onEdit={handleEdit} onDelete={handleDelete} onComplete={handleComplete} />)}
        </div>
      )}

      {/* Completed Goals */}
      {completed.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold text-tx-3 hover:text-tx-2 transition-colors list-none flex items-center gap-1.5 py-1">
            <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
            {completed.length} completed goal{completed.length > 1 ? "s" : ""}
          </summary>
          <div className="mt-2 space-y-2 opacity-60">
            {completed.map(goal => <GoalCard key={goal.id} goal={goal} onEdit={handleEdit} onDelete={handleDelete} onComplete={handleComplete} />)}
          </div>
        </details>
      )}
    </div>
  );
}

function GoalCard({ goal, onEdit, onDelete, onComplete }: {
  goal: Goal;
  onEdit: (g: Goal) => void;
  onDelete: (id: number) => void;
  onComplete: (g: Goal) => void;
}) {
  const meta = GOAL_TYPE_META[goal.goal_type];
  const barWidth = Math.min(goal.progress_pct, 100);
  const isSpendLimit = goal.goal_type === "spend_limit";

  const statusLabel = () => {
    if (goal.status === "completed") return "✓ Completed";
    if (isSpendLimit) {
      if (goal.progress_pct >= 100) return "⚠ Limit exceeded";
      if (goal.progress_pct >= 75) return "⚠ Approaching limit";
      return "✓ On track";
    }
    if (goal.on_track) return "✓ On track";
    return "Behind pace";
  };

  const statusColor = () => {
    if (goal.status === "completed") return "text-income";
    if (isSpendLimit) {
      if (goal.progress_pct >= 100) return "text-expense";
      if (goal.progress_pct >= 75) return "text-warn";
      return "text-income";
    }
    return goal.on_track ? "text-income" : "text-warn";
  };

  return (
    <div className={cn("rounded-2xl border p-4", progressBarBg(goal))}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={cn("shrink-0", meta.color)}>{meta.icon}</span>
            <p className="text-sm font-semibold text-tx truncate">{goal.name}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] bg-elevated text-tx-2 px-1.5 py-0.5 rounded-full border border-border/50">
              {meta.label}
            </span>
            {goal.category && (
              <span className="text-[10px] bg-elevated text-tx-2 px-1.5 py-0.5 rounded-full border border-border/50">
                {goal.category}
              </span>
            )}
            <span className={cn("text-[10px] font-medium", statusColor())}>{statusLabel()}</span>
          </div>
        </div>
        {goal.status === "active" && (
          <div className="flex gap-1 shrink-0">
            <button onClick={() => onEdit(goal)} className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 text-tx-3 hover:text-tx transition-colors" title="Edit">
              <Pencil size={12} />
            </button>
            <button onClick={() => onComplete(goal)} className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 text-tx-3 hover:text-income transition-colors" title="Mark complete">
              <Check size={12} />
            </button>
            <button onClick={() => onDelete(goal.id)} className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 text-tx-3 hover:text-expense transition-colors" title="Delete">
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden mb-2">
        <div
          className={cn("h-full rounded-full transition-all duration-500", progressColor(goal))}
          style={{ width: `${barWidth}%` }}
        />
      </div>

      {/* Numbers row */}
      <div className="flex items-center justify-between text-xs text-tx-2">
        <span>
          {isSpendLimit
            ? <>${goal.current_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })} <span className="text-tx-3">/ ${goal.target_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })} limit</span></>
            : <>${goal.current_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })} <span className="text-tx-3">of ${goal.target_amount.toLocaleString(undefined, { maximumFractionDigits: 0 })} goal</span></>
          }
        </span>
        <span className="tabular-nums">
          {goal.progress_pct.toFixed(0)}%
          {goal.days_left !== null && (
            <span className="text-tx-3 ml-1">· {goal.days_left}d left</span>
          )}
        </span>
      </div>
    </div>
  );
}
