"""Horse form enricher. For each horse entered in a scheduled (not-yet-run) race we
track, pull its real race-by-race history from racing.com's per-horse history endpoint
(GetRaceEntryItemByHorsePaged) and store it in form_starts for our own form analysis.

This is genuine primary data — actual past finishing positions, margins, prices, dates,
plus trial/jump-out flags — not the source's pre-computed form summary. We only pull
horses we're actually going to tip (runners in scheduled races), and skip any horse
whose form we already refreshed recently, so a daily run stays bounded rather than
re-pulling thousands of full histories every time.
"""

import datetime as dt

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventParticipant, Event, Horse, FormStart
from app.scrapers.racing_com import GRAPHQL_URL, _headers
from app.scrapers.util import get_source, parse_price, upsert_form_start

FORM_FRESH_HOURS = 12
HISTORY_QUERY = """
query getRaceEntryItemByHorsePaged($horseCode: ID!, $pageSize: Int = 30) {
  GetRaceEntryItemByHorsePaged(horseCode: $horseCode, limit: $pageSize) {
    finish
    margin
    startingPrice
    raceDate
    raceDistance
    trackCondition
    isTrial
    isJumpOut
    venueName
    race { id }
  }
}
"""


def _target_horses(db: Session) -> list[Horse]:
    """Horses entered in a scheduled horse race and not scratched — the runners we tip."""
    stmt = (
        select(Horse)
        .join(EventParticipant, (EventParticipant.entity_id == Horse.id) & (EventParticipant.entity_type == "horse"))
        .join(Event, Event.id == EventParticipant.event_id)
        .where(
            Event.sport == "horse_racing",
            Event.status == "scheduled",
            EventParticipant.scratched.is_(False),
            Horse.external_id.isnot(None),
        )
        .distinct()
    )
    return list(db.scalars(stmt))


def _has_fresh_form(db: Session, horse_id: int) -> bool:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=FORM_FRESH_HOURS)
    recent = db.scalar(
        select(FormStart).where(
            FormStart.entity_type == "horse",
            FormStart.entity_id == horse_id,
            FormStart.scraped_at >= cutoff,
        )
    )
    return recent is not None


def run(db: Session, limit: int | None = None) -> dict:
    source = get_source(db, "racing.com")
    horses = _target_horses(db)

    fetched, skipped, rows_written, failed = 0, 0, 0, 0
    for horse in horses:
        if limit is not None and fetched >= limit:
            break
        if _has_fresh_form(db, horse.id):
            skipped += 1
            continue
        try:
            resp = httpx.post(
                GRAPHQL_URL,
                json={
                    "query": HISTORY_QUERY,
                    "operationName": "getRaceEntryItemByHorsePaged",
                    "variables": {"horseCode": horse.external_id, "pageSize": 30},
                },
                timeout=20,
                headers=_headers(),
            )
            resp.raise_for_status()
            starts = resp.json().get("data", {}).get("GetRaceEntryItemByHorsePaged") or []
        except Exception:
            failed += 1
            continue

        fetched += 1
        for s in starts:
            raw_date = s.get("raceDate")
            if not raw_date:
                continue
            race_date = dt.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            race = s.get("race") or {}
            if upsert_form_start(
                db,
                entity_type="horse",
                entity_id=horse.id,
                race_date=race_date,
                external_race_id=str(race["id"]) if race.get("id") else None,
                source_id=source.id,
                finish_position=s.get("finish"),
                margin=s.get("margin"),
                distance=s.get("raceDistance"),
                track_condition=s.get("trackCondition"),
                starting_price=parse_price(s.get("startingPrice")),
                venue=s.get("venueName"),
                is_trial=bool(s.get("isTrial")),
                is_jumpout=bool(s.get("isJumpOut")),
            ):
                rows_written += 1
        db.commit()

    return {"horses_fetched": fetched, "skipped_fresh": skipped, "failed": failed, "form_rows_written": rows_written}
