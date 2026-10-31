'use client';

import { useState } from 'react';

export default function Home() {
  const [inputVal, setInputVal] = useState('');
  const [activeTargets, setActiveTargets] = useState<string[]>([
    'credit card digits',
    'passwords',
    'id numbers'
  ]);
  const [status, setStatus] = useState<string | null>(null);

  const syncBackend = async (targets: string[]) => {
    try {
      await fetch('http://localhost:8080/api/v1/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets }),
      });
      setStatus(`Synced ${targets.length} targets with engine.`);
    } catch {
      setStatus(`Updated locally (${targets.length} targets active, daemon offline)`);
    }
  };

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputVal.trim();
    if (!trimmed) return;

    // Split by comma if user pasted multiple at once
    const newItems = trimmed
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0 && !activeTargets.includes(item));

    if (newItems.length > 0) {
      const updated = [...activeTargets, ...newItems];
      setActiveTargets(updated);
      syncBackend(updated);
    }
    setInputVal('');
  };

  const handleRemove = (itemToRemove: string) => {
    const updated = activeTargets.filter((t) => t !== itemToRemove);
    setActiveTargets(updated);
    syncBackend(updated);
  };

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
        <h1 className="text-lg font-bold mb-1 tracking-tight">Censorship Preferences</h1>
        <p className="text-xs text-slate-400 mb-5">
          Add multiple target categories (separate by commas or add one by one). YOLO-World evaluates them in parallel.
        </p>

        <form onSubmit={handleAdd} className="space-y-3">
          <div>
            <label htmlFor="pref" className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Add Detection Target(s)
            </label>
            <input
              id="pref"
              type="text"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="e.g. passport, IBAN, private keys"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          <button
            type="submit"
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm py-2 rounded-lg transition-colors shadow"
          >
            Add Target
          </button>
        </form>

        {/* Active Target Tags */}
        <div className="mt-5 pt-4 border-t border-slate-800">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
            Active Rules ({activeTargets.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {activeTargets.map((target) => (
              <span
                key={target}
                className="inline-flex items-center gap-1.5 text-xs bg-slate-950 border border-slate-700 text-slate-200 px-2.5 py-1 rounded-md"
              >
                <span>{target}</span>
                <button
                  type="button"
                  onClick={() => handleRemove(target)}
                  className="text-slate-500 hover:text-rose-400 transition-colors font-bold"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>

        {status && (
          <div className="mt-4 p-2.5 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono text-emerald-400">
            {status}
          </div>
        )}
      </div>
    </main>
  );
}