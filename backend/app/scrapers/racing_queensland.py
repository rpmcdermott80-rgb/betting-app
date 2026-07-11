"""Queensland greyhound scraper. Confirmed working 2026-07-10.

racingqueensland.com.au's robots.txt is fully permissive. Race data comes from a
same-origin API (api.racingqueensland.com.au, no robots.txt of its own either)
authenticated with a JWT embedded server-side in every page load (window.apiToken) —
public, refreshed per page-load rather than a fixed static key, but the same "shipped
to every visitor's browser" trust model as racing.com's key. The API call also needs
the session cookie set on that same page load and a Referer header, or it 401s.

Scope: Queensland tracks only (this scraper doesn't cover VIC/NSW/SA/WA greyhound
racing) — a real but partial greyhound source, paired with Betfair for national
coverage and live odds.

Three calls: getcurrentschedule (www host, no auth) lists which tracks race on which
dates; a page load grabs a fresh token+cookie; /api/greyhound/meetings lists races for
one track/date; /api/greyhound/races returns full runner detail (box, trainer,
result, starting price, form) for one race.
"""

import datetime as dt
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.models import EventParticipant, OddsSnapshot, Result
from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.util import get_or_create_event, get_or_create_greyhound, get_or_create_venue, parse_price

WWW_BASE = "https://www.racingqueensland.com.au"
API_BASE = "https://api.racingqueensland.com.au"
QLD_TZ = dt.timezone(dt.timedelta(hours=10))  # Queensland doesn't observe daylight saving


class RacingQueenslandScraper(BaseScraper):
    source_name = "racingqueensland.com.au"

    def __init__(self):
        self._client: httpx.Client | None = None
        self._token: str | None = None
        self._race_meta: dict[str, dict] = {}

    def _auth_headers(self) -> dict:
        return {"Authorization": f"bearer {self._token}", "Referer": f"{WWW_BASE}/"}

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)

        schedule = self._client.get(f"{WWW_BASE}/api/calendar/getcurrentschedule")
        schedule.raise_for_status()
        meetings = []
        for day in schedule.json().get("data", []):
            for m in day["meetings"]:
                if m["racingCode"] == "Greyhound":
                    meetings.append(
                        {
                            "date": day["date"][:10],
                            "trackCode": m["trackCode"].strip().lower(),
                            "trackName": m["trackName"],
                        }
                    )

        if not meetings:
            return []

        # A single page load hands us a fresh token + session cookie (window.apiToken),
        # needed for every api.racingqueensland.com.au call below.
        first = meetings[0]
        page_url = f"{WWW_BASE}/racing/full-calendar/greyhound/meeting/{first['trackCode']}/{first['date'].replace('-', '')}"
        page = self._client.get(page_url)
        match = re.search(r"window\.apiToken = '([^']+)'", page.text)
        if not match:
            raise RuntimeError("Could not find window.apiToken on a Racing Queensland page")
        self._token = match.group(1)

        race_urls: list[str] = []
        for meeting in meetings:
            if limit is not None and len(race_urls) >= limit:
                break
            resp = self._client.get(
                f"{API_BASE}/api/greyhound/meetings",
                params={"date": meeting["date"], "trackCode": meeting["trackCode"]},
                headers=self._auth_headers(),
            )
            if resp.status_code != 200:
                continue
            for race in resp.json().get("Races", []):
                url = (
                    f"{API_BASE}/api/greyhound/races?date={meeting['date']}"
                    f"&trackCode={meeting['trackCode']}&raceNumber={race['RaceNumber']}"
                )
                self._race_meta[url] = {"trackName": meeting["trackName"]}
                race_urls.append(url)

        if limit is not None:
            race_urls = race_urls[:limit]
        return race_urls

    def fetch(self, url: str) -> str:
        resp = self._client.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.text

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        data = json.loads(html)
        meta = self._race_meta.get(url, {})
        venue = get_or_create_venue(db, name=meta.get("trackName", data.get("TrackName", "Unknown")), vertical="greyhound")
        start_time = dt.datetime.fromisoformat(data["StartTime"]).replace(tzinfo=QLD_TZ)

        event = get_or_create_event(
            db,
            external_key="rq_race_id",
            external_value=str(data["RaceID"]),
            vertical="greyhound",
            sport="greyhound",
            start_time=start_time,
            venue_id=venue.id,
            status="completed" if data.get("HasResults") else "scheduled",
            race_number=data.get("RaceNumber"),
        )

        rows_written = 0
        for runner in data.get("Runners", []):
            name = runner.get("Name")
            if not name:
                continue
            greyhound = get_or_create_greyhound(db, name=name, external_id=str(runner.get("AnimalID")))
            scratched = bool(runner.get("Scratched"))
            box_raw = runner.get("Box")
            box_number = int(box_raw) if box_raw and str(box_raw).isdigit() else None

            existing = db.query(EventParticipant).filter(
                EventParticipant.event_id == event.id,
                EventParticipant.entity_type == "greyhound",
                EventParticipant.entity_id == greyhound.id,
            ).first()
            if existing is None:
                db.add(
                    EventParticipant(
                        event_id=event.id,
                        entity_type="greyhound",
                        entity_id=greyhound.id,
                        barrier_or_number=box_number,
                        scratched=scratched,
                    )
                )
                rows_written += 1
            else:
                existing.scratched = scratched
                existing.barrier_or_number = box_number

            position = runner.get("Position")
            if position is not None and not scratched:
                existing_result = db.query(Result).filter(
                    Result.event_id == event.id,
                    Result.entity_type == "greyhound",
                    Result.entity_id == greyhound.id,
                ).first()
                if existing_result is None:
                    db.add(
                        Result(
                            event_id=event.id,
                            entity_type="greyhound",
                            entity_id=greyhound.id,
                            finish_position=position,
                            margin=runner.get("Margin"),
                        )
                    )
                    rows_written += 1

            price = parse_price(runner.get("StartingPrice"))
            if price is not None:
                db.add(
                    OddsSnapshot(
                        event_id=event.id,
                        entity_type="greyhound",
                        entity_id=greyhound.id,
                        market_type="win",
                        price=price,
                        bookmaker="TAB (SP)",
                        source_id=self.source_id,
                    )
                )
                rows_written += 1

        return rows_written
