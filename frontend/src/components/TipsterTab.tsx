import { useApiGet } from "../lib/useApi";
import type { TipsterTips } from "../lib/types";

const OUTCOME_STYLE: Record<string, string> = {
  win: "bg-emerald-900 text-emerald-300",
  loss: "bg-red-900 text-red-300",
  void: "bg-slate-700 text-slate-300",
  pending: "bg-amber-900 text-amber-300",
  unresolved: "bg-slate-800 text-slate-400",
};

function pct(v: number | null): string | null {
  if (v === null) return null;
  return `${Math.round(v * 100)}%`;
}

export default function TipsterTab({ endpoint, emptyReason }: { endpoint: string; emptyReason: string }) {
  const { data, error, loading } = useApiGet<TipsterTips>(endpoint);

  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (error) return <p className="text-red-400">Failed to load: {error}</p>;

  const sources = data?.sources ?? [];
  const picks = data?.picks ?? [];

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-amber-900/50 bg-amber-950/30 p-3 text-xs text-amber-200/80">
        Third-party tipster picks — not our own analysis. The win rate shown is what{" "}
        <span className="font-medium">we've verified</span> from real results, never the tipster's own claim.
      </div>

      {sources.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {sources.map((s) => (
            <div key={s.source_name} className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm">
              <div className="font-medium">{s.source_name}</div>
              <div className="text-xs text-slate-400">
                {s.win_rate !== null
                  ? `${pct(s.win_rate)} verified (${s.settled_wins}-${s.settled_losses})`
                  : "no settled picks yet"}
              </div>
            </div>
          ))}
        </div>
      )}

      {picks.length === 0 ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-slate-400">
          <p className="font-medium text-slate-300">No tipster picks yet.</p>
          <p className="mt-1 text-sm">{emptyReason}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {picks.map((pick) => (
            <div key={pick.id} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="font-medium">{pick.entity_name ?? pick.raw_selection_text}</span>
                  {pick.event_context && <p className="mt-0.5 text-xs text-slate-400">{pick.event_context}</p>}
                  <p className="mt-0.5 text-xs text-amber-200/70">via {pick.source_name}</p>
                </div>
                <span className={`shrink-0 rounded px-2 py-0.5 text-xs uppercase ${OUTCOME_STYLE[pick.outcome]}`}>
                  {pick.outcome}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-400">{pick.raw_selection_text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
