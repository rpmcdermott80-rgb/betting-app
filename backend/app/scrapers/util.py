import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, FormStart, MatchResult, Player, PlayerGameLog, Source, TipsterPick, Venue


def get_source(db: Session, name: str) -> Source:
    source = db.scalar(select(Source).where(Source.name == name))
    if source is None:
        raise ValueError(f"Source {name!r} not found — run `python -m app.seed` first")
    return source


def get_or_create_player(db: Session, name: str, sport: str, team: str | None = None) -> Player:
    player = db.scalar(select(Player).where(Player.name == name, Player.sport == sport))
    if player is None:
        # Different sources format names differently (e.g. reconstructing "Firstname
        # Lastname" from a "LASTNAME, Firstname" table can mangle casing like
        # "McInnes" -> "Mcinnes"). Fall back to a case-insensitive match and reuse
        # whatever casing is already stored, rather than creating a near-duplicate
        # Player for the same real person.
        player = db.scalar(
            select(Player).where(func.lower(Player.name) == name.lower(), Player.sport == sport)
        )
    if player is None:
        player = Player(name=name, sport=sport, team=team)
        db.add(player)
        db.flush()
    elif team and player.team != team:
        player.team = team  # keep current team up to date
    return player


def get_or_create_venue(db: Session, name: str, vertical: str) -> Venue:
    venue = db.scalar(select(Venue).where(Venue.name == name, Venue.vertical == vertical))
    if venue is None:
        venue = Venue(name=name, vertical=vertical)
        db.add(venue)
        db.flush()
    return venue


def get_or_create_horse(db: Session, name: str, external_id: str | None = None):
    from app.models import Horse

    query = select(Horse).where(Horse.name == name)
    horse = db.scalar(query)
    if horse is None:
        horse = Horse(name=name, external_id=external_id)
        db.add(horse)
        db.flush()
    return horse


def parse_price(raw: str | None) -> float | None:
    """Parses bookmaker price strings like '$7.50' into a float."""
    if not raw:
        return None
    try:
        return float(raw.replace("$", "").strip())
    except ValueError:
        return None


def get_or_create_greyhound(db: Session, name: str, external_id: str | None = None):
    from app.models import Greyhound

    greyhound = db.scalar(select(Greyhound).where(Greyhound.name == name))
    if greyhound is None:
        greyhound = Greyhound(name=name, external_id=external_id)
        db.add(greyhound)
        db.flush()
    return greyhound


def upsert_player_game_log(
    db: Session,
    player_id: int,
    event_id: int,
    stat_type: str,
    stat_value: float,
    source_id: int,
) -> bool:
    """Returns True if a new row was created. A game's stats don't change once
    played, so an existing (player, event, stat_type) row is left as-is rather
    than re-inserted — re-scraping a player's page must not duplicate history."""
    existing = db.scalar(
        select(PlayerGameLog).where(
            PlayerGameLog.player_id == player_id,
            PlayerGameLog.event_id == event_id,
            PlayerGameLog.stat_type == stat_type,
        )
    )
    if existing is not None:
        return False
    db.add(
        PlayerGameLog(
            player_id=player_id,
            event_id=event_id,
            stat_type=stat_type,
            stat_value=stat_value,
            source_id=source_id,
        )
    )
    return True


def upsert_form_start(
    db: Session,
    entity_type: str,
    entity_id: int,
    race_date: dt.datetime,
    external_race_id: str | None,
    source_id: int,
    **fields,
) -> bool:
    """Store one past-race form row, deduped on (entity, external_race_id) when a race
    id is available, else (entity, race_date, distance). Past races don't change, so an
    existing row is left as-is. Returns True if a new row was created."""
    query = select(FormStart).where(
        FormStart.entity_type == entity_type, FormStart.entity_id == entity_id
    )
    if external_race_id:
        query = query.where(FormStart.external_race_id == external_race_id)
    else:
        query = query.where(FormStart.race_date == race_date, FormStart.distance == fields.get("distance"))
    if db.scalar(query) is not None:
        return False
    db.add(
        FormStart(
            entity_type=entity_type,
            entity_id=entity_id,
            race_date=race_date,
            external_race_id=external_race_id,
            source_id=source_id,
            **fields,
        )
    )
    return True


def upsert_match_result(
    db: Session,
    event_id: int,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> bool:
    """One row per completed AFL/NRL match's final score. A match's score never
    changes once played, so an existing row is left as-is. Returns True if new."""
    if db.scalar(select(MatchResult).where(MatchResult.event_id == event_id)) is not None:
        return False
    db.add(
        MatchResult(
            event_id=event_id,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
        )
    )
    return True


def upsert_tipster_pick(
    db: Session,
    source_id: int,
    sport: str,
    published_at: dt.datetime,
    raw_selection_text: str,
    external_id: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    event_id: int | None = None,
    market_type: str | None = None,
    line: float | None = None,
    recommended_side: str | None = None,
    outcome: str = "pending",
) -> bool:
    """One row per published tipster pick, deduped on (source_id, external_id) so
    re-scraping a page already seen doesn't duplicate it. Returns True if new."""
    existing = db.scalar(
        select(TipsterPick).where(
            TipsterPick.source_id == source_id, TipsterPick.external_id == external_id
        )
    )
    if existing is not None:
        return False
    db.add(
        TipsterPick(
            source_id=source_id,
            sport=sport,
            published_at=published_at,
            raw_selection_text=raw_selection_text,
            external_id=external_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_id=event_id,
            market_type=market_type,
            line=line,
            recommended_side=recommended_side,
            outcome=outcome,
        )
    )
    return True


def get_or_create_event(
    db: Session,
    external_key: str,
    external_value: str,
    vertical: str,
    sport: str,
    start_time: dt.datetime,
    venue_id: int | None = None,
    status: str = "completed",
    race_number: int | None = None,
) -> Event:
    event = db.scalar(
        select(Event).where(Event.external_ids[external_key].as_string() == external_value)
    )
    if event is None:
        event = Event(
            vertical=vertical,
            sport=sport,
            start_time=start_time,
            external_ids={external_key: external_value},
            venue_id=venue_id,
            status=status,
            race_number=race_number,
        )
        db.add(event)
        db.flush()
    else:
        event.status = status
        if race_number is not None:
            event.race_number = race_number  # backfill on re-scrape
    return event
