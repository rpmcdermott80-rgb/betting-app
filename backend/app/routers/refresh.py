from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RefreshRun
from app.refresh import (
    is_refresh_running,
    launch_refresh_subprocess,
    record_run_pid,
    start_refresh_run,
)
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
    # A real OS subprocess rather than an in-process thread — a hang only kills this
    # one process (the watchdog in app/refresh.py detects and kills it by PID), not
    # the whole API server the way an in-process thread hang used to.
    proc = launch_refresh_subprocess(run.id)
    record_run_pid(db, run.id, proc.pid)
    return RefreshTriggerOut(status="started", run_id=run.id)
