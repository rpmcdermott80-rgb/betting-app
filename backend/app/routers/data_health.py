from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Source, SourceHealth
from app.schemas import SourceHealthOut

router = APIRouter(prefix="/api/data-health", tags=["data_health"])


@router.get("", response_model=list[SourceHealthOut])
def data_health(db: Session = Depends(get_db)):
    stmt = select(Source, SourceHealth).outerjoin(SourceHealth, SourceHealth.source_id == Source.id)
    rows = db.execute(stmt).all()
    out = []
    for source, health in rows:
        out.append(
            SourceHealthOut(
                source_name=source.name,
                vertical=source.vertical,
                status=health.status if health else "unknown",
                last_success_at=health.last_success_at if health else None,
                last_attempt_at=health.last_attempt_at if health else None,
                consecutive_failures=health.consecutive_failures if health else 0,
            )
        )
    return out
