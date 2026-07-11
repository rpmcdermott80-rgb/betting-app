"""AFL reference scraper. Confirmed working 2026-07-10 — plain HTML, no robots.txt,
no AI-crawler restrictions. See app/sources.py for the discovery notes.

Scrapes by GAME, not by player: /afl/seas/<year>.html lists every game played this
season, and each game's boxscore page (/afl/stats/games/<year>/<code>.html) lists
every player from both teams with their per-game stats in one request. Discovery
skips games we already have an Event for (matched on the same external_id used by
the original per-player scraper, so this is a drop-in replacement, not a parallel
data source) — so a daily run only touches genuinely new games, not the whole
current-season roster every time.
"""

import datetime as dt
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Event
from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.util import (
    get_or_create_event,
    get_or_create_player,
    upsert_match_result,
    upsert_player_game_log,
)

STAT_COLUMNS = {"DI": "disposals", "GL": "goals"}

# Real format confirmed 2026-07-11 against a live page (an earlier "X defeated Y"
# sentence assumption, based on a research-tool summary rather than the actual
# HTML, turned out wrong — see feedback_source_vetting_production_test.md): each
# team's line is its 4 quarter scores as "goals.behinds. runningTotal", e.g.
# "Essendon 2.1. 13 3.3. 21 4.5. 29 7.8. 50 St Kilda 5.4. 34 13.8. 86 14.10. 94
# 17.15. 117" — the last number after the 4th quarter is that team's final score.
# Needed only for MatchResult (final score) — verifying match-winner-style tipster
# picks, since our own analysis never needed team-level results before.
_QTR = r"\d{1,2}\.\d{1,2}\.\s*\d{1,3}\s+"
SCORE_LINE_RE = re.compile(
    rf"([A-Za-z][A-Za-z\s]*?)\s+(?:{_QTR}){{3}}\d{{1,2}}\.\d{{1,2}}\.\s*(\d{{1,3}})\s+"
    rf"([A-Za-z][A-Za-z\s]*?)\s+(?:{_QTR}){{3}}\d{{1,2}}\.\d{{1,2}}\.\s*(\d{{1,3}})"
)


class AFLTablesScraper(BaseScraper):
    source_name = "afltables.com"

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        year = dt.datetime.now(dt.timezone.utc).year
        season_url = f"https://afltables.com/afl/seas/{year}.html"
        resp = httpx.get(season_url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()

        links = re.findall(r'href="([^"]*stats/games/\d{4}[^"]*)"', resp.text)
        game_urls: list[str] = []
        for link in links:
            full = urljoin(season_url, link)
            if full not in game_urls:
                game_urls.append(full)

        existing = {
            e.external_ids.get("afltables_game_url")
            for e in db.query(Event).filter(Event.sport == "afl").all()
            if e.external_ids and "afltables_game_url" in e.external_ids
        }
        new_urls = [u for u in game_urls if u not in existing]

        if limit is not None:
            new_urls = new_urls[:limit]
        return new_urls

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        date_match = re.search(r"(\d{8})\.html$", url)
        if not date_match:
            return 0
        start_time = dt.datetime.strptime(date_match.group(1), "%Y%m%d").replace(tzinfo=dt.timezone.utc)

        event = get_or_create_event(
            db,
            external_key="afltables_game_url",
            external_value=url,
            vertical="player_prop",
            sport="afl",
            start_time=start_time,
        )

        soup = BeautifulSoup(html, "lxml")
        rows_written = 0

        score_match = SCORE_LINE_RE.search(soup.get_text(" ", strip=True))
        if score_match:
            home_team, home_score, away_team, away_score = score_match.groups()
            if upsert_match_result(
                db, event.id, home_team.strip(), away_team.strip(), int(home_score), int(away_score)
            ):
                rows_written += 1

        for table in soup.find_all("table", class_="sortable"):
            header = table.find("th", attrs={"colspan": True})
            if header is None or "Match Statistics" not in header.get_text():
                continue
            team = header.get_text(strip=True).split(" Match Statistics")[0]
            headers = [th.get_text(strip=True) for th in table.find_all("tr")[1].find_all("th")]

            tbody = table.find("tbody")
            if tbody is None:
                continue

            for tr in tbody.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) != len(headers):
                    continue
                cell_map = dict(zip(headers, cells))

                player_cell = cell_map.get("Player")
                link = player_cell.find("a") if player_cell else None
                if link is None or not link.get("href"):
                    continue
                # derive name from the URL (e.g. players/M/Matt_Crouch.html) to match
                # the same name format used elsewhere, not the "Last, First" display text
                player_name = link["href"].rsplit("/", 1)[-1].removesuffix(".html").replace("_", " ")
                player = get_or_create_player(db, player_name, sport="afl", team=team)

                for header_key, stat_type in STAT_COLUMNS.items():
                    cell = cell_map.get(header_key)
                    if cell is None:
                        continue
                    text = cell.get_text(strip=True)
                    value = float(text) if text else 0.0
                    if upsert_player_game_log(db, player.id, event.id, stat_type, value, self.source_id):
                        rows_written += 1

        return rows_written
