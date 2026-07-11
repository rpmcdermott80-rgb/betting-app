import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RefreshRun
from app.refresh import execute_refresh, is_refresh_running, start_refresh_run
from app.schemas import RefreshRunOut, RefreshTriggerOut

router = APIRouter(prefix="/api/refresh", tags=["refresh"])


@router.get("/latest", response_model=RefreshRunOut | None)
def latest_refresh(db: Session = Depends(get_db)):
    return db.query(RefreshRun).order_by(RefreshRun.started_at.desc()).first()


@router.post("/trigger", response_model=RefreshTriggerOut)
def trigger_refresh(db: Session = Depends(get_db)):
    if is_refresh_running(db):
        latest = db.query(RefreshRun).order_by(RefreshRun.started_at.desc()).first()
        return RefreshTriggerOut(status="already_running", run_id=latest.id)

    run = start_refresh_run(db)
    # Scrapers are sync (httpx/SQLAlchemy), so run in a background thread rather than
    # blocking the request — this is a single-user tool, a plain thread is enough,
    # no task queue needed.
    threading.Thread(target=execute_refresh, args=(run.id,), daemon=True).start()
    return RefreshTriggerOut(status="started", run_id=run.id)
