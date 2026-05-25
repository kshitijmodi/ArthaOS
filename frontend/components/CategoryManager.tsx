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
    setEditId(cat.id);
    setEditName(cat.name);
    setEditKeywords(cat.keywords);
  };

  const cancelEdit = () => setEditId(null);

  const saveEdit = async (id: number) => {
    setSaving(true);
    try {
      await apiFetch(`/categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: editName, keywords: editKeywords }),
      });
      setEditId(null);
      load();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  const deleteCategory = async (id: number) => {
    await apiFetch(`/categories/${id}`, { method: "DELETE" });
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
      setNewName("");
      setNewKeywords("");
      setAdding(false);
      load();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  if (loading) return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5 animate-pulse h-40" />
  );

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <div className="flex items-center gap-2 mb-5">
          <Tag size={16} className="text-blue-400" />
          <h3 className="font-semibold text-white">Categories</h3>
          <span className="text-xs text-white/40 ml-1">({categories.length})</span>
          <button
            onClick={() => setAdding(true)}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs text-white transition-colors"
          >
            <Plus size={13} /> Add category
          </button>
        </div>

        {adding && (
          <div className="mb-4 p-4 rounded-lg border border-blue-500/30 bg-blue-500/10 space-y-3">
            <p className="text-xs text-white/60 font-medium">New category</p>
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Category name"
              className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
            />
            <input
              value={newKeywords}
              onChange={e => setNewKeywords(e.target.value)}
              placeholder="Keywords (comma-separated, e.g. walmart, target, costco)"
              className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
            />
            <div className="flex gap-2">
              <button
                onClick={addCategory}
                disabled={saving || !newName.trim()}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg text-xs text-white transition-colors flex items-center gap-1"
              >
                <Check size={12} /> Save
              </button>
              <button
                onClick={() => { setAdding(false); setNewName(""); setNewKeywords(""); }}
                className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded-lg text-xs text-white/70 transition-colors flex items-center gap-1"
              >
                <X size={12} /> Cancel
              </button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {categories.map(cat => (
            <div key={cat.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
              {editId === cat.id ? (
                <div className="space-y-2">
                  <input
                    autoFocus
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500/50"
                  />
                  <input
                    value={editKeywords}
                    onChange={e => setEditKeywords(e.target.value)}
                    placeholder="Keywords (comma-separated)"
                    className="w-full bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveEdit(cat.id)}
                      disabled={saving}
                      className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded text-xs text-white flex items-center gap-1"
                    >
                      <Check size={11} /> Save
                    </button>
                    <button
                      onClick={cancelEdit}
                      className="px-2.5 py-1 bg-white/10 hover:bg-white/20 rounded text-xs text-white/70 flex items-center gap-1"
                    >
                      <X size={11} /> Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{cat.name}</span>
                      {cat.is_system === 1 && (
                        <span className="text-xs text-white/30 border border-white/10 rounded px-1.5 py-0.5">system</span>
                      )}
                    </div>
                    {cat.keywords && (
                      <p className="text-xs text-white/40 mt-0.5 truncate">{cat.keywords}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => startEdit(cat)}
                      className="p-1.5 text-white/30 hover:text-white/70 transition-colors rounded"
                    >
                      <Pencil size={13} />
                    </button>
                    {cat.is_system === 0 && (
                      <button
                        onClick={() => deleteCategory(cat.id)}
                        className="p-1.5 text-white/30 hover:text-red-400 transition-colors rounded"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <p className="text-xs text-white/30 mt-4">
          System categories cannot be deleted. Keywords are used for automatic transaction matching.
        </p>
      </div>
    </section>
  );
}
