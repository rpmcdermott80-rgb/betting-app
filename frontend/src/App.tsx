import { useState } from "react";
import RefreshControl from "./components/RefreshControl";
import TipsTab from "./components/TipsTab";
import TipsterTab from "./components/TipsterTab";
import DataHealth from "./components/tabs/DataHealth";
import OddsCalculator from "./components/tabs/OddsCalculator";
import RulesChecklist from "./components/tabs/RulesChecklist";
import TrackRecord from "./components/tabs/TrackRecord";

const TABS = [
  { id: "horse", label: "Horse Tips" },
  { id: "greyhound", label: "Dog Tips" },
  { id: "multis", label: "Sports Multis" },
  { id: "player-props", label: "Player Props" },
  { id: "tipster-horse", label: "Tipster: Horses" },
  { id: "tipster-greyhound", label: "Tipster: Dogs" },
  { id: "tipster-afl", label: "Tipster: AFL" },
  { id: "tipster-nrl", label: "Tipster: NRL" },
  { id: "track-record", label: "Track Record" },
  { id: "checklist", label: "Rules Checklist" },
  { id: "calculator", label: "Odds Calculator" },
  { id: "data-health", label: "Data Health" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [active, setActive] = useState<TabId>("horse");

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-4 text-xl font-semibold">Bet Board</h1>

      <RefreshControl />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-800 pb-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`rounded px-3 py-1 text-sm ${
              active === tab.id ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {active === "horse" && (
        <TipsTab
          endpoint="/tips/horse"
          emptyReason="Form tips are generated from each runner's real recent starts and trials (racing.com). None to show right now — this fills once there are scheduled races with enough of the field's form captured. Note: this is heuristic form analysis, not a backtested edge over the market."
        />
      )}
      {active === "greyhound" && (
        <TipsTab
          endpoint="/tips/greyhound"
          emptyReason="Form tips are generated from each dog's real recent runs and barrier trials (racingqueensland.com.au, QLD only). None to show right now — this fills once there are scheduled QLD races with enough form captured. Heuristic form analysis, not a backtested edge."
        />
      )}
      {active === "multis" && (
        <TipsTab
          endpoint="/tips/multis"
          emptyReason="Multis are stacked from the strongest AFL/NRL player props (highest recent hit-rate, one per game). They appear once there are enough high-hit-rate props. Note: the combined figure is a rough 'all land' estimate, not a real multi price — there's no player-prop odds source."
        />
      )}
      {active === "player-props" && (
        <TipsTab
          endpoint="/tips/player-props"
          emptyReason="Player props are generated from real game logs (afltables.com for AFL, rugbyleagueproject.org for NRL) via stat-threshold hit-rate analysis — run the scraper and tip generator to populate this."
        />
      )}
      {active === "tipster-horse" && (
        <TipsterTab
          endpoint="/tipster-tips/horse"
          emptyReason="freehorseracingtipsaustralia.com.au's free selections post progressively through the morning (first three races per meeting only, real TAB prices) — none captured yet. This fills once a day's picks have posted and been matched to a scheduled race."
        />
      )}
      {active === "tipster-greyhound" && (
        <TipsterTab
          endpoint="/tipster-tips/greyhound"
          emptyReason="No working greyhound tipster source yet — every real candidate checked so far was blocked, paywalled, offline, or needs deeper JS/network-inspection work to access. Same honest gap as this app's own greyhound coverage being QLD-only."
        />
      )}
      {active === "tipster-afl" && (
        <TipsterTab
          endpoint="/tipster-tips/afl"
          emptyReason="No working AFL tipster source right now — KRUZEY looked viable but blocks every real scraping request (403, regardless of how we identify ourselves), so it's disabled. Will fill in if a real, scrapable match-winner tipster source is found."
        />
      )}
      {active === "tipster-nrl" && (
        <TipsterTab
          endpoint="/tipster-tips/nrl"
          emptyReason="No working NRL tipster source right now — same KRUZEY blocking issue as AFL. Will fill in if a real, scrapable match-winner tipster source is found."
        />
      )}
      {active === "track-record" && <TrackRecord />}
      {active === "checklist" && <RulesChecklist />}
      {active === "calculator" && <OddsCalculator />}
      {active === "data-health" && <DataHealth />}
    </div>
  );
}
