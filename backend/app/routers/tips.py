import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, Greyhound, Horse, Player, PlayerGameLog, Result, Tip, Venue
from app.schemas import TipOut

router = APIRouter(prefix="/api/tips", tags=["tips"])

VERTICALS = {
    "horse": "horse_racing",
    "greyhound": "greyhound",
    "player-props": "player_prop",
    "multis": "multi",
}

ENTITY_MODELS = {"horse": Horse, "greyhound": Greyhound, "player": Player}
RACING_VERTICALS = {"horse_racing", "greyhound"}

# A player_prop tip is a snapshot of "recent form" as of its anchor game. Once a
# player hasn't played in this long, that snapshot no longer represents anything
# current (retired/delisted players' years-old tips were otherwise sitting forever
# alongside live ones, sorted by confidence, with no way to tell them apart) — long
# enough to survive a normal AFL/NRL off-season gap, short enough to exclude
# genuinely stale entries.
PLAYER_PROP_STALE_DAYS = 270


def _racing_result(tip: Tip, event: Event | None, db: Session) -> tuple[str, int | None]:
    """Real outcome for a win-market racing tip, computed the same way
    settle_bets.py settles a bet on it — shown on every tip regardless of
    whether the user actually took a bet on it."""
    if event is None or event.status != "completed":
        return "pending", None
    result = db.scalar(
        select(Result).where(
            Result.event_id == tip.event_id,
            Result.entity_type == tip.entity_type,
            Result.entity_id == tip.entity_id,
        )
    )
    if result is None or result.finish_position is None:
        return "pending", None
    return ("won" if result.finish_position == 1 else "lost"), result.finish_position


def _player_prop_result(tip: Tip, db: Session) -> tuple[str, int | None]:
    """A player_prop tip is a snapshot of recent form, not tied to a specific
    upcoming fixture — so "did this hit" means checking the player's next
    *actually played* game once our own scrapers log it, not a scheduled event.
    Real data only: if no later game has been logged yet, stays pending."""
    anchor_event = db.get(Event, tip.event_id) if tip.event_id else None
    if anchor_event is None or tip.line is None:
        return "pending", None
    next_log = db.scalar(
        select(PlayerGameLog)
        .join(Event, PlayerGameLog.event_id == Event.id)
        .where(
            PlayerGameLog.player_id == tip.entity_id,
            PlayerGameLog.stat_type == tip.market_type,
            Event.start_time > anchor_event.start_time,
        )
        .order_by(Event.start_time.asc())
    )
    if next_log is None:
        return "pending", None
    value = float(next_log.stat_value)
    threshold = float(tip.line)
    hit = value >= threshold if tip.recommended_side == "over" else value < threshold
    return ("won" if hit else "lost"), None


def _multi_result(tip: Tip, db: Session) -> tuple[str, int | None]:
    """A multi is only as good as its weakest leg — resolve each leg via the same
    next-real-game check the Player Props tab uses. Won only once every leg has
    won; lost as soon as any single leg loses (the rest no longer matter); still
    pending otherwise, even if some legs have already resolved."""
    legs = (tip.stat_basis or {}).get("legs") or []
    if not legs:
        return "pending", None
    statuses = []
    for leg in legs:
        leg_tip = db.get(Tip, leg.get("tip_id")) if leg.get("tip_id") else None
        if leg_tip is None:
            statuses.append("pending")
            continue
        status, _ = _player_prop_result(leg_tip, db)
        statuses.append(status)
    if any(s == "lost" for s in statuses):
        return "lost", None
    if all(s == "won" for s in statuses):
        return "won", None
    return "pending", None


def _enrich(tip: Tip, db: Session) -> TipOut:
    entity_name, entity_team, entity_sport = None, None, None
    model = ENTITY_MODELS.get(tip.entity_type)
    if model is not None and tip.entity_id:
        entity = db.get(model, tip.entity_id)
        if entity is not None:
            entity_name = entity.name
            entity_team = getattr(entity, "team", None)
            entity_sport = getattr(entity, "sport", None)

    venue_name, race_number, start_time = None, None, None
    event = db.get(Event, tip.event_id) if tip.event_id else None
    if event is not None:
        race_number = event.race_number
        start_time = event.start_time
        if event.venue_id:
            venue = db.get(Venue, event.venue_id)
            venue_name = venue.name if venue else None

    if tip.vertical in RACING_VERTICALS:
        result_status, finish_position = _racing_result(tip, event, db)
    elif tip.vertical == "player_prop":
        result_status, finish_position = _player_prop_result(tip, db)
    elif tip.vertical == "multi":
        result_status, finish_position = _multi_result(tip, db)
    else:
        result_status, finish_position = "pending", None

    return TipOut(
        id=tip.id,
        vertical=tip.vertical,
        event_id=tip.event_id,
        entity_type=tip.entity_type,
        entity_id=tip.entity_id,
        entity_name=entity_name,
        entity_team=entity_team,
        sport=entity_sport,
        market_type=tip.market_type,
        line=float(tip.line) if tip.line is not None else None,
        recommended_side=tip.recommended_side,
        rationale_text=tip.rationale_text,
        confidence_score=float(tip.confidence_score) if tip.confidence_score is not None else None,
        venue_name=venue_name,
        race_number=race_number,
        start_time=start_time,
        stat_basis=tip.stat_basis,
        generated_at=tip.generated_at,
        result_status=result_status,
        finish_position=finish_position,
    )


def _tips_for(vertical: str, db: Session) -> list[TipOut]:
    # Highest confidence first (nulls last), then most recent.
    stmt = (
        select(Tip)
        .where(Tip.vertical == vertical)
        .order_by(Tip.confidence_score.desc().nullslast(), Tip.generated_at.desc())
    )
    if vertical == "player_prop":
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=PLAYER_PROP_STALE_DAYS)
        stmt = stmt.join(Event, Tip.event_id == Event.id).where(Event.start_time >= cutoff)
    return [_enrich(t, db) for t in db.scalars(stmt)]


@router.get("/horse", response_model=list[TipOut])
def horse_tips(db: Session = Depends(get_db)):
    return _tips_for(VERTICALS["horse"], db)


@router.get("/greyhound", response_model=list[TipOut])
def greyhound_tips(db: Session = Depends(get_db)):
    return _tips_for(VERTICALS["greyhound"], db)


@router.get("/player-props", response_model=list[TipOut])
def player_props(db: Session = Depends(get_db)):
    return _tips_for(VERTICALS["player-props"], db)


@router.get("/multis", response_model=list[TipOut])
def multis(db: Session = Depends(get_db)):
    return _tips_for(VERTICALS["multis"], db)
