import { useState } from "react";
import { apiDelete, apiPost } from "../../lib/api";
import { useApiGet } from "../../lib/useApi";
import type { ChecklistItem } from "../../lib/types";

export default function RulesChecklist() {
  const { data, error, loading } = useApiGet<ChecklistItem[]>("/checklist");
  const [label, setLabel] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  async function add() {
    if (!label.trim()) return;
    await apiPost("/checklist", { label, sort_order: (data?.length ?? 0) });
    setLabel("");
    setRefreshKey((k) => k + 1);
  }

  async function remove(id: number) {
    await apiDelete(`/checklist/${id}`);
    setRefreshKey((k) => k + 1);
  }

  return (
    <div key={refreshKey} className="space-y-3">
      <div className="flex gap-2">
        <input
          className="flex-1 rounded bg-slate-800 px-2 py-1 text-sm"
          placeholder="New checklist item (e.g. 'Check trial form')"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button onClick={add} className="rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600">
          Add
        </button>
      </div>

      {loading && <p className="text-slate-400">Loading...</p>}
      {error && <p className="text-red-400">Failed to load: {error}</p>}

      <ul className="space-y-2">
        {(data ?? []).map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm"
          >
            <label className="flex items-center gap-2">
              <input type="checkbox" />
              {item.label}
            </label>
            <button onClick={() => remove(item.id)} className="text-slate-500 hover:text-red-400">
              remove
            </button>
          </li>
        ))}
        {(data ?? []).length === 0 && !loading && <p className="text-slate-500">No checklist items yet.</p>}
      </ul>
    </div>
  );
}
