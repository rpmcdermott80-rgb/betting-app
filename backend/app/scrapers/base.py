"""Scraper orchestrator: fetch -> raw_scrapes (always) -> source_health update -> parse/store.

Hard rule: a fetch failure never fabricates data downstream. Every attempt lands in
raw_scrapes regardless of outcome, and source_health tracks consecutive failures so a
blocked source shows up honestly in the Data Health tab instead of going silently stale.
"""

import abc
import datetime as dt
import time

import httpx
from sqlalchemy.orm import Session

from app.models import RawScrape, SourceHealth
from app.scrapers.util import get_source

USER_AGENT = "Mozilla/5.0 (compatible; personal-betting-research-bot/0.1; +local use only)"
FAILURE_THRESHOLD = 3
REQUEST_DELAY_SECONDS = 1.5


class BaseScraper(abc.ABC):
    source_name: str
    source_id: int | None = None

    def get_urls(self, db: Session, limit: int | None = None) -> list[str]:
        """Concrete URLs to fetch this run. Override for real discovery logic.

        `limit` is a hint for discovery to stop early (e.g. resolving fewer player
        IDs) — implementations that do multi-step discovery should respect it so a
        small test run doesn't pay the full discovery cost.
        """
        raise NotImplementedError

    def fetch(self, url: str) -> str:
        resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.text

    @abc.abstractmethod
    def parse_and_store(self, html: str, url: str, db: Session) -> int:
        """Parse fetched HTML and write rows to domain tables. Returns rows written."""

    def run(self, db: Session, limit: int | None = None) -> dict:
        source = get_source(db, self.source_name)
        self.source_id = source.id
        health = db.get(SourceHealth, source.id)
        if health is None:
            health = SourceHealth(source_id=source.id, status="unknown")
            db.add(health)

        health.last_attempt_at = dt.datetime.now(dt.timezone.utc)
        try:
            urls = self.get_urls(db, limit=limit)
        except Exception as e:
            health.consecutive_failures += 1
            health.last_error = f"discovery failed: {e}"
            health.status = "blocked" if health.consecutive_failures >= FAILURE_THRESHOLD else "degraded"
            db.add(RawScrape(source_id=source.id, url="<discovery>", raw_payload=None, parse_status="failed", error_message=str(e)))
            db.commit()
            return {"urls": 0, "fetched": 0, "failed": 1, "rows_written": 0, "error": "discovery failed"}

        if limit is not None:
            urls = urls[:limit]

        fetched, failed, rows_written = 0, 0, 0

        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(REQUEST_DELAY_SECONDS)
            health.last_attempt_at = dt.datetime.now(dt.timezone.utc)
            try:
                html = self.fetch(url)
            except Exception as e:
                failed += 1
                health.consecutive_failures += 1
                health.last_error = str(e)
                health.status = "blocked" if health.consecutive_failures >= FAILURE_THRESHOLD else "degraded"
                db.add(RawScrape(source_id=source.id, url=url, raw_payload=None, parse_status="failed", error_message=str(e)))
                db.commit()
                continue

            fetched += 1
            health.consecutive_failures = 0
            health.last_success_at = dt.datetime.now(dt.timezone.utc)
            health.status = "healthy"
            health.last_error = None

            raw = RawScrape(source_id=source.id, url=url, raw_payload={"text": html}, parse_status="pending")
            db.add(raw)
            db.flush()

            try:
                n = self.parse_and_store(html, url, db)
                rows_written += n
                raw.parse_status = "processed"
            except Exception as e:
                raw.parse_status = "failed"
                raw.error_message = str(e)

            db.commit()

        return {"urls": len(urls), "fetched": fetched, "failed": failed, "rows_written": rows_written}
