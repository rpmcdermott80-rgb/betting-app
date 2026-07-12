"""Auto-settles pending user bets against real scraped results.

horse_racing/greyhound tips are anchored to a specific scheduled Event, and
racing_com/racing_queensland write a real Result row once that event completes.
player_prop tips are anchored to a player's *most recent already-played* game
(we don't scrape upcoming AFL/NRL fixtures) rather than a future one — but once
our own scrapers log that player's *next* real game, we can check whether the
tipped threshold actually hit, same idea as checking a race result. multi tips
combine several player-prop legs into one basket and aren't resolved here yet —
those still need manual settling in Track Record.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, PlayerGameLog, Result, Tip, UserBet

AUTO_SETTLEABLE_VERTICALS = {"horse_racing", "greyhound", "player_prop"}


def _resolve_outcome(tip: Tip, result: Result) -> str | None:
    if result.finish_position is None:
        return None
    if tip.recommended_side == "win":
        return "win" if result.finish_position == 1 else "loss"
    if tip.recommended_side == "place":
        return "win" if result.finish_position <= 3 else "loss"
    return None


def _resolve_player_prop(tip: Tip, db: Session) -> str | None:
    anchor_event = db.get(Event, tip.event_id) if tip.event_id else None
    if anchor_event is None or tip.line is None:
        return None
    next_log = db.scalar(
        select(PlayerGameLog)
        .join(Event, PlayerGameLog.event_id == Event.id)
        .where(
            PlayerGameLog.player_id == tip.entity_id,
            PlayerGameLog.stat_type == tip.market_type,
            Event.start_time > anchor_event.start_time,
        )
        .order_by(Event.start_time.asc())
    )
    if next_log is None:
        return None
    value = float(next_log.stat_value)
    threshold = float(tip.line)
    hit = value >= threshold if tip.recommended_side == "over" else value < threshold
    return "win" if hit else "loss"


def settle_pending_bets(db: Session) -> dict:
    summary = {"settled_win": 0, "settled_loss": 0, "awaiting_result": 0, "not_auto_settleable": 0}

    pending = list(
        db.scalars(select(UserBet).where(UserBet.outcome == "pending", UserBet.tip_id.isnot(None)))
    )

    for bet in pending:
        tip = db.get(Tip, bet.tip_id)
        if tip is None or tip.vertical not in AUTO_SETTLEABLE_VERTICALS:
            summary["not_auto_settleable"] += 1
            continue

        if tip.vertical == "player_prop":
            outcome = _resolve_player_prop(tip, db)
            if outcome is None:
                summary["awaiting_result"] += 1
                continue
            bet.outcome = outcome
            bet.settled_at = dt.datetime.now(dt.timezone.utc)
            summary[f"settled_{outcome}"] += 1
            continue

        event = db.get(Event, tip.event_id) if tip.event_id else None
        if event is None or event.status != "completed":
            summary["awaiting_result"] += 1
            continue

        result = db.scalar(
            select(Result).where(
                Result.event_id == tip.event_id,
                Result.entity_type == tip.entity_type,
                Result.entity_id == tip.entity_id,
            )
        )
        if result is None:
            summary["awaiting_result"] += 1
            continue

        outcome = _resolve_outcome(tip, result)
        if outcome is None:
            summary["awaiting_result"] += 1
            continue

        bet.outcome = outcome
        bet.settled_at = dt.datetime.now(dt.timezone.utc)
        summary[f"settled_{outcome}"] += 1

    db.commit()
    return summary
