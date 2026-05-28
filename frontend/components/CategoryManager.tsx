"use client";
import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2, Check, X, Tag } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Category {
  id: number;
  name: string;
  keywords: string;
  is_system: number;
}

export default function CategoryManager() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editKeywords, setEditKeywords] = useState("");
  const [newName, setNewName] = useState("");
  const [newKeywords, setNewKeywords] = useState("");
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () =>
    apiFetch<{ categories: Category[] }>("/categories")
      .then(r => setCategories(r.categories))
      .catch(console.error)
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const startEdit = (cat: Category) => {
    setEditId(cat.id); setEditName(cat.name); setEditKeywords(cat.keywords);
  };
  const cancelEdit = () => setEditId(null);

  const saveEdit = async (id: number) => {
    setSaving(true);
    try {
      await apiFetch(`/categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: editName, keywords: editKeywords }),
      });
      setEditId(null); load();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  const deleteCategory = async (cat: Category) => {
    if (cat.is_system === 1) {
      if (!confirm(`"${cat.name}" is a built-in category. Transactions assigned to it will keep the label but the category won't appear in filters. Delete anyway?`)) return;
    }
    await apiFetch(`/categories/${cat.id}`, { method: "DELETE" });
    load();
  };

  const addCategory = async () => {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      await apiFetch("/categories", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), keywords: newKeywords.trim() }),
      });
      setNewName(""); setNewKeywords(""); setAdding(false); load();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  if (loading) return (
    <div className="rounded-2xl border border-border bg-surface p-5 animate-pulse h-40" />
  );

  const inputCls = "w-full bg-bg border border-border rounded-xl px-3 py-2 text-sm text-tx placeholder:text-tx-3 focus:outline-none focus:border-accent/50 transition-colors";

  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2 mb-5">
        <Tag size={16} className="text-accent" />
        <h3 className="font-semibold text-tx">Categories</h3>
        <span className="text-xs text-tx-3">({categories.length})</span>
        <button
          onClick={() => setAdding(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-accent hover:bg-accent-h rounded-xl text-xs text-white transition-colors"
        >
          <Plus size={13} /> Add
        </button>
      </div>

      {adding && (
        <div className="mb-4 p-4 rounded-xl border border-accent/30 bg-accent/5 space-y-3">
          <p className="text-xs text-tx-2 font-semibold">New category</p>
          <input autoFocus value={newName} onChange={e => setNewName(e.target.value)} placeholder="Name" className={inputCls} />
          <input value={newKeywords} onChange={e => setNewKeywords(e.target.value)} placeholder="Keywords (comma-separated)" className={inputCls} />
          <div className="flex gap-2">
            <button
              onClick={addCategory}
              disabled={saving || !newName.trim()}
              className="px-3 py-1.5 bg-accent hover:bg-accent-h disabled:opacity-40 rounded-lg text-xs text-white flex items-center gap-1"
            >
              <Check size={12} /> Save
            </button>
            <button
              onClick={() => { setAdding(false); setNewName(""); setNewKeywords(""); }}
              className="px-3 py-1.5 bg-elevated hover:bg-border rounded-lg text-xs text-tx-2 flex items-center gap-1"
            >
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {categories.map(cat => (
          <div key={cat.id} className="rounded-xl border border-border bg-elevated p-3.5">
            {editId === cat.id ? (
              <div className="space-y-2">
                <input autoFocus value={editName} onChange={e => setEditName(e.target.value)} className={inputCls} />
                <input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} placeholder="Keywords (comma-separated)" className={inputCls} />
                <div className="flex gap-2">
                  <button
                    onClick={() => saveEdit(cat.id)}
                    disabled={saving}
                    className="px-2.5 py-1 bg-accent hover:bg-accent-h disabled:opacity-40 rounded-lg text-xs text-white flex items-center gap-1"
                  >
                    <Check size={11} /> Save
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="px-2.5 py-1 bg-surface hover:bg-border rounded-lg text-xs text-tx-2 flex items-center gap-1"
                  >
                    <X size={11} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-tx">{cat.name}</span>
                    {cat.is_system === 1 && (
                      <span className="text-[10px] text-tx-3 border border-border rounded px-1.5 py-0.5">system</span>
                    )}
                  </div>
                  {cat.keywords && (
                    <p className="text-xs text-tx-3 mt-0.5 truncate">{cat.keywords}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => startEdit(cat)}
                    className="p-1.5 text-tx-3 hover:text-tx-2 transition-colors rounded-lg"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => deleteCategory(cat)}
                    className="p-1.5 text-tx-3 hover:text-expense transition-colors rounded-lg"
                    title={cat.is_system ? "Delete system category" : "Delete"}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-xs text-tx-3 mt-4">
        Keywords are used for automatic transaction matching. Deleting a system category will ask for confirmation.
      </p>
    </section>
  );
}
