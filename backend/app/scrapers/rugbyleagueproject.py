"""NRL reference scraper. Confirmed working 2026-07-10 — plain HTML, robots.txt only
blocks /matches/Custom and query-string URLs, no AI-crawler restriction.

Scrapes by MATCH, not by player. Each team's season summary page has a round-by-round
table with a match link per game — but match IDs are assigned for the whole season's
draw up front (including finals), so "highest ID" does NOT mean "most recently
played"; unplayed fixtures already have a link too. The reliable signal is whether the
row has a result (a <span class="w/l/d"> — present only once the game's been played).
Discovery keeps only the last few *completed* games per team (a small recent window,
same idea as racing_com.py's rolling date window), not the whole season — so a daily
run only touches genuinely new games, and get_or_create_event/upsert_player_game_log
still correctly no-op on anything already known.

Per match, two pages are needed: .../summary.html (redirect target of /matches/<id>,
has the real date) and .../stats.html (a clean per-player table with This-Match
tries/goals/field-goals/points, at fixed column positions since "T"/"G"/"FG"/"Pts"
each appear three times — this match, season-for-team, season-for-competition —
so header-name lookup would collide).
"""

import datetime as dt
import json
import re
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.util import (
    get_or_create_event,
    get_or_create_player,
    upsert_match_result,
    upsert_player_game_log,
)

DISCOVERY_DELAY_SECONDS = 1.5
RECENT_GAMES_PER_TEAM = 4  # small trailing window, not the whole season

STATS_ROW_LENGTH = 16
IDX_TRIES_THIS_MATCH = 2

# Real format confirmed 2026-07-11 against a live page (an earlier "X (Y) N lost to
# Z (Y) M" assumption, based on a research-tool summary rather than the actual
# HTML, turned out wrong — see feedback_source_vetting_production_test.md): the
# summary page's `<table class="program">` scoreboard flattens to e.g. "Wests
# Tigers 6 – 32 Warriors" (an en-dash between the two scores). Needed only for
# MatchResult (final score) to verify match-winner-style tipster picks.
SCORE_LINE_RE = re.compile(
    r"([A-Za-z][A-Za-z\s]*?)\s+(\d{1,3})\s*[–‒-]\s*(\d{1,3})\s+"
    r"([A-Za-z][A-Za-z\s]*?)(?=\s+Match Info)"
)


def _strip_ordinal(date_text: str) -> str:
    return re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_text)


class RugbyLeagueProjectScraper(BaseScraper):
    source_name = "rugbyleagueproject.org"

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        year = dt.datetime.now(dt.timezone.utc).year
        comp_url = "https://www.rugbyleagueproject.org/competitions/nrl/summary.html"
        resp = httpx.get(comp_url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        team_urls = sorted(set(re.findall(rf'href="(/seasons/nrl-{year}/[^"]+/summary\.html)"', resp.text)))

        match_ids: set[int] = set()
        for team_path in team_urls:
            time.sleep(DISCOVERY_DELAY_SECONDS)
            try:
                r = httpx.get(urljoin(comp_url, team_path), timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            except Exception:
                continue  # one team roster failing shouldn't abort discovery for the rest

            soup = BeautifulSoup(r.text, "lxml")
            played_ids: list[int] = []
            for tr in soup.find_all("tr"):
                result_span = tr.find("span", class_=("w", "l", "d"))
                link = tr.find("a", class_="rlplnk", href=re.compile(r"/matches/\d+"))
                if result_span is None or link is None:
                    continue
                played_ids.append(int(link["href"].rsplit("/", 1)[-1]))

            match_ids.update(played_ids[-RECENT_GAMES_PER_TEAM:])

        candidate_ids = sorted(match_ids, reverse=True)
        if limit is not None:
            candidate_ids = candidate_ids[:limit]
        return [f"https://www.rugbyleagueproject.org/matches/{mid}" for mid in candidate_ids]

    def fetch(self, url: str) -> str:
        resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        canonical_url = str(resp.url)
        summary_html = resp.text

        stats_url = canonical_url.replace("/summary.html", "/stats.html")
        time.sleep(1.5)
        stats_resp = httpx.get(stats_url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        stats_resp.raise_for_status()

        return json.dumps({"canonical_url": canonical_url, "summary_html": summary_html, "stats_html": stats_resp.text})

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        data = json.loads(html)
        canonical_url = data["canonical_url"]

        summary_soup = BeautifulSoup(data["summary_html"], "lxml")

        status_th = summary_soup.find("th", string="Status")
        status = status_th.find_next("td").get_text(strip=True) if status_th else ""
        if status != "Completed":
            return 0  # future/scheduled fixture — nothing to record yet, not an error

        date_th = summary_soup.find("th", string="Date")
        if date_th is None:
            return 0
        date_text = _strip_ordinal(date_th.find_next("td").get_text(strip=True))
        try:
            start_time = dt.datetime.strptime(date_text, "%A, %d %B, %Y").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return 0

        event = get_or_create_event(
            db,
            external_key="rlp_match_url",
            external_value=canonical_url,
            vertical="player_prop",
            sport="nrl",
            start_time=start_time,
        )

        rows_written = 0
        score_match = SCORE_LINE_RE.search(summary_soup.get_text(" ", strip=True))
        if score_match:
            home_team, home_score, away_score, away_team = score_match.groups()
            if upsert_match_result(
                db, event.id, home_team.strip(), away_team.strip(), int(home_score), int(away_score)
            ):
                rows_written += 1

        stats_soup = BeautifulSoup(data["stats_html"], "lxml")

        for table in stats_soup.find_all("table", class_="list"):
            heading = table.find_previous(["h2", "h3", "h4"])
            team = heading.get_text(strip=True) if heading else None

            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) != STATS_ROW_LENGTH:
                    continue

                name_link = cells[0].find("a")
                if name_link is None or not name_link.get("href"):
                    continue
                player_name = cells[0].get_text(strip=True)
                # table shows "LASTNAME, Firstname" — reformat to "Firstname Lastname"
                # to match the name format used elsewhere for the same players.
                if "," in player_name:
                    last, first = [p.strip() for p in player_name.split(",", 1)]
                    player_name = f"{first} {last.title()}"

                player = get_or_create_player(db, player_name, sport="nrl", team=team)

                tries_text = cells[IDX_TRIES_THIS_MATCH].get_text(strip=True)
                tries = float(tries_text) if tries_text.replace(".", "", 1).isdigit() else 0.0

                if upsert_player_game_log(db, player.id, event.id, "tries", tries, self.source_id):
                    rows_written += 1

        return rows_written
