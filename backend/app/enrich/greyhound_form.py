"""Greyhound form enricher. For each greyhound entered in a scheduled (not-yet-run)
QLD race we track, pull its recent race history from Racing Queensland's dog-profile
API (api.racingqueensland.com.au/api/profiles/greyhound) and store it in form_starts.

Genuine primary data — actual past finishing positions, dates, distances, prices, and
crucially the IsBarrierTrial flag (greyhound trials the user wants weighed separately).
The endpoint returns the dog's recent form (~last 5), which is the standard greyhound
form window anyway. Uses the same public per-page-load JWT as the meetings/races API.
"""

import datetime as dt
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, EventParticipant, FormStart, Greyhound
from app.scrapers.base import USER_AGENT
from app.scrapers.util import get_source, parse_price, upsert_form_start

WWW_BASE = "https://www.racingqueensland.com.au"
API_BASE = "https://api.racingqueensland.com.au"
QLD_TZ = dt.timezone(dt.timedelta(hours=10))
FORM_FRESH_HOURS = 12
TOKEN_PAGE = f"{WWW_BASE}/racing/full-calendar/greyhound"


def _target_greyhounds(db: Session) -> list[Greyhound]:
    stmt = (
        select(Greyhound)
        .join(EventParticipant, (EventParticipant.entity_id == Greyhound.id) & (EventParticipant.entity_type == "greyhound"))
        .join(Event, Event.id == EventParticipant.event_id)
        .where(
            Event.sport == "greyhound",
            Event.status == "scheduled",
            EventParticipant.scratched.is_(False),
            Greyhound.external_id.isnot(None),
        )
        .distinct()
    )
    return list(db.scalars(stmt))


def _has_fresh_form(db: Session, gid: int) -> bool:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=FORM_FRESH_HOURS)
    return db.scalar(
        select(FormStart).where(
            FormStart.entity_type == "greyhound",
            FormStart.entity_id == gid,
            FormStart.scraped_at >= cutoff,
        )
    ) is not None


def _parse_description(desc_html: str) -> dict:
    """The description packs date/margin/distance/venue into HTML strongs, e.g.
    '<strong>09/07/26</strong>, <strong>0.50L</strong>, <strong>350m</strong>, ...'."""
    text = re.sub(r"<[^>]+>", "", desc_html)
    out: dict = {}
    date_m = re.search(r"(\d{2})/(\d{2})/(\d{2})", text)
    if date_m:
        d, mth, y = date_m.groups()
        out["race_date"] = dt.datetime(2000 + int(y), int(mth), int(d), tzinfo=QLD_TZ)
    dist_m = re.search(r"(\d+)m\b", text)
    if dist_m:
        out["distance"] = f"{dist_m.group(1)}m"
    marg_m = re.search(r"(\d+\.\d+)L", text)
    if marg_m:
        out["margin"] = f"{marg_m.group(1)}L"
    return out


def run(db: Session, limit: int | None = None) -> dict:
    source = get_source(db, "racingqueensland.com.au")
    greyhounds = _target_greyhounds(db)
    if not greyhounds:
        return {"greyhounds_fetched": 0, "skipped_fresh": 0, "failed": 0, "form_rows_written": 0}

    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
    page = client.get(TOKEN_PAGE)
    token_m = re.search(r"window\.apiToken = '([^']+)'", page.text)
    if not token_m:
        raise RuntimeError("Could not find window.apiToken on a Racing Queensland page")
    auth = {"Authorization": f"bearer {token_m.group(1)}", "Referer": f"{WWW_BASE}/"}

    fetched, skipped, rows_written, failed = 0, 0, 0, 0
    for g in greyhounds:
        if limit is not None and fetched >= limit:
            break
        if _has_fresh_form(db, g.id):
            skipped += 1
            continue
        try:
            r = client.get(f"{API_BASE}/api/profiles/greyhound", params={"animalid": g.external_id}, headers=auth)
            r.raise_for_status()
            races = (r.json().get("RecentForm") or {}).get("PreviousRaces") or []
        except Exception:
            failed += 1
            continue

        fetched += 1
        for pr in races:
            parsed = _parse_description(pr.get("DescriptionHTML", ""))
            race_date = parsed.get("race_date")
            if race_date is None:
                continue
            if upsert_form_start(
                db,
                entity_type="greyhound",
                entity_id=g.id,
                race_date=race_date,
                external_race_id=None,  # no stable race id here; dedup on (entity, date, distance)
                source_id=source.id,
                finish_position=pr.get("Position"),
                margin=parsed.get("margin"),
                distance=parsed.get("distance"),
                track_condition=None,
                starting_price=parse_price(pr.get("StartingOdds")),
                venue=None,
                is_trial=bool(pr.get("IsBarrierTrial")),
                is_jumpout=False,
            ):
                rows_written += 1
        db.commit()

    client.close()
    return {"greyhounds_fetched": fetched, "skipped_fresh": skipped, "failed": failed, "form_rows_written": rows_written}
