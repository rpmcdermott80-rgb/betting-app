"""Horse racing reference scraper. Confirmed working 2026-07-10.

racing.com's robots.txt is fully permissive and its horse-profile pages, while a
client-side SPA, are backed by a real GraphQL API (graphql.rmdprod.racing.com, no
robots.txt of its own either) authenticated with a static x-api-key header shipped in
racing.com's own JS bundle — public, not a secret credential. Discovered via a one-time
Playwright network-inspection pass; production scraping below calls the API directly
with plain httpx, no browser needed.

Two calls cover everything: GetRaceMeetingsByStateNew_CD lists meetings for a date
window, getRacesForMeet_CD returns full race conditions + every runner (barrier,
weight, jockey/trainer, result, and multi-bookmaker odds) for one meeting.
"""

import datetime as dt
import json
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventParticipant, OddsSnapshot, Result
from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.util import get_or_create_event, get_or_create_horse, get_or_create_venue, parse_price

GRAPHQL_URL = "https://graphql.rmdprod.racing.com/"
API_KEY = "da2-6nsi4ztsynar3l3frgxf77q5fe"

MEETINGS_QUERY = """
query GetRaceMeetingsByStateNew_CD(
  $states: String!
  $daysBack: Int!
  $daysForward: Int!
  $userDate: String!
) {
  GetRaceMeetingsByStateNew(
    states: $states
    daysBack: $daysBack
    daysForward: $daysForward
    userDate: $userDate
  ) {
    id
    venue
    date
    state
    isTrial
    isJumpOut
  }
}
"""

RACES_FOR_MEET_QUERY = """
query getRacesForMeet_CD($meetCode: ID!) {
  getRacesForMeet(meetCode: $meetCode) {
    id
    raceNumber
    raceStatus
    distance
    time
    name
    formRaceEntries {
      id
      horseCode
      horseName
      barrierNumber
      weight
      scratched
      finish
      margin
      startingPrice
      odds {
        providerCode
        oddsWin
        oddsPlace
      }
    }
  }
}
"""

ALL_AU_STATES = "VIC|NSW|QLD|SA|WA|TAS|NT|ACT"


def _headers() -> dict:
    return {"User-Agent": USER_AGENT, "x-api-key": API_KEY, "Content-Type": "application/json"}


class RacingComScraper(BaseScraper):
    source_name = "racing.com"

    def __init__(self):
        self._meetings: dict[str, dict] = {}

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        # Rough AEST approximation (UTC+10) rather than pulling in a timezone lib —
        # good enough to pick "today" for a personal AU-only tool.
        now_aest = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=10)
        user_date = f"{now_aest.year}-{now_aest.month}-{now_aest.day}"

        resp = httpx.post(
            GRAPHQL_URL,
            json={
                "query": MEETINGS_QUERY,
                "operationName": "GetRaceMeetingsByStateNew_CD",
                "variables": {"states": ALL_AU_STATES, "daysBack": 2, "daysForward": 1, "userDate": user_date},
            },
            timeout=20,
            headers=_headers(),
        )
        resp.raise_for_status()
        meetings = resp.json().get("data", {}).get("GetRaceMeetingsByStateNew") or []

        if limit is not None:
            meetings = meetings[:limit]

        self._meetings = {m["id"]: m for m in meetings}
        return [f"{GRAPHQL_URL}?op=getRacesForMeet&meetCode={m['id']}" for m in meetings]

    def fetch(self, url: str) -> str:
        meet_code = parse_qs(urlparse(url).query)["meetCode"][0]
        resp = httpx.post(
            GRAPHQL_URL,
            json={
                "query": RACES_FOR_MEET_QUERY,
                "operationName": "getRacesForMeet_CD",
                "variables": {"meetCode": meet_code},
            },
            timeout=20,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.text

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        meet_code = parse_qs(urlparse(url).query)["meetCode"][0]
        meeting = self._meetings.get(meet_code, {})
        venue = get_or_create_venue(db, name=meeting.get("venue", "Unknown"), vertical="horse_racing")

        races = json.loads(html).get("data", {}).get("getRacesForMeet") or []
        rows_written = 0

        for race in races:
            start_time = dt.datetime.fromisoformat(race["time"].replace("Z", "+00:00"))
            entries = race.get("formRaceEntries") or []
            has_results = any(e.get("finish") is not None for e in entries)

            event = get_or_create_event(
                db,
                external_key="racing_com_race_id",
                external_value=str(race["id"]),
                vertical="horse_racing",
                sport="horse_racing",
                start_time=start_time,
                venue_id=venue.id,
                status="completed" if has_results else "scheduled",
                race_number=race.get("raceNumber"),
            )

            for entry in entries:
                horse_name = entry.get("horseName")
                if not horse_name:
                    continue
                horse = get_or_create_horse(db, name=horse_name, external_id=entry.get("horseCode"))
                scratched = bool(entry.get("scratched"))
                # racing.com's API returns a literal 0 for barrierNumber when no real
                # barrier draw exists (scratched runners, and every runner in trial/jump-out
                # meetings) rather than omitting the field or returning null. 0 is never a
                # real barrier, so treat it the same as missing.
                barrier = entry.get("barrierNumber") or None

                participant = db.scalar(
                    select(EventParticipant).where(
                        EventParticipant.event_id == event.id,
                        EventParticipant.entity_type == "horse",
                        EventParticipant.entity_id == horse.id,
                    )
                )
                if participant is None:
                    db.add(
                        EventParticipant(
                            event_id=event.id,
                            entity_type="horse",
                            entity_id=horse.id,
                            barrier_or_number=barrier,
                            scratched=scratched,
                        )
                    )
                    rows_written += 1
                else:
                    participant.scratched = scratched
                    participant.barrier_or_number = barrier

                finish = entry.get("finish")
                if finish is not None and not scratched:
                    result = db.scalar(
                        select(Result).where(
                            Result.event_id == event.id,
                            Result.entity_type == "horse",
                            Result.entity_id == horse.id,
                        )
                    )
                    if result is None:
                        db.add(
                            Result(
                                event_id=event.id,
                                entity_type="horse",
                                entity_id=horse.id,
                                finish_position=finish,
                                margin=entry.get("margin"),
                            )
                        )
                        rows_written += 1

                for odds in entry.get("odds") or []:
                    provider = odds.get("providerCode")
                    for market_type, key in (("win", "oddsWin"), ("place", "oddsPlace")):
                        price = parse_price(odds.get(key))
                        if price is None:
                            continue
                        db.add(
                            OddsSnapshot(
                                event_id=event.id,
                                entity_type="horse",
                                entity_id=horse.id,
                                market_type=market_type,
                                price=price,
                                bookmaker=provider,
                                source_id=self.source_id,
                            )
                        )
                        rows_written += 1

        return rows_written
