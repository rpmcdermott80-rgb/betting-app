import { useApiGet } from "../../lib/useApi";
import type { SourceHealth } from "../../lib/types";

const STATUS_COLOR: Record<SourceHealth["status"], string> = {
  healthy: "bg-emerald-900 text-emerald-300",
  degraded: "bg-amber-900 text-amber-300",
  blocked: "bg-red-900 text-red-300",
  unknown: "bg-slate-700 text-slate-300",
};

export default function DataHealth() {
  const { data, error, loading } = useApiGet<SourceHealth[]>("/data-health");

  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (error) return <p className="text-red-400">Failed to load: {error}</p>;

  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-400">
        Every known source, honestly. A source with no successful pull yet shows "unknown" — it is never
        silently treated as working.
      </p>
      {(data ?? []).map((s) => (
        <div
          key={s.source_name}
          className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm"
        >
          <div>
            <span className="font-medium">{s.source_name}</span>
            <span className="ml-2 text-slate-500">{s.vertical}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-slate-400">
              {s.last_success_at ? `last success: ${new Date(s.last_success_at).toLocaleString()}` : "never succeeded"}
            </span>
            <span className={`rounded px-2 py-0.5 text-xs uppercase ${STATUS_COLOR[s.status]}`}>{s.status}</span>
          </div>
        </div>
      ))}
      {(data ?? []).length === 0 && <p className="text-slate-500">No sources registered yet.</p>}
    </div>
  );
}
