"""Greyhound scraper via the Betfair Exchange API — every scraped greyhound source
(thedogs.com.au, racingandsports.com.au, greyhoundrecorder.com.au, grv.org.au) was
ruled out on 2026-07-10 for a genuine WAF block, an active bot challenge, an explicit
ToS prohibition, or simply not having the data. Betfair is free for personal/low
volume use and is a real API, not scraping.

NOTE: unverified end-to-end — needs real BETFAIR_APP_KEY/USERNAME/PASSWORD in .env,
which only the user can obtain (developer.betfair.com). The login/call shapes here
match Betfair's documented API-NG format and were checked against the live endpoint
(confirmed the real error shape for a missing app key), but the full flow hasn't
been exercised with real credentials yet.
"""

import datetime as dt
import json
import re

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EventParticipant, OddsSnapshot
from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.util import get_or_create_event, get_or_create_greyhound, get_or_create_venue

LOGIN_URL = "https://identitysso.betfair.com/api/login"
BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"

RUNNER_NAME_RE = re.compile(r"^(\d+)\.\s*(.+)$")


class BetfairAuthError(RuntimeError):
    pass


def login() -> str:
    if not (settings.betfair_app_key and settings.betfair_username and settings.betfair_password):
        raise BetfairAuthError(
            "Betfair credentials not configured — set BETFAIR_APP_KEY, BETFAIR_USERNAME, "
            "BETFAIR_PASSWORD in .env (see developer.betfair.com to obtain an app key)"
        )
    resp = httpx.post(
        LOGIN_URL,
        data={"username": settings.betfair_username, "password": settings.betfair_password},
        headers={
            "X-Application": settings.betfair_app_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("loginStatus") != "SUCCESS":
        # Betfair's loginStatus codes are self-explanatory (e.g. CERT_AUTH_REQUIRED means
        # this account needs certificate-based login instead of username/password).
        raise BetfairAuthError(f"Betfair login failed: {data.get('loginStatus')}")
    return data["sessionToken"]


def _call(method: str, session_token: str, params: dict) -> dict:
    resp = httpx.post(
        f"{BETTING_URL}/{method}/",
        json=params,
        headers={
            "X-Application": settings.betfair_app_key,
            "X-Authentication": session_token,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


class BetfairGreyhoundScraper(BaseScraper):
    source_name = "betfair"

    def __init__(self):
        self._catalogue: dict[str, dict] = {}
        self._session_token: str | None = None

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        self._session_token = login()

        event_types = _call("listEventTypes", self._session_token, {"filter": {}})
        greyhound = next(
            (et["eventType"] for et in event_types if "greyhound" in et["eventType"]["name"].lower()),
            None,
        )
        if greyhound is None:
            raise RuntimeError("Could not find a 'Greyhound Racing' event type in Betfair's listEventTypes response")

        catalogue = _call(
            "listMarketCatalogue",
            self._session_token,
            {
                "filter": {
                    "eventTypeIds": [greyhound["id"]],
                    "marketCountries": ["AU"],
                    "marketTypeCodes": ["WIN"],
                },
                "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME"],
                "maxResults": limit or 100,
            },
        )

        self._catalogue = {m["marketId"]: m for m in catalogue}
        return [f"{BETTING_URL}/listMarketBook?marketId={m['marketId']}" for m in catalogue]

    def fetch(self, url: str) -> str:
        market_id = url.rsplit("marketId=", 1)[-1]
        book = _call(
            "listMarketBook",
            self._session_token,
            {"marketIds": [market_id], "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}},
        )
        return json.dumps(book)

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        market_id = url.rsplit("marketId=", 1)[-1]
        catalogue_entry = self._catalogue.get(market_id)
        if catalogue_entry is None:
            return 0

        market_books = json.loads(html)
        if not market_books:
            return 0
        market_book = market_books[0]

        event_info = catalogue_entry.get("event", {})
        venue = get_or_create_venue(db, name=event_info.get("venue", "Unknown"), vertical="greyhound")
        start_time = dt.datetime.fromisoformat(catalogue_entry["marketStartTime"].replace("Z", "+00:00"))

        event = get_or_create_event(
            db,
            external_key="betfair_market_id",
            external_value=market_id,
            vertical="greyhound",
            sport="greyhound",
            start_time=start_time,
            venue_id=venue.id,
            status="completed" if market_book.get("status") == "CLOSED" else "scheduled",
        )

        runner_prices = {r["selectionId"]: r for r in market_book.get("runners", [])}
        rows_written = 0

        for runner in catalogue_entry.get("runners", []):
            match = RUNNER_NAME_RE.match(runner.get("runnerName", ""))
            box_number = int(match.group(1)) if match else None
            name = match.group(2) if match else runner.get("runnerName", "Unknown")

            greyhound = get_or_create_greyhound(db, name=name, external_id=str(runner.get("selectionId")))

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
                        scratched=False,
                    )
                )
                rows_written += 1

            price_info = runner_prices.get(runner["selectionId"])
            if price_info:
                backs = price_info.get("ex", {}).get("availableToBack", [])
                if backs:
                    db.add(
                        OddsSnapshot(
                            event_id=event.id,
                            entity_type="greyhound",
                            entity_id=greyhound.id,
                            market_type="win",
                            price=backs[0]["price"],
                            bookmaker="Betfair",
                            source_id=self.source_id,
                        )
                    )
                    rows_written += 1

        return rows_written
