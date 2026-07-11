"""Runs all production scrapers + tip generation as one job, tracked in refresh_runs
so both the scheduled nightly run and the manual "Refresh now" button share the same
path and the UI can show real status instead of guessing.

Betfair is deliberately excluded here — it's disabled in the source registry (no
credentials configured), so including it would just add a guaranteed failure to every
run. It's still runnable manually via `python -m app.run_scraper betfair` if that
changes.
"""

import datetime as dt

from sqlalchemy.orm import Session

from app.analysis import form_tips
from app.analysis.multis import generate_multis
from app.analysis.player_props import generate_tips
from app.analysis.settle_bets import settle_pending_bets
from app.analysis.tipster_settle import settle_pending_picks
from app.db import SessionLocal
from app.enrich import greyhound_form, horse_form
from app.models import RefreshRun
from app.scrapers.afltables import AFLTablesScraper
from app.scrapers.racing_com import RacingComScraper
from app.scrapers.racing_queensland import RacingQueenslandScraper
from app.scrapers.rugbyleagueproject import RugbyLeagueProjectScraper
from app.scrapers.tipsters.alphr_football import AlphrAFLScraper, AlphrNRLScraper
from app.scrapers.tipsters.free_horse_racing_tips import FreeHorseRacingTipsScraper

PRODUCTION_SCRAPERS = {
    "afltables": AFLTablesScraper,
    "rlp": RugbyLeagueProjectScraper,
    "racing_com": RacingComScraper,
    "racing_qld": RacingQueenslandScraper,
}

# Separate from PRODUCTION_SCRAPERS so a future tipster source being disabled (e.g.
# if it starts blocking us like KRUZEY did) doesn't need touching the primary-data
# list above — these feed TipsterPick, never Tip.
TIPSTER_SCRAPERS = {
    "free_horse_tips": FreeHorseRacingTipsScraper,
    "alphr_afl": AlphrAFLScraper,
    "alphr_nrl": AlphrNRLScraper,
}

# rugbyleagueproject.org's discovery phase (resolving each player ID to its slug)
# is what triggered a rate-limit/block earlier — an unlimited daily crawl would
# repeat that same large burst every single run. Capped here; the other scrapers
# are naturally bounded by their own current-window discovery (season roster,
# today's meetings) so they don't carry the same risk.
SCRAPER_LIMITS = {
    "rlp": 100,
}

STALE_RUN_HOURS = 2


def is_refresh_running(db: Session) -> bool:
    latest = db.query(RefreshRun).order_by(RefreshRun.started_at.desc()).first()
    if latest is None or latest.status != "running":
        return False
    age = dt.datetime.now(dt.timezone.utc) - latest.started_at
    if age > dt.timedelta(hours=STALE_RUN_HOURS):
        # A previous run never finished (e.g. the process crashed) — don't block forever.
        latest.status = "failed"
        latest.finished_at = dt.datetime.now(dt.timezone.utc)
        latest.summary = {**(latest.summary or {}), "note": "marked failed: stale/stuck run"}
        db.commit()
        return False
    return True


def start_refresh_run(db: Session) -> RefreshRun:
    """Synchronously creates the run row so callers get a real id immediately;
    the actual scraping work happens separately via execute_refresh."""
    run = RefreshRun(status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_refresh(run_id: int) -> None:
    """Does the actual scraping + tip generation for an already-created run row.
    Uses its own DB session since this typically runs on a background thread."""
    db = SessionLocal()
    summary: dict = {}
    try:
        run = db.get(RefreshRun, run_id)

        for name, scraper_cls in PRODUCTION_SCRAPERS.items():
            try:
                summary[name] = scraper_cls().run(db, limit=SCRAPER_LIMITS.get(name))
            except Exception as e:
                summary[name] = {"error": str(e)}

        # Settling bets only needs fresh Results (written by the racing scrapers above),
        # not the form/tip-generation steps below, so it can run right here.
        try:
            summary["bet_settlement"] = settle_pending_bets(db)
        except Exception as e:
            summary["bet_settlement_error"] = str(e)

        # Tipster scrapers need this run's fresh Events/Results/MatchResults already in
        # place to match picks against, so they run after the primary scrapers above.
        for name, scraper_cls in TIPSTER_SCRAPERS.items():
            try:
                summary[name] = scraper_cls().run(db)
            except Exception as e:
                summary[name] = {"error": str(e)}

        try:
            summary["tipster_settlement"] = settle_pending_picks(db)
        except Exception as e:
            summary["tipster_settlement_error"] = str(e)

        # Form enrichment must run after the scrapers (which refresh the scheduled-race
        # fields) and before tip generation (which reads the enriched form_starts).
        for name, enricher in (("horse_form", horse_form), ("greyhound_form", greyhound_form)):
            try:
                summary[name] = enricher.run(db)
            except Exception as e:
                summary[name] = {"error": str(e)}

        try:
            summary["player_prop_tips"] = generate_tips(db)
        except Exception as e:
            summary["player_prop_tips_error"] = str(e)

        try:
            summary["form_tips"] = form_tips.generate_all(db)
        except Exception as e:
            summary["form_tips_error"] = str(e)

        try:
            summary["multis"] = generate_multis(db)  # built from the player-prop tips above
        except Exception as e:
            summary["multis_error"] = str(e)

        run.status = "completed"
    except Exception as e:
        run = db.get(RefreshRun, run_id)
        run.status = "failed"
        summary["fatal_error"] = str(e)
    finally:
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.summary = summary
        db.commit()
        db.close()


def run_full_refresh() -> None:
    """Convenience wrapper for the scheduler: creates its own run row and executes
    it in one call (no separate thread needed, since APScheduler already runs this
    off the main event loop)."""
    db = SessionLocal()
    try:
        run = start_refresh_run(db)
    finally:
        db.close()
    execute_refresh(run.id)


def run_tipster_refresh() -> None:
    """Separate, lighter cron job for tipster scraping alone. freehorseracingtips-
    australia.com.au (and any future daily tipster source) posts selections mid-
    morning (~9:40-10:35am QLD) — well after the main nightly refresh at 4am AEST —
    so relying on the main job alone would always be a day late reading each day's
    own picks. Doesn't touch RefreshRun/primary scrapers, just the tipster pipeline,
    so it can run independently without duplicating the main job's work."""
    db = SessionLocal()
    try:
        for scraper_cls in TIPSTER_SCRAPERS.values():
            try:
                scraper_cls().run(db)
            except Exception:
                pass  # best-effort; the next scheduled run or a manual refresh will retry
        settle_pending_picks(db)
    finally:
        db.close()
