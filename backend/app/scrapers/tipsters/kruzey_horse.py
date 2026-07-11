"""KRUZEY horse racing tipster scraper. Feeds TipsterPick, never Tip/tips — this is
the separate "follow a real tipster, verify our own win-rate" feature, structurally
isolated from the app's own real-data-only analysis. See app/sources.py for the
robots.txt vetting notes.

Discovers today's per-venue tip pages from the /horse-racing-tips/ hub, then parses
each venue page's finalized race-by-race win selections (posted "around 10am race
morning" per the site itself — pages fetched earlier in the day may have no
selections yet, which is not an error, just nothing to write).
"""

import datetime as dt
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.tipsters.matching import find_event_for_race, find_horse, find_venue, runner_is_in_race
from app.scrapers.util import upsert_tipster_pick

HUB_URL = "https://www.kruzey.com.au/horse-racing-tips/"

PAGE_URL_RE = re.compile(r'href="(https://www\.kruzey\.com\.au/horse-racing-tips/[\w-]+-tips-\d{1,2}-[a-z]{3}-\d{4}/)"')
SLUG_RE = re.compile(r"/horse-racing-tips/(.+)-tips-(\d{1,2})-([a-z]{3})-(\d{4})/?$")

# Tolerant of both "#9 Talavera $6.00" and "9. Talavera $6.00" style barrier/number
# prefixes seen across different render passes of the same content.
PICK_RE = re.compile(
    r"Race\s+(\d+)\s*\([^)]*\)\s*:?\s*#?(\d{1,2})[.\s]+"
    r"([A-Z][A-Za-z''\-]*(?:\s[A-Z][A-Za-z''\-]*)*)\s*\$(\d+\.\d{2})"
)


class KruzeyHorseScraper(BaseScraper):
    source_name = "KRUZEY (horse racing)"

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        resp = httpx.get(HUB_URL, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        urls = sorted(set(urljoin(HUB_URL, m) for m in PAGE_URL_RE.findall(resp.text)))
        if limit is not None:
            urls = urls[:limit]
        return urls

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        slug_match = SLUG_RE.search(url)
        if slug_match is None:
            return 0
        venue_slug, day, mon, year = slug_match.groups()
        venue_display = venue_slug.replace("-", " ").title()
        try:
            race_date = dt.datetime.strptime(f"{day} {mon} {year}", "%d %b %Y").date()
        except ValueError:
            return 0

        published_at = dt.datetime.combine(race_date, dt.time(10, 0), tzinfo=dt.timezone.utc)
        venue = find_venue(db, venue_display, vertical="horse_racing")

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        rows_written = 0
        for m in PICK_RE.finditer(text):
            race_number, _barrier, horse_name, price = m.groups()
            race_number = int(race_number)
            raw_text = m.group(0)
            external_id = f"{url}#race{race_number}"

            event = find_event_for_race(db, venue, "horse_racing", race_number, race_date) if venue else None
            horse = find_horse(db, horse_name)

            resolved = (
                event is not None
                and horse is not None
                and runner_is_in_race(db, event, "horse", horse.id)
            )

            if upsert_tipster_pick(
                db,
                source_id=self.source_id,
                sport="horse_racing",
                published_at=published_at,
                raw_selection_text=raw_text,
                external_id=external_id,
                entity_type="horse" if resolved else None,
                entity_id=horse.id if resolved else None,
                event_id=event.id if resolved else None,
                market_type="win" if resolved else None,
                recommended_side="win" if resolved else None,
                outcome="pending" if resolved else "unresolved",
            ):
                rows_written += 1

        return rows_written
