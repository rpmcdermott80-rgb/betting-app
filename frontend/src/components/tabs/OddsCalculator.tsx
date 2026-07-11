import { useState } from "react";

export default function OddsCalculator() {
  const [legs, setLegs] = useState<string[]>(["", ""]);
  const [stake, setStake] = useState("10");

  const parsed = legs.map((l) => parseFloat(l)).filter((n) => !isNaN(n) && n > 0);
  const combined = parsed.reduce((acc, n) => acc * n, 1);
  const stakeNum = parseFloat(stake) || 0;
  const payout = combined * stakeNum;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 space-y-2">
        <p className="font-medium">Multi legs (decimal odds)</p>
        {legs.map((leg, i) => (
          <input
            key={i}
            className="block w-full rounded bg-slate-800 px-2 py-1 text-sm"
            placeholder={`Leg ${i + 1} odds`}
            value={leg}
            onChange={(e) => {
              const next = [...legs];
              next[i] = e.target.value;
              setLegs(next);
            }}
          />
        ))}
        <div className="flex gap-2">
          <button
            onClick={() => setLegs([...legs, ""])}
            className="rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600"
          >
            + Add leg
          </button>
          {legs.length > 1 && (
            <button
              onClick={() => setLegs(legs.slice(0, -1))}
              className="rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600"
            >
              − Remove leg
            </button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 space-y-2">
        <label className="flex items-center gap-2 text-sm">
          Stake
          <input
            className="w-24 rounded bg-slate-800 px-2 py-1"
            value={stake}
            onChange={(e) => setStake(e.target.value)}
          />
        </label>
        <p className="text-lg">
          Combined odds: <span className="font-medium">{combined.toFixed(2)}</span>
        </p>
        <p className="text-lg">
          Payout: <span className="font-medium">${payout.toFixed(2)}</span>
        </p>
      </div>
    </div>
  );
}
