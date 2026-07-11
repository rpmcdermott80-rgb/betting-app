"""alphr.com.au AFL/NRL tipster scraper. Feeds TipsterPick, never Tip/tips.

Found 2026-07-11 after KRUZEY turned out blocked — alphr.com.au's robots.txt is
unusually explicit about welcoming AI crawlers (ClaudeBot, GPTBot, PerplexityBot
all explicitly Allowed), and a real production fetch confirmed a normal 200 with
substantial, cleanly-structured server-rendered HTML (not a JS shell).

Discovery uses the site's own /sitemap.xml rather than the hub page — the hub only
ever shows the current/most-recent round (~7-9 matches), while the sitemap lists
every individual match page Alphr has ever published (369 AFL + 356 NRL as of
2026-07-11, plenty for a real sample size, not just today's snapshot). Each match
page has a clean "H2H Recommendation {Team} to Win @ {price}" line — read directly
as the pick, same principle as the hub cards. The site publishes its own backtested
strike rate prominently (including per-match "Won ✓"/"Lost ✗" labels), but per this
app's rule that a tipster's own claim is never trusted, none of that is read here —
outcomes are only ever settled from our own data (app/analysis/tipster_settle.py).

Alphr's own team-name spellings occasionally differ slightly from the official
names our afltables.com/rugbyleagueproject.org scrapers store (e.g. "GWS GIANTS"
vs "GWS", "Carlton Blues" vs "Carlton") — matching.find_event_for_teams already
does substring-based team matching for exactly this reason.

Every match page shows an H2H Recommendation regardless of whether it's actually
one of Alphr's own recommended bets — some have a negative or below-threshold
"Edge" (the model doesn't think the price offers value, just says who it expects
to win), which is not what "follow this tipster's real recommended plays" means.
2026-07-11: a first pass logging every H2H Recommendation gave a 35.2%/17.3%
verified win rate for AFL/NRL — real and correctly computed, but a poor read on
Alphr's actual recommended-bet performance since it mixed in these non-recommended
predictions. Per the user's explicit choice, only recommendations meeting Alphr's
own stated "Expert Play" criteria are logged now (AFL: edge ≥7%; NRL: edge ≥3% and
price ≥$1.40 — both pulled directly from Alphr's own published methodology text,
not guessed) — matches picks that don't qualify are skipped entirely, not stored
as some other status.
"""

import datetime as dt
import re

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import USER_AGENT, BaseScraper
from app.scrapers.tipsters.matching import find_event_for_teams
from app.scrapers.util import upsert_tipster_pick

SITEMAP_URL = "https://alphr.com.au/sitemap.xml"

TITLE_RE = re.compile(r"^(.+?)\s+vs\s+(.+?)\s+Tips\s*\|")
# Captures team, price, and the signed edge % together — e.g. "H2H Recommendation
# Essendon to Win @ 4.45 Lost ✗ Edge + 52.0 %" -> ("Essendon", "4.45", "+", "52.0").
# The Won/Lost text in between is skipped non-greedily; DOTALL since it can span
# the rendered whitespace/HTML-comment noise between the two lines.
WINNER_RE = re.compile(
    r"H2H Recommendation\s+([A-Z][A-Za-z\s]+?)\s+to Win\s*@\s*([\d.]+).*?"
    r"Edge\s*([+-])\s*([\d.]+)\s*%",
    re.S,
)
PUBLISHED_RE = re.compile(r"Published:\s*([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})")
SLUG_YEAR_RE = re.compile(r"/(?:afl|nrl)/match/(\d{4})-")
MONTHS = {m: i for i, m in enumerate(
    ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
) if m}


class AlphrFootballScraper(BaseScraper):
    sport: str
    match_url_prefix: str
    min_edge_pct: float
    min_price: float | None = None

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        resp = httpx.get(SITEMAP_URL, timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        urls = sorted(set(re.findall(rf"<loc>({re.escape(self.match_url_prefix)}[^<]+)</loc>", resp.text)))
        if limit is not None:
            urls = urls[:limit]
        return urls

    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        title_match = TITLE_RE.search(text)
        winner_match = WINNER_RE.search(text)
        if title_match is None or winner_match is None:
            return 0  # no clear pick on this page — nothing to log, not an error

        team_a, team_b = (t.strip() for t in title_match.groups())
        winner, price_str, edge_sign, edge_str = winner_match.groups()
        winner = winner.strip()
        price = float(price_str)
        edge_pct = float(edge_str) if edge_sign == "+" else -float(edge_str)

        # Only Alphr's own "Expert Play" tier counts as a real recommendation —
        # a negative or below-threshold edge means the model doesn't think the
        # price offers value, even though the page still names a predicted winner.
        if edge_pct < self.min_edge_pct or (self.min_price is not None and price < self.min_price):
            return 0

        year_match = SLUG_YEAR_RE.search(url)
        published_match = PUBLISHED_RE.search(text)
        if year_match is None:
            return 0
        year = int(year_match.group(1))
        if published_match:
            month_abbr, day, pub_year = published_match.groups()
            month = MONTHS.get(month_abbr)
            published_at = (
                dt.datetime(int(pub_year), month, int(day), tzinfo=dt.timezone.utc)
                if month
                else dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
            )
        else:
            published_at = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)

        raw_text = f"{team_a} vs {team_b}: {winner} to win"
        external_id = url

        event = find_event_for_teams(db, self.sport, team_a, team_b, published_at.date())
        resolved = event is not None

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
            recommended_side=winner,
            outcome="pending" if resolved else "unresolved",
        ):
            return 1
        return 0


class AlphrAFLScraper(AlphrFootballScraper):
    source_name = "Alphr (AFL)"
    sport = "afl"
    match_url_prefix = "https://alphr.com.au/afl/match/"
    # From Alphr's own /afl/expert-tips methodology text: "Edge ≥7% filter — only
    # picks where the model probability exceeds the bookmaker's implied
    # probability by at least 7% are published."
    min_edge_pct = 7.0


class AlphrNRLScraper(AlphrFootballScraper):
    source_name = "Alphr (NRL)"
    sport = "nrl"
    match_url_prefix = "https://alphr.com.au/nrl/match/"
    # From Alphr's own /nrl/expert-tips methodology text: "Back the head-to-head
    # pick only when the model's probability beats the market by at least 3
    # points (edge ≥+3%) and the price is $1.40 or better."
    min_edge_pct = 3.0
    min_price = 1.40
