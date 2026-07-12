"""One-off cleanup for the non-NRL-competition contamination bug (see
rugbyleagueproject.py's _is_real_nrl_club): the scraper's per-team discovery
picked up matches from other competitions those players also feature in —
confirmed real cases: Queensland Cup feeder-club games (Redcliffe Dolphins,
Souths Logan Magpies, Burleigh Bears...), a Super League exhibition (Betfred
World Club Challenge, with real current NRL players' stats attached), and
representative/All Stars matches. None of those are real NRL premiership
games, so none should have been in any player's "recent NRL form" window.

The scraper itself is now fixed to reject anything that isn't both teams being
one of the 17 real NRL clubs; this only cleans up data already stored before
that fix landed.

For each contaminated event: any player_prop Tip anchored to it gets deleted
(it was computed from bad data anyway — a correct one regenerates against the
player's real most-recent legitimate game on the next refresh); any
TipsterPick matched to it gets reverted to unresolved so it can re-match
against the real fixture once that's found; any UserBet referencing such a
Tip blocks the cleanup for that event so it can be handled by hand rather than
silently orphaned. Then player_game_logs, match_result, and the event itself
are deleted.

Usage: docker compose exec api python -m app.cleanup_non_nrl_matches [--dry-run]
"""

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Event, MatchResult, PlayerGameLog, Tip, TipsterPick, UserBet
from app.scrapers.tipsters.matching import strip_nrl_round_prefix, NRL_TEAM_ALIASES


def _is_real_nrl_club(team_name: str) -> bool:
    return strip_nrl_round_prefix(team_name) in NRL_TEAM_ALIASES


def find_contaminated_events(db):
    rows = db.execute(
        select(Event.id, Event.start_time, MatchResult.home_team, MatchResult.away_team)
        .select_from(MatchResult)
        .join(Event, Event.id == MatchResult.event_id)
        .where(Event.sport == "nrl")
    ).all()
    return [
        (eid, start_time, home, away)
        for eid, start_time, home, away in rows
        if not (_is_real_nrl_club(home) and _is_real_nrl_club(away))
    ]


def main():
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        contaminated = find_contaminated_events(db)
        print(f"Found {len(contaminated)} contaminated (non-NRL) events")

        skipped_has_bet = 0
        deleted_events = 0
        deleted_logs_total = 0
        deleted_tips_total = 0
        reverted_picks_total = 0

        for event_id, start_time, home, away in contaminated:
            tip_ids = list(db.scalars(select(Tip.id).where(Tip.event_id == event_id)))
            bet_count = (
                db.scalar(select(UserBet).where(UserBet.tip_id.in_(tip_ids)).limit(1)) is not None
                if tip_ids
                else False
            )
            if bet_count:
                print(f"SKIP {start_time.date()} {home} vs {away} (event {event_id}): has a real UserBet, handle by hand")
                skipped_has_bet += 1
                continue

            pick_ids = list(db.scalars(select(TipsterPick.id).where(TipsterPick.event_id == event_id)))
            log_count = db.scalar(
                select(PlayerGameLog).where(PlayerGameLog.event_id == event_id).limit(1)
            )
            n_logs = db.execute(
                select(PlayerGameLog.id).where(PlayerGameLog.event_id == event_id)
            ).all()

            print(
                f"{start_time.date()} {home} vs {away} (event {event_id}): "
                f"{len(n_logs)} logs, {len(tip_ids)} tips, {len(pick_ids)} tipster picks"
            )

            if not dry_run:
                if tip_ids:
                    db.query(Tip).filter(Tip.id.in_(tip_ids)).delete(synchronize_session=False)
                if pick_ids:
                    db.query(TipsterPick).filter(TipsterPick.id.in_(pick_ids)).update(
                        {"event_id": None, "entity_type": None, "entity_id": None, "outcome": "unresolved"},
                        synchronize_session=False,
                    )
                db.query(PlayerGameLog).filter(PlayerGameLog.event_id == event_id).delete(
                    synchronize_session=False
                )
                db.query(MatchResult).filter(MatchResult.event_id == event_id).delete(
                    synchronize_session=False
                )
                db.query(Event).filter(Event.id == event_id).delete(synchronize_session=False)

            deleted_events += 1
            deleted_logs_total += len(n_logs)
            deleted_tips_total += len(tip_ids)
            reverted_picks_total += len(pick_ids)

        if not dry_run:
            db.commit()

        print(
            f"\n{'[DRY RUN] would have' if dry_run else ''} removed {deleted_events} contaminated events, "
            f"{deleted_logs_total} player_game_logs, {deleted_tips_total} tips; "
            f"reverted {reverted_picks_total} tipster picks to unresolved; "
            f"skipped {skipped_has_bet} events with a real bet attached"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
