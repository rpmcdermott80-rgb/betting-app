import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Source(Base):
    """Registry of scrapeable data sources. Evolved from the original sources.py."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    vertical: Mapped[str] = mapped_column(String(32))  # horse_racing | greyhound | afl | nrl | multi
    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_url: Mapped[str] = mapped_column(String(512))
    scrape_method: Mapped[str] = mapped_column(String(16))  # http | playwright
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceHealth(Base):
    """One row per source. Drives the Data Health tab — a source that stops
    returning data shows up here as stale/blocked instead of silently going quiet."""

    __tablename__ = "source_health"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # healthy | degraded | blocked | unknown

    source: Mapped["Source"] = relationship()


class RawScrape(Base):
    """Immutable log of every fetch attempt, success or failure. Nothing downstream
    is ever derived except from a row that actually landed here — no fabricated data."""

    __tablename__ = "raw_scrapes"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    url: Mapped[str] = mapped_column(String(1024))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | processed | failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    vertical: Mapped[str] = mapped_column(String(32))


class Horse(Base):
    __tablename__ = "horses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Greyhound(Base):
    __tablename__ = "greyhounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sport: Mapped[str] = mapped_column(String(16))  # afl | nrl


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    vertical: Mapped[str] = mapped_column(String(32))
    sport: Mapped[str] = mapped_column(String(32))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True)  # racing only
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    external_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled | completed | abandoned


class EventParticipant(Base):
    """entity_type/entity_id is a soft (non-FK-enforced) polymorphic reference into
    horses/greyhounds/players, since the entity table depends on entity_type."""

    __tablename__ = "event_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    entity_type: Mapped[str] = mapped_column(String(16))  # horse | greyhound | player
    entity_id: Mapped[int] = mapped_column(Integer)
    barrier_or_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scratched: Mapped[bool] = mapped_column(Boolean, default=False)


class Result(Base):
    """Actual finishing positions/scores. The backtesting backbone."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[int] = mapped_column(Integer)
    finish_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    margin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PlayerGameLog(Base):
    """Per-player per-stat-per-game values, e.g. disposals, goals, tries for one game.
    This is the table the legz.com.au hit-rate approach reads from."""

    __tablename__ = "player_game_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    stat_type: Mapped[str] = mapped_column(String(32))  # disposals | goals | tries | kicking_points | ...
    stat_value: Mapped[float] = mapped_column(Numeric)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OddsSnapshot(Base):
    """Append-only price history. Never overwritten — a later backtest needs the
    price that was actually available at a point in time, not today's price."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[int] = mapped_column(Integer)
    market_type: Mapped[str] = mapped_column(String(16))  # win | place | line | prop
    line_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price: Mapped[float] = mapped_column(Numeric)
    bookmaker: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))


class ModelVersion(Base):
    """Every trained model traces to a version with its own stored backtest summary."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    vertical: Mapped[str] = mapped_column(String(32))
    version_label: Mapped[str] = mapped_column(String(64))
    trained_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    backtest_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Tip(Base):
    __tablename__ = "tips"

    id: Mapped[int] = mapped_column(primary_key=True)
    vertical: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[int] = mapped_column(Integer)
    market_type: Mapped[str] = mapped_column(String(16))
    line: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    recommended_side: Mapped[str] = mapped_column(String(16))  # over | under | win | place
    stat_basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rationale_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class UserBet(Base):
    """Real, persisted bet log. This table is the fix for Track Record resetting to 0-0."""

    __tablename__ = "user_bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tip_id: Mapped[int | None] = mapped_column(ForeignKey("tips.id"), nullable=True)
    placed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stake: Mapped[float] = mapped_column(Numeric)
    odds_taken: Mapped[float] = mapped_column(Numeric)
    outcome: Mapped[str] = mapped_column(String(16), default="pending")  # pending | win | loss | void
    settled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChecklistItem(Base):
    """Rules Checklist tab — simple persisted CRUD list."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(256))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RefreshRun(Base):
    """One row per refresh job (scheduled or manually triggered), so the UI can show
    real last-run status/history instead of silently running in the background."""

    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | completed | failed
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # PID of the OS subprocess actually doing the work (see app/run_refresh_job.py) —
    # lets the watchdog tell a genuinely hung run from one that's still alive and
    # working, and kill it cleanly instead of restarting the whole API process.
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FormStart(Base):
    """One row per past race a horse/greyhound ran, pulled from the source's own
    per-runner history endpoint. This is the raw material for our own form analysis
    (recent finishes, trial/jump-out performance, distance/track record) — distinct
    from `results`, which only covers races WE scrape as meetings. Trials and
    jump-outs are kept (is_trial / is_jumpout) because form judgement weighs them
    differently from real starts."""

    __tablename__ = "form_starts"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # horse | greyhound
    entity_id: Mapped[int] = mapped_column(Integer)
    race_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    finish_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    margin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    distance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    track_condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    starting_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    is_jumpout: Mapped[bool] = mapped_column(Boolean, default=False)
    external_race_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchResult(Base):
    """Final score for one AFL/NRL match. Our own analysis never needed team-level
    results (only PlayerGameLog), so this didn't exist before — added specifically to
    verify match-winner-style TipsterPicks, derived from the same boxscore pages
    afltables.com/rugbyleagueproject.org already fetch for player stats."""

    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True)
    home_team: Mapped[str] = mapped_column(String(128))
    away_team: Mapped[str] = mapped_column(String(128))
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TipsterPick(Base):
    """A real, verbatim pick published by a third-party tipster. Deliberately NOT the
    `Tip` model — this can never blend into `/api/tips/*`, Track Record, or the
    existing bet-settlement code. We track each pick and compute OUR OWN verified
    win-rate from real results; the tipster's self-reported record is never trusted
    or shown (see FormStart/settle_bets.py for the same "verify, don't trust" pattern
    applied to our own analysis)."""

    __tablename__ = "tipster_picks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    sport: Mapped[str] = mapped_column(String(16))  # horse_racing | greyhound | afl | nrl
    published_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    raw_selection_text: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # horse | greyhound | player
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    market_type: Mapped[str | None] = mapped_column(String(24), nullable=True)  # win | match_winner
    line: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    recommended_side: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="pending")  # pending|win|loss|void|unresolved
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str] = mapped_column(String(256))  # dedupe key: source-specific, e.g. page URL + selection
    scraped_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
