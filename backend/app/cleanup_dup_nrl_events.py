"""One-off cleanup for the duplicate-NRL-match bug (see rugbyleagueproject.py):
the scraper used to dedupe by raw match URL, and rugbyleagueproject.org sometimes
serves the same real match under more than one /matches/<id> URL, so the same
game was captured twice under two different Event rows, double-counting player
game logs. The scraper itself is now fixed to dedupe by (sport, date, teams)
instead; this only cleans up data already corrupted before that fix landed.

For each duplicate pair (same sport/date/home_team/away_team on MatchResult),
keeps the Event with the most player_game_logs rows (the more complete capture,
ties broken by lower id = discovered first), repoints any Tip/TipsterPick that
referenced the loser's event_id to the winner, then deletes the loser's
player_game_logs, match_result, and event row.

Usage: docker compose exec api python -m app.cleanup_dup_nrl_events [--dry-run]
"""

import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Event, MatchResult, PlayerGameLog, Tip, TipsterPick


def find_duplicate_groups(db):
    rows = db.execute(
        select(
            Event.start_time,
            MatchResult.home_team,
            MatchResult.away_team,
            func.array_agg(Event.id).label("event_ids"),
        )
        .select_from(MatchResult)
        .join(Event, Event.id == MatchResult.event_id)
        .where(Event.sport == "nrl")
        .group_by(Event.start_time, MatchResult.home_team, MatchResult.away_team)
        .having(func.count() > 1)
    ).all()
    return rows


def main():
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        groups = find_duplicate_groups(db)
        print(f"Found {len(groups)} duplicate match groups")

        total_deleted_logs = 0
        total_repointed_tips = 0
        total_repointed_picks = 0

        for start_time, home_team, away_team, event_ids in groups:
            counts = {
                eid: db.scalar(select(func.count()).where(PlayerGameLog.event_id == eid))
                for eid in event_ids
            }
            winner = max(event_ids, key=lambda eid: (counts[eid], -eid))
            losers = [eid for eid in event_ids if eid != winner]

            print(
                f"{start_time.date()} {home_team} vs {away_team}: "
                f"keep event {winner} ({counts[winner]} logs), "
                f"drop {losers} ({[counts[l] for l in losers]} logs)"
            )

            for loser in losers:
                tip_ids = list(db.scalars(select(Tip.id).where(Tip.event_id == loser)))
                pick_ids = list(db.scalars(select(TipsterPick.id).where(TipsterPick.event_id == loser)))

                if not dry_run:
                    if tip_ids:
                        db.query(Tip).filter(Tip.id.in_(tip_ids)).update(
                            {"event_id": winner}, synchronize_session=False
                        )
                    if pick_ids:
                        db.query(TipsterPick).filter(TipsterPick.id.in_(pick_ids)).update(
                            {"event_id": winner}, synchronize_session=False
                        )
                    deleted = (
                        db.query(PlayerGameLog).filter(PlayerGameLog.event_id == loser).delete(
                            synchronize_session=False
                        )
                    )
                    db.query(MatchResult).filter(MatchResult.event_id == loser).delete(
                        synchronize_session=False
                    )
                    db.query(Event).filter(Event.id == loser).delete(synchronize_session=False)
                    total_deleted_logs += deleted
                total_repointed_tips += len(tip_ids)
                total_repointed_picks += len(pick_ids)

        if not dry_run:
            db.commit()
        print(
            f"\n{'[DRY RUN] would have' if dry_run else ''} "
            f"deleted {total_deleted_logs} duplicate player_game_logs, "
            f"repointed {total_repointed_tips} tips, {total_repointed_picks} tipster picks"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
