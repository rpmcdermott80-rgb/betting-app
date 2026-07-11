from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, Greyhound, Horse, Player, Tip, Venue
from app.schemas import TipOut

router = APIRouter(prefix="/api/tips", tags=["tips"])

VERTICALS = {
    "horse": "horse_racing",
    "greyhound": "greyhound",
    "player-props": "player_prop",
    "multis": "multi",
}

ENTITY_MODELS = {"horse": Horse, "greyhound": Greyhound, "player": Player}


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
