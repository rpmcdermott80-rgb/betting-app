"""Tipster Tips API — deliberately separate from /api/tips/*. Serves real,
third-party-published picks (TipsterPick), each with OUR OWN verified win-rate
computed from real settled outcomes, never the tipster's self-reported record.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, Greyhound, Horse, Source, TipsterPick, Venue
from app.schemas import TipsterPickOut, TipsterSourceStats, TipsterTipsOut

router = APIRouter(prefix="/api/tipster-tips", tags=["tipster_tips"])

SPORTS = {"horse": "horse_racing", "greyhound": "greyhound", "afl": "afl", "nrl": "nrl"}
ENTITY_MODELS = {"horse": Horse, "greyhound": Greyhound}


def _event_context(pick: TipsterPick, db: Session) -> str | None:
    if pick.event_id is None:
        return None
    event = db.get(Event, pick.event_id)
    if event is None:
        return None
    if pick.sport in ("horse_racing", "greyhound"):
        venue = db.get(Venue, event.venue_id) if event.venue_id else None
        parts = [venue.name if venue else None, f"Race {event.race_number}" if event.race_number else None]
        return " · ".join(p for p in parts if p) or None
    if pick.sport in ("afl", "nrl"):
        from app.models import MatchResult

        mr = db.scalar(select(MatchResult).where(MatchResult.event_id == pick.event_id))
        return f"{mr.home_team} vs {mr.away_team}" if mr else None
    return None


def _entity_name(pick: TipsterPick, db: Session) -> str | None:
    if pick.entity_type in ENTITY_MODELS and pick.entity_id is not None:
        entity = db.get(ENTITY_MODELS[pick.entity_type], pick.entity_id)
        return entity.name if entity else None
    if pick.entity_type == "team":
        return pick.recommended_side
    return None


def _enrich(pick: TipsterPick, source_name: str, db: Session) -> TipsterPickOut:
    return TipsterPickOut(
        id=pick.id,
        sport=pick.sport,
        source_name=source_name,
        published_at=pick.published_at,
        raw_selection_text=pick.raw_selection_text,
        entity_name=_entity_name(pick, db),
        event_context=_event_context(pick, db),
        market_type=pick.market_type,
        line=float(pick.line) if pick.line is not None else None,
        recommended_side=pick.recommended_side,
        outcome=pick.outcome,
        resolved_at=pick.resolved_at,
    )


def _source_stats(sport: str, db: Session) -> list[TipsterSourceStats]:
    source_ids = db.scalars(select(TipsterPick.source_id).where(TipsterPick.sport == sport).distinct())
    stats = []
    for source_id in source_ids:
        source = db.get(Source, source_id)
        if source is None:
            continue
        picks = list(db.scalars(select(TipsterPick).where(TipsterPick.source_id == source_id, TipsterPick.sport == sport)))
        wins = sum(1 for p in picks if p.outcome == "win")
        losses = sum(1 for p in picks if p.outcome == "loss")
        settled = wins + losses
        stats.append(
            TipsterSourceStats(
                source_name=source.name,
                settled_wins=wins,
                settled_losses=losses,
                win_rate=round(wins / settled, 3) if settled > 0 else None,
            )
        )
    # Best VERIFIED record first — sources with no settled picks yet sort last, not first.
    stats.sort(key=lambda s: (s.win_rate is None, -(s.win_rate or 0)))
    return stats


def _tips_for(sport: str, db: Session) -> TipsterTipsOut:
    stmt = select(TipsterPick).where(TipsterPick.sport == sport).order_by(TipsterPick.published_at.desc())
    picks = []
    for p in db.scalars(stmt):
        source = db.get(Source, p.source_id)
        picks.append(_enrich(p, source.name if source else "unknown", db))
    return TipsterTipsOut(sources=_source_stats(sport, db), picks=picks)


@router.get("/horse", response_model=TipsterTipsOut)
def horse(db: Session = Depends(get_db)):
    return _tips_for(SPORTS["horse"], db)


@router.get("/greyhound", response_model=TipsterTipsOut)
def greyhound(db: Session = Depends(get_db)):
    return _tips_for(SPORTS["greyhound"], db)


@router.get("/afl", response_model=TipsterTipsOut)
def afl(db: Session = Depends(get_db)):
    return _tips_for(SPORTS["afl"], db)


@router.get("/nrl", response_model=TipsterTipsOut)
def nrl(db: Session = Depends(get_db)):
    return _tips_for(SPORTS["nrl"], db)
