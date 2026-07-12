import { useState } from "react";
import { apiPost } from "../lib/api";
import { useApiGet } from "../lib/useApi";
import type { Tip, UserBet } from "../lib/types";

function pct(v: number | null): string | null {
  if (v === null) return null;
  return `${Math.round(v * 100)}%`;
}

// Racing form ratings, player-prop hit-rates and multi estimates are different kinds
// of number, so label them honestly rather than a generic "confidence".
function ratingLabel(vertical: string): string {
  if (vertical === "player_prop") return "hit rate";
  if (vertical === "multi") return "all land (est)";
  return "form rating";
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

// Real outcome once the race has actually run — shown on every tip, not just
// ones a bet was taken on, so "did this pick actually win" never requires
// digging into Track Record.
function resultBadge(tip: Tip): { label: string; className: string } | null {
  if (tip.result_status === "won") return { label: "WON", className: "bg-emerald-900 text-emerald-300" };
  if (tip.result_status === "lost") {
    const label = tip.finish_position ? `LOST — ${ordinal(tip.finish_position)}` : "LOST";
    return { label, className: "bg-red-900 text-red-300" };
  }
  return null;
}

function marketLine(tip: Tip): string {
  if (tip.market_type === tip.recommended_side) return "WIN";
  return `${tip.market_type} ${tip.recommended_side}${tip.line !== null ? ` ${tip.line}` : ""}`;
}

function contextLine(tip: Tip): string | null {
  if (tip.vertical === "horse_racing" || tip.vertical === "greyhound") {
    const parts = [tip.venue_name, tip.race_number !== null ? `Race ${tip.race_number}` : null].filter(Boolean);
    return parts.length ? parts.join(" · ") : null;
  }
  if (tip.vertical === "player_prop") {
    return [tip.entity_team, marketLine(tip)].filter(Boolean).join(" · ") || null;
  }
  return null;
}

// Only horse/greyhound tips point at a real scheduled event we'll later scrape a
// result for, so only those can be auto-settled. Player-prop/multi tips are
// snapshots of a player's most recent already-played game — there's no future
// fixture for the app to check, so those bets need manual win/loss/void in
// Track Record.
function autoSettleNote(vertical: string): string | null {
  if (vertical === "horse_racing" || vertical === "greyhound") {
    return "Auto-settles once this race result comes in.";
  }
  return "Settle manually in Track Record once the game's played — no upcoming-fixture data to auto-check this against.";
}

function TakeBetForm({ tip, onTaken }: { tip: Tip; onTaken: () => void }) {
  const [open, setOpen] = useState(false);
  const [stake, setStake] = useState("");
  const [odds, setOdds] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!stake || !odds) return;
    setSubmitting(true);
    try {
      await apiPost("/bets", { tip_id: tip.id, stake: Number(stake), odds_taken: Number(odds) });
      onTaken();
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-2 rounded bg-emerald-800 px-2 py-1 text-xs hover:bg-emerald-700"
      >
        Take bet
      </button>
    );
  }

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex flex-wrap gap-2">
        <input
          className="w-20 rounded bg-slate-800 px-2 py-1 text-xs"
          placeholder="Stake"
          value={stake}
          onChange={(e) => setStake(e.target.value)}
        />
        <input
          className="w-24 rounded bg-slate-800 px-2 py-1 text-xs"
          placeholder="Odds taken"
          value={odds}
          onChange={(e) => setOdds(e.target.value)}
        />
        <button
          onClick={submit}
          disabled={submitting || !stake || !odds}
          className="rounded bg-emerald-700 px-2 py-1 text-xs hover:bg-emerald-600 disabled:opacity-50"
        >
          Confirm
        </button>
        <button onClick={() => setOpen(false)} className="rounded bg-slate-700 px-2 py-1 text-xs">
          Cancel
        </button>
      </div>
      <p className="text-[11px] text-slate-500">{autoSettleNote(tip.vertical)}</p>
    </div>
  );
}

export default function TipsTab({ endpoint, emptyReason }: { endpoint: string; emptyReason: string }) {
  const { data, error, loading } = useApiGet<Tip[]>(endpoint);
  const { data: betsData } = useApiGet<UserBet[]>("/bets");
  const [justTaken, setJustTaken] = useState<Set<number>>(new Set());

  const takenTipIds = new Set([
    ...(betsData ?? []).map((b) => b.tip_id).filter((id): id is number => id !== null),
    ...justTaken,
  ]);

  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (error) return <p className="text-red-400">Failed to load: {error}</p>;

  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-slate-400">
        <p className="font-medium text-slate-300">No tips yet.</p>
        <p className="mt-1 text-sm">{emptyReason}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((tip) => {
        const isRacing = tip.vertical === "horse_racing" || tip.vertical === "greyhound";
        const legCount = Array.isArray((tip.stat_basis as { legs?: unknown[] })?.legs)
          ? (tip.stat_basis as { legs: unknown[] }).legs.length
          : null;
        const title =
          tip.vertical === "multi"
            ? `${legCount ?? ""}-leg multi`
            : (tip.entity_name ?? (isRacing ? "Selection" : marketLine(tip)));
        const context = contextLine(tip);
        const rating = pct(tip.confidence_score);
        const taken = takenTipIds.has(tip.id);
        const result = resultBadge(tip);
        return (
          <div key={tip.id} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="font-medium">{title}</span>
                {isRacing && tip.entity_name && (
                  <span className="ml-2 text-xs uppercase tracking-wide text-emerald-400">WIN</span>
                )}
                {result && (
                  <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${result.className}`}>
                    {result.label}
                  </span>
                )}
                {context && <p className="mt-0.5 text-xs text-slate-400">{context}</p>}
              </div>
              {rating && (
                <div className="shrink-0 text-right">
                  <div className="text-lg font-semibold text-emerald-400">{rating}</div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">{ratingLabel(tip.vertical)}</div>
                </div>
              )}
            </div>
            {tip.rationale_text && <p className="mt-2 text-sm text-slate-400">{tip.rationale_text}</p>}
            {taken ? (
              <p className="mt-2 text-xs font-medium text-emerald-500">✓ Bet taken — tracked in Track Record</p>
            ) : (
              <TakeBetForm
                tip={tip}
                onTaken={() => setJustTaken((prev) => new Set(prev).add(tip.id))}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
