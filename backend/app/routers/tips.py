from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, Greyhound, Horse, Player, Result, Tip, Venue
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


def _enrich(tip: Tip, db: Session) -> TipOut:
    entity_name, entity_team = None, None
    model = ENTITY_MODELS.get(tip.entity_type)
    if model is not None and tip.entity_id:
        entity = db.get(model, tip.entity_id)
        if entity is not None:
            entity_name = entity.name
            entity_team = getattr(entity, "team", None)

    venue_name, race_number, start_time = None, None, None
    event = db.get(Event, tip.event_id) if tip.event_id else None
    if event is not None:
        race_number = event.race_number
        start_time = event.start_time
        if event.venue_id:
            venue = db.get(Venue, event.venue_id)
            venue_name = venue.name if venue else None

    result_status, finish_position = (
        _racing_result(tip, event, db) if tip.vertical in RACING_VERTICALS else ("pending", None)
    )

    return TipOut(
        id=tip.id,
        vertical=tip.vertical,
        event_id=tip.event_id,
        entity_type=tip.entity_type,
        entity_id=tip.entity_id,
        entity_name=entity_name,
        entity_team=entity_team,
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
