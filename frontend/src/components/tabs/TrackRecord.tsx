import { useState } from "react";
import { apiPatch, apiPost } from "../../lib/api";
import { useApiGet } from "../../lib/useApi";
import type { UserBet } from "../../lib/types";

export default function TrackRecord() {
  const { data, error, loading } = useApiGet<UserBet[]>("/bets");
  const [stake, setStake] = useState("");
  const [odds, setOdds] = useState("");
  const [notes, setNotes] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [settling, setSettling] = useState(false);
  const [settleResult, setSettleResult] = useState<Record<string, number> | null>(null);

  async function logBet() {
    if (!stake || !odds) return;
    await apiPost("/bets", { stake: Number(stake), odds_taken: Number(odds), notes: notes || null });
    setStake("");
    setOdds("");
    setNotes("");
    setRefreshKey((k) => k + 1);
  }

  async function settle(id: number, outcome: "win" | "loss" | "void") {
    await apiPatch(`/bets/${id}/settle`, { outcome });
    setRefreshKey((k) => k + 1);
  }

  async function settleAllPending() {
    setSettling(true);
    try {
      const result = await apiPost<Record<string, number>>("/bets/settle", {});
      setSettleResult(result);
      setRefreshKey((k) => k + 1);
    } finally {
      setSettling(false);
    }
  }

  const bets = data ?? [];
  const settled = bets.filter((b) => b.outcome !== "pending");
  const wins = settled.filter((b) => b.outcome === "win").length;
  const losses = settled.filter((b) => b.outcome === "loss").length;

  return (
    <div key={refreshKey} className="space-y-4">
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-lg font-medium">
            {wins}–{losses} <span className="text-sm font-normal text-slate-400">(settled bets, persisted)</span>
          </p>
          <button
            onClick={settleAllPending}
            disabled={settling}
            className="shrink-0 rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600 disabled:opacity-50"
          >
            {settling ? "Settling..." : "Settle bets"}
          </button>
        </div>
        {settleResult && (
          <p className="mt-2 text-xs text-slate-400">
            {settleResult.settled_win ?? 0} won, {settleResult.settled_loss ?? 0} lost,{" "}
            {settleResult.awaiting_result ?? 0} awaiting a result, {settleResult.not_auto_settleable ?? 0} need
            manual settling (player props/multis).
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 space-y-2">
        <p className="font-medium">Log a bet</p>
        <div className="flex flex-wrap gap-2">
          <input
            className="rounded bg-slate-800 px-2 py-1 text-sm"
            placeholder="Stake"
            value={stake}
            onChange={(e) => setStake(e.target.value)}
          />
          <input
            className="rounded bg-slate-800 px-2 py-1 text-sm"
            placeholder="Odds taken"
            value={odds}
            onChange={(e) => setOdds(e.target.value)}
          />
          <input
            className="rounded bg-slate-800 px-2 py-1 text-sm flex-1"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <button onClick={logBet} className="rounded bg-emerald-700 px-3 py-1 text-sm hover:bg-emerald-600">
            Log
          </button>
        </div>
      </div>

      {loading && <p className="text-slate-400">Loading...</p>}
      {error && <p className="text-red-400">Failed to load: {error}</p>}

      <div className="space-y-2">
        {bets.map((bet) => (
          <div
            key={bet.id}
            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm"
          >
            <div>
              <span className="font-medium">
                ${bet.stake} @ {bet.odds_taken}
              </span>
              {bet.notes && <span className="ml-2 text-slate-400">{bet.notes}</span>}
              {bet.tip_label && (
                <p className="mt-0.5 text-xs text-slate-400">
                  {bet.tip_label}
                  {bet.outcome === "pending" && bet.auto_settleable && (
                    <span className="ml-2 text-slate-500">(auto-settles on result)</span>
                  )}
                </p>
              )}
            </div>
            {bet.outcome === "pending" ? (
              <div className="flex gap-1">
                <button onClick={() => settle(bet.id, "win")} className="rounded bg-emerald-800 px-2 py-0.5">
                  Win
                </button>
                <button onClick={() => settle(bet.id, "loss")} className="rounded bg-red-900 px-2 py-0.5">
                  Loss
                </button>
                <button onClick={() => settle(bet.id, "void")} className="rounded bg-slate-700 px-2 py-0.5">
                  Void
                </button>
              </div>
            ) : (
              <span className="uppercase text-slate-400">{bet.outcome}</span>
            )}
          </div>
        ))}
        {bets.length === 0 && !loading && <p className="text-slate-500">No bets logged yet.</p>}
      </div>
    </div>
  );
}
