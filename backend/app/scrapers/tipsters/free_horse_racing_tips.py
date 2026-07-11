"""freehorseracingtipsaustralia.com.au horse racing tipster scraper. Feeds
TipsterPick, never Tip/tips. See app/sources.py for the robots.txt/production-fetch
vetting notes (this one actually passed a real request from our scraper, unlike
KRUZEY, which looked clean but 403s every real request).

Single page (/free-horse-racing-tips/), updated in place through the day — no
per-day archive URLs exist, so there's nothing to "discover" beyond this one URL.
Real structure: a `<div class='meetings'>` containing one `<div class='meeting'>`
per venue, each with an `<h5 class='meeting-title'>VENUE race tips:</h5>` heading.
Selections for a venue aren't posted until "no later than" a stated time each
morning (QLD time) — fetched before that, a meeting's div still holds a "Tips will
be posted here..." placeholder, correctly 0 rows, not an error. The free tier only
ever covers each meeting's first three races (Premium-only beyond that) — per the
site's own FAQ, never scraped since that's paywalled.

Confirmed against a real populated page 2026-07-11: each race line is runner
NUMBERS in order of preference, not horse names — e.g. "Race 3: (P) 3, 5, 7, 17 -
Winner (1) $3.90 Exacta $21.80 Trifecta $103.70". The leading status code in
brackets ((P)/(*)/(O)/etc) is some meeting/going marker, not part of the pick.
The site's own "Winner (K) $X.XX" is THEIR self-reported result of which of their
4 selections actually won — deliberately ignored here; we settle every pick
against our own Result data instead (see app/analysis/tipster_settle.py), never a
tipster's own claim. The top pick (first number listed) is resolved to a horse via
our own EventParticipant.barrier_or_number for that race, not by name-matching.
"""

import datetime as dt
import re

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import BaseScraper
from app.scrapers.tipsters.matching import find_event_for_race, find_horse_by_barrier, find_venue
from app.scrapers.util import upsert_tipster_pick

PAGE_URL = "https://www.freehorseracingtipsaustralia.com.au/free-horse-racing-tips/"

# "Race 3: (P) 3, 5, 7, 17 - Winner ..." -> race_number=3, top_pick_barrier=3.
# Only the first number after the status parenthetical is taken (their #1 selection).
PICK_RE = re.compile(r"Race\s*(\d+):\s*\([^)]*\)\s*(\d+)")


class FreeHorseRacingTipsScraper(BaseScraper):
    source_name = "freehorseracingtipsaustralia.com.au"

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        return [PAGE_URL]

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        soup = BeautifulSoup(html, "lxml")
        today = dt.datetime.now(dt.timezone.utc).date()
        published_at = dt.datetime.combine(today, dt.time(11, 0), tzinfo=dt.timezone.utc)

        rows_written = 0
        for meeting in soup.select("div.meeting"):
            title_el = meeting.select_one(".meeting-title")
            if title_el is None:
                continue
            venue_name = title_el.get_text(strip=True).removesuffix("race tips:").strip()
            venue = find_venue(db, venue_name, vertical="horse_racing")

            block_text = meeting.get_text(" ", strip=True)
            if "will be posted" in block_text.lower():
                continue  # not dropped yet today — not an error, nothing to write

            for pick_match in PICK_RE.finditer(block_text):
                race_number, barrier = (int(g) for g in pick_match.groups())
                raw_text = pick_match.group(0)
                external_id = f"{url}#{venue_name}-race{race_number}-{today.isoformat()}"

                event = (
                    find_event_for_race(db, venue, "horse_racing", race_number, today)
                    if venue
                    else None
                )
                horse = find_horse_by_barrier(db, event, barrier) if event else None
                resolved = horse is not None

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
