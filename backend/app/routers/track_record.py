import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.settle_bets import settle_pending_bets
from app.db import get_db
from app.models import Event, Greyhound, Horse, Player, Tip, UserBet, Venue
from app.schemas import UserBetIn, UserBetOut, UserBetSettle

router = APIRouter(prefix="/api/bets", tags=["track_record"])

ENTITY_MODELS = {"horse": Horse, "greyhound": Greyhound, "player": Player}
AUTO_SETTLEABLE_VERTICALS = {"horse_racing", "greyhound"}


def _tip_label(tip: Tip, db: Session) -> str:
    if tip.vertical == "multi":
        legs = (tip.stat_basis or {}).get("legs", [])
        return f"{len(legs)}-leg multi"

    model = ENTITY_MODELS.get(tip.entity_type)
    entity = db.get(model, tip.entity_id) if model and tip.entity_id else None
    name = entity.name if entity else tip.recommended_side

    if tip.vertical in ("horse_racing", "greyhound"):
        event = db.get(Event, tip.event_id) if tip.event_id else None
        venue = db.get(Venue, event.venue_id) if event and event.venue_id else None
        race = f"Race {event.race_number}" if event and event.race_number is not None else None
        context = " · ".join(p for p in [venue.name if venue else None, race] if p)
        return f"{name} to win" + (f" — {context}" if context else "")

    if tip.vertical == "player_prop":
        line = f" {tip.line}" if tip.line is not None else ""
        return f"{name} {tip.market_type} {tip.recommended_side}{line}"

    return name


def _enrich(bet: UserBet, db: Session) -> UserBetOut:
    tip_label, tip_vertical, auto_settleable = None, None, False
    if bet.tip_id is not None:
        tip = db.get(Tip, bet.tip_id)
        if tip is not None:
            tip_label = _tip_label(tip, db)
            tip_vertical = tip.vertical
            auto_settleable = tip.vertical in AUTO_SETTLEABLE_VERTICALS

    return UserBetOut(
        id=bet.id,
        tip_id=bet.tip_id,
        placed_at=bet.placed_at,
        stake=float(bet.stake),
        odds_taken=float(bet.odds_taken),
        outcome=bet.outcome,
        settled_at=bet.settled_at,
        notes=bet.notes,
        tip_label=tip_label,
        tip_vertical=tip_vertical,
        auto_settleable=auto_settleable,
    )


@router.get("", response_model=list[UserBetOut])
def list_bets(db: Session = Depends(get_db)):
    stmt = select(UserBet).order_by(UserBet.placed_at.desc())
    return [_enrich(b, db) for b in db.scalars(stmt)]


@router.post("", response_model=UserBetOut)
def log_bet(bet: UserBetIn, db: Session = Depends(get_db)):
    row = UserBet(**bet.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _enrich(row, db)


@router.post("/settle")
def settle_all_pending(db: Session = Depends(get_db)) -> dict:
    """Manually runs the same auto-settlement the nightly/manual refresh does,
    without waiting for a full scrape — useful right after a race you know has
    finished. Only resolves horse_racing/greyhound bets; player-prop/multi bets
    have no future-fixture data to check against and stay pending."""
    return settle_pending_bets(db)


@router.patch("/{bet_id}/settle", response_model=UserBetOut)
def settle_bet(bet_id: int, settle: UserBetSettle, db: Session = Depends(get_db)):
    row = db.get(UserBet, bet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bet not found")
    if settle.outcome not in ("win", "loss", "void"):
        raise HTTPException(status_code=400, detail="outcome must be win, loss, or void")
    row.outcome = settle.outcome
    row.settled_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    db.refresh(row)
    return _enrich(row, db)
