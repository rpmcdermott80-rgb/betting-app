"""Shared base for KRUZEY's AFL/NRL match-winner tipster scrapers. Feeds
TipsterPick, never Tip/tips. Unlike KRUZEY's horse racing tips (clean per-race win
selections), AFL/NRL predictions are prose ("I've got the Blues to win", "Nobody is
tipping against the Roosters... us included") written inconsistently even within the
same author, let alone between the two different tipsters KRUZEY uses for AFL vs
NRL. _extract_winner tries a small library of common phrasings; if none match, the
pick is still logged (raw text preserved) but recommended_side/outcome stay
unresolved rather than guessing which team was actually tipped.

Verifying these needs a real final score per match, which our own analysis never
tracked before (only PlayerGameLog) — see MatchResult (app/models.py) and the score
parsing added to afltables.py/rugbyleagueproject.org's parse_and_store.
"""

import datetime as dt
import re

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.tipsters.matching import find_event_for_teams, resolve_team_name
from app.scrapers.util import upsert_tipster_pick

# Tried in order; first match wins. Deliberately conservative — a phrasing that
# doesn't fit any of these leaves the pick unresolved rather than guessing.
WINNER_PHRASES = [
    re.compile(r"I['’]ve\s+(?:got|still\s+got)\s+the\s+([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?)\s+(?:winning|to win)"),
    re.compile(r"I['’]m\s+backing\s+the\s+([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?)"),
    re.compile(r"tipping\s+against\s+the\s+([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?)"),  # negated below
    re.compile(r"back\s+the\s+([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?)\s+(?:to win|here)"),
]


def _extract_winner(text: str, team_a: str, team_b: str, nickname_map: dict[str, str]) -> str | None:
    for i, pattern in enumerate(WINNER_PHRASES):
        m = pattern.search(text)
        if not m:
            continue
        mentioned = resolve_team_name(m.group(1), nickname_map)
        # "tipping against the X" means the OTHER team wins.
        if i == 2:
            if mentioned.lower() == team_a.lower():
                return team_b
            if mentioned.lower() == team_b.lower():
                return team_a
            continue
        if mentioned.lower() == team_a.lower():
            return team_a
        if mentioned.lower() == team_b.lower():
            return team_b
    return None


class KruzeyFootballScraper(BaseScraper):
    sport: str
    hub_url: str
    link_re: re.Pattern
    slug_re: re.Pattern
    nickname_map: dict[str, str]

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        resp = httpx.get(self.hub_url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        urls = sorted(set(self.link_re.findall(resp.text)))
        if limit is not None:
            urls = urls[:limit]
        return urls

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        slug_match = self.slug_re.search(url)
        if slug_match is None:
            return 0  # e.g. non-dated special pages like a State of Origin preview
        team_a_slug, team_b_slug, day, mon, year = slug_match.groups()
        team_a = resolve_team_name(team_a_slug.replace("-", " "), self.nickname_map)
        team_b = resolve_team_name(team_b_slug.replace("-", " "), self.nickname_map)
        try:
            match_date = dt.datetime.strptime(f"{day} {mon} {year}", "%d %m %y").date()
        except ValueError:
            return 0

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        published_at = dt.datetime.combine(match_date, dt.time(9, 0), tzinfo=dt.timezone.utc)

        winner = _extract_winner(text, team_a, team_b, self.nickname_map)
        # The game usually hasn't been played yet, so our own Event for it may not
        # exist until afltables.com/rugbyleagueproject.org scrape it afterwards —
        # that's retried later by tipster_settle.py's re-resolution pass, not here.
        event = find_event_for_teams(db, self.sport, team_a, team_b, match_date)
        resolved = winner is not None and event is not None

        external_id = url
        raw_text = f"{team_a} vs {team_b}: " + (winner or "no clear winner phrase found")

        if upsert_tipster_pick(
            db,
            source_id=self.source_id,
            sport=self.sport,
            published_at=published_at,
            raw_selection_text=raw_text,
            external_id=external_id,
            entity_type="team" if resolved else None,
            entity_id=None,
            event_id=event.id if resolved else None,
            market_type="match_winner" if resolved else None,
            # Keep the picked team name even when the event isn't matched yet, so
            # a later re-scrape/settlement pass can still re-attempt the match.
            recommended_side=winner,
            outcome="pending" if resolved else "unresolved",
        ):
            return 1
        return 0
