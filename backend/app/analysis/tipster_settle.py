"""Resolves pending TipsterPick rows against real results — mirrors settle_bets.py's
approach applied to third-party picks instead of our own bets. A pick's outcome is
something WE calculate from real data, never the tipster's own claim.

Two shapes, matching how the scrapers resolve picks:
- horse_racing/greyhound ("win" market): needs the matched Event completed with a
  real Result row, exactly like settle_bets.py's own logic.
- afl/nrl ("match_winner" market): needs a MatchResult (final score) for the matched
  Event; the higher score wins, compared against the tipster's recommended team name.

Match-winner (afl/nrl) picks are typically for a game that HASN'T been played yet —
our own Event for that game doesn't exist until afltables.com/rugbyleagueproject.org
scrape it, which only happens after it's completed. A pick scraped before that is
correctly "unresolved" at scrape time, but — unlike a horse/greyhound pick that
either matches a real scheduled race or never will — it should become checkable
once the game is actually played. So football picks get a re-match attempt here on
every settlement run; racing picks that came back unresolved at scrape time stay
that way (that was a real, permanent judgement about a specific already-scheduled
race, not a "wait for it to exist" situation).
"""

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, MatchResult, Result, TipsterPick
from app.scrapers.tipsters.matching import find_event_for_teams, same_team

RACING_SPORTS = {"horse_racing", "greyhound"}
FOOTBALL_SPORTS = {"afl", "nrl"}

# Scrapers for football tipster picks store raw_selection_text starting with this
# shape so it doubles as a re-matchable record of the two teams involved.
_TEAMS_PREFIX_RE = re.compile(r"^(.+?) vs (.+?):")


def _resolve_racing(pick: TipsterPick, db: Session) -> str | None:
    event = db.get(Event, pick.event_id) if pick.event_id else None
    if event is None or event.status != "completed":
        return None
    result = db.scalar(
        select(Result).where(
            Result.event_id == pick.event_id,
            Result.entity_type == pick.entity_type,
            Result.entity_id == pick.entity_id,
        )
    )
    if result is None or result.finish_position is None:
        return None
    return "win" if result.finish_position == 1 else "loss"


def _resolve_football(pick: TipsterPick, db: Session) -> str | None:
    if pick.event_id is None or pick.recommended_side is None:
        return None
    match_result = db.scalar(select(MatchResult).where(MatchResult.event_id == pick.event_id))
    if match_result is None:
        return None
    if match_result.home_score == match_result.away_score:
        return "void"
    winner = match_result.home_team if match_result.home_score > match_result.away_score else match_result.away_team
    # Alias-aware match, not plain substring — see same_team's docstring for the
    # real bugs this fixes (e.g. "Adelaide" vs "Adelaide Crows" never matched
    # under exact equality; "GWS GIANTS" vs stored "Greater Western Sydney" and
    # "Cronulla Sharks" vs stored "Cronulla Sutherland Sharks" never matched
    # under plain substring containment either).
    return "win" if same_team(winner, pick.recommended_side, pick.sport) else "loss"


def _try_reresolve_football(pick: TipsterPick, db: Session) -> bool:
    if pick.sport not in FOOTBALL_SPORTS or pick.outcome != "unresolved" or not pick.recommended_side:
        return False
    m = _TEAMS_PREFIX_RE.match(pick.raw_selection_text)
    if not m:
        return False
    team_a, team_b = (t.strip() for t in m.groups())
    event = find_event_for_teams(db, pick.sport, team_a, team_b, pick.published_at.date())
    if event is None:
        return False
    pick.event_id = event.id
    pick.entity_type = "team"
    pick.market_type = "match_winner"
    pick.outcome = "pending"
    return True


def settle_pending_picks(db: Session) -> dict:
    summary = {"settled_win": 0, "settled_loss": 0, "settled_void": 0, "awaiting_result": 0, "newly_matched": 0}

    unresolved_football = list(
        db.scalars(
            select(TipsterPick).where(TipsterPick.outcome == "unresolved", TipsterPick.sport.in_(FOOTBALL_SPORTS))
        )
    )
    for pick in unresolved_football:
        if _try_reresolve_football(pick, db):
            summary["newly_matched"] += 1

    # This project's sessions use autoflush=False (see app/db.py), so the just-
    # mutated outcome="pending" rows above wouldn't otherwise be visible to the
    # query below within the same call — confirmed by testing: without this,
    # newly-matched picks stayed "pending" until a second, separate settle run.
    db.flush()

    pending = list(db.scalars(select(TipsterPick).where(TipsterPick.outcome == "pending")))
    for pick in pending:
        if pick.sport in RACING_SPORTS:
            outcome = _resolve_racing(pick, db)
        elif pick.sport in FOOTBALL_SPORTS:
            outcome = _resolve_football(pick, db)
        else:
            outcome = None

        if outcome is None:
            summary["awaiting_result"] += 1
            continue

        pick.outcome = outcome
        pick.resolved_at = dt.datetime.now(dt.timezone.utc)
        summary[f"settled_{outcome}"] += 1

    db.commit()
    return summary
